"""
IntentClassifier — 纯 LLM 驱动的用户意图分类层

职责: 判断用户消息是"需要启动复现任务"还是"问答/辅助操作"。
完全依赖 LLM 理解语义，不使用关键词匹配。
"""

import json
import re
from enum import Enum
from pathlib import Path
from typing import Optional

from app.core.config import get_config
from app.core.llm import get_llm
from app.core.logging import get_logger


class IntentType(str, Enum):
    REPRODUCTION = "reproduction"
    ENGINEERING_TEST = "engineering_test"
    SESSION_FOLLOWUP = "session_followup"
    AUXILIARY = "auxiliary"
    QA = "qa"
    UNKNOWN = "unknown"


_CLASSIFICATION_PROMPT = """你是一个智能对话管家，负责判断用户是否需要启动「论文复现任务」。

## 背景信息
{context}

## 用户最新消息
{message}

## 你的任务
理解用户消息的**真实意图**，输出 JSON 格式的判断结果。

### 意图类型说明

1. **reproduction**（学术复现）
   - 用户要求复现一篇论文、搜索论文、找论文的代码实现
   - 消息中包含论文名、作者名、算法名等学术标识
   - 例如: "复现 Attention Is All You Need"、"帮我找一下 ResNet 论文"
   - ❌ 如果用户只是询问"你是如何复现的"、"复现结果怎么样"，这不是 reproduction

2. **engineering_test**（工程测试）
   - 用户要求测试/运行一个 GitHub 项目，但没有提到论文
   - 例如: "跑一下 ML-From-Scratch"、"克隆 tensor2tensor"

3. **session_followup**（会话跟进）
   - 用户在已完成任务的基础上要求继续操作
   - 例如: "再跑另一个脚本"、"继续执行"、"帮我看看这个报错"
   - 注意: 对话历史中有已克隆的仓库和之前的执行记录

4. **auxiliary**（辅助管理）
   - 管理工作区: 查看工作区、清理仓库、查看环境状态
   - 管理报告: 查看/搜索/删除报告
   - 查看配置/统计信息
   - 例如: "查看工作区"、"列出报告"、"清理环境"

5. **qa**（问答/咨询）
   - 用户询问知识性问题、要求解释或总结
   - 用户问"做了什么"、"结果如何"、"遇到了什么错误"
   - 用户要求"讲解"、"解释"、"总结"、"描述"之前的过程
   - 闲聊、问候
   - 例如: "讲解一下你是如何复现的"、"什么是 Transformer"

### 核心判断原则
- 用户是**询问/讨论**已完成的工作 → qa
- 用户要求**执行新的操作**（复现新论文、克隆新仓库、跑新实验）→ 对应 action 类别
- "复现"这个词本身不代表 reproduction——要看上下文是"要求执行"还是"询问过程"

### 输出格式
请严格输出以下 JSON（不要其他内容）:
```json
{{"intent": "reproduction | engineering_test | session_followup | auxiliary | qa", "reason": "用一句话说明判断理由", "requires_agent": true | false}}
```
- requires_agent=true: 需要启动 Agent 执行流水线（reproduction / engineering_test / session_followup / auxiliary）
- requires_agent=false: 不需要执行，直接问答回复即可（qa）"""


class IntentClassifier:
    """纯 LLM 驱动的意图分类器，无关键词匹配。"""

    def __init__(self):
        self._llm = get_llm()
        self._log = get_logger("intent_classifier")

    def classify(self, message: str, context: str = "") -> tuple[IntentType, bool]:
        """判断用户意图。

        Args:
            message: 用户消息
            context: 对话上下文（上次执行结果、工作区状态等）

        Returns:
            (intent, requires_agent) 元组
            - requires_agent=True: 需要启动 Agent 流水线处理
            - requires_agent=False: 不需要，直接回复即可
        """
        lower = message.lower().strip()

        # ── 极简快速路径（纯问候，不值得浪费 LLM 调用）──
        if not lower or lower in {"你好", "hello", "hi", "hey", "你好啊", "在吗"}:
            return IntentType.QA, False

        # ── LLM 分类 ──
        return self._llm_classify(message, context)

    # ------------------------------------------------------------------
    # LLM classification
    # ------------------------------------------------------------------

    def _llm_classify(self, message: str, context: str = "") -> tuple[IntentType, bool]:
        """调用 LLM 判断意图，返回 (IntentType, requires_agent)。"""
        try:
            rich_context = self._build_llm_context(context)
            prompt = _CLASSIFICATION_PROMPT.format(
                message=message[:800],
                context=rich_context,
            )
            try:
                resp = self._llm.generate(prompt, max_tokens=256, temperature=0.0)
            except Exception as e:
                self._log.warning(f"LLM generate failed: {str(e)[:200]}")
                # 尝试用 generate_stream 绕过可能的 API 问题
                try:
                    gen = self._llm.generate_stream(prompt, max_tokens=256, temperature=0.0)
                    content = ""
                    for chunk in gen:
                        content += chunk
                    from app.core.llm import LLMResponse
                    resp = LLMResponse(content=content, model="", usage={}, finish_reason="stop")
                except Exception as e2:
                    self._log.warning(f"LLM stream fallback also failed: {str(e2)[:200]}")
                    return self._fallback_classify(message)

            parsed = self._parse_llm_response(resp.content)
            if parsed:
                intent, reason, requires_agent = parsed
                self._log.info(
                    f"LLM classified: {intent.value} "
                    f"(agent={requires_agent}, reason={reason})"
                )
                return intent, requires_agent
            else:
                self._log.warning(
                    f"LLM response parse failed, raw: {resp.content[:300]}"
                )

        except Exception as e:
            self._log.warning(f"LLM classification unexpected error: {e}")

        return self._fallback_classify(message)

    def _fallback_classify(self, message: str) -> tuple[IntentType, bool]:
        """LLM 失败时的回退分类（纯启发式，保证不丢消息）。"""
        lower = message.lower().strip()

        # QA: 问句优先 —— 避免 "讲解一下你是如何复现的" 被误判为 reproduction
        question_patterns = [
            "如何", "怎么", "什么", "为什么", "哪些", "吗",
            "讲解", "解释", "说明", "描述", "介绍", "总结",
            "tell me", "explain", "describe", "what", "why", "how",
        ]
        if any(p in lower for p in question_patterns):
            return IntentType.QA, False

        # 问候
        if lower in {"你好", "hello", "hi", "hey", "在吗", "您好"}:
            return IntentType.QA, False

        # 辅助管理
        if any(kw in lower for kw in ["工作区", "workspace", "报告", "report",
                                        "配置", "config", "统计", "stats",
                                        "清理", "环境状态"]):
            return IntentType.AUXILIARY, True

        # 继续/跟进 已有任务
        if any(kw in lower for kw in ["再跑", "再试", "继续", "接着", "下一步"]):
            return IntentType.SESSION_FOLLOWUP, True

        # 复现/克隆/跑项目 任务
        if any(kw in lower for kw in ["复现", "reproduce", "复刻", "克隆", "clone",
                                        "搜索论文", "跑一下", "github",
                                        "找论文", "论文"]):
            return IntentType.REPRODUCTION, True

        return IntentType.QA, False

    @staticmethod
    def _parse_llm_response(content: str) -> Optional[tuple[IntentType, str, bool]]:
        """从 LLM 响应中健壮地解析 JSON。"""
        import json
        try:
            text = content.strip()

            # Strategy 1: ```json ... ``` block
            start = text.find("```json")
            if start >= 0:
                start += 7
                end = text.find("```", start)
                text = text[start:end].strip() if end >= 0 else text[start:].strip()

            # Strategy 2: brace matching
            brace_start = text.find("{")
            if brace_start >= 0:
                depth = 0
                for i in range(brace_start, len(text)):
                    c = text[i]
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            text = text[brace_start:i + 1]
                            break

            data = json.loads(text)
            intent = IntentType(data.get("intent", "").lower().strip())
            return intent, data.get("reason", ""), data.get("requires_agent", False)
        except Exception:
            return None

    def _build_llm_context(self, existing_context: str = "") -> str:
        """构建 LLM 上下文，包含对话历史和工作区状态。"""
        parts = []

        if existing_context:
            parts.append(f"对话历史: {existing_context[:500]}")

        # 工作区状态
        repos = self._list_workspace_repos()
        if repos:
            repo_list = ", ".join(repos)
            parts.append(f"工作区已有仓库: {repo_list}")
        else:
            parts.append("工作区无仓库")

        return "\n".join(parts) if parts else "无历史记录"

    @staticmethod
    def _list_workspace_repos() -> list:
        try:
            ws = Path(get_config().agent.workspace_dir).resolve()
            if not ws.exists():
                return []
            return sorted([
                p.name for p in ws.iterdir()
                if p.is_dir() and (p / ".git").exists()
            ])
        except Exception:
            return []


# Module-level singleton
_classifier: Optional[IntentClassifier] = None


def get_classifier() -> IntentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier
