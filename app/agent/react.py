from typing import Any, Dict, Optional

from app.core.llm import get_llm
from app.core.logging import get_logger
from app.tools import get_tool, list_available_tools


class ReActStep:
    def __init__(self, thought: str, action: str, action_args: dict = None,
                 observation: str = "", status: str = "pending"):
        self.thought = thought
        self.action = action
        self.action_args = action_args or {}
        self.observation = observation
        self.status = status  # pending, success, failed

    def to_dict(self) -> dict:
        return {
            "thought": self.thought, "action": self.action,
            "action_args": self.action_args, "observation": self.observation,
            "status": self.status,
        }


class ReActEngine:
    def __init__(self, max_retries: int = 3):
        self._llm = get_llm()
        self._max_retries = max_retries
        self._log = get_logger("react")

    def decide(self, goal: str, step: "PlanStep", history: str = "",
               tools_desc: str = "") -> ReActStep:
        prompt = self._build_decision_prompt(goal, step, history, tools_desc)
        try:
            resp = self._llm.generate_structured(prompt)
            action = resp.get("action", "search_tool")
            # Sanitize: reject invalid action names
            valid_actions = set(list_available_tools().keys()) | {"idle", "finish", "report"}
            if action not in valid_actions:
                self._log.warning(f"Invalid action '{action}', falling back to search_tool")
                action = "search_tool"
            args = resp.get("action_args", {})
            if not isinstance(args, dict):
                args = {}
            return ReActStep(
                thought=resp.get("thought", ""),
                action=action,
                action_args=args,
            )
        except Exception as e:
            self._log.error(f"Decision failed: {e}, using fallback")
            return self._fallback_decide(step)

    def execute(self, react_step: ReActStep) -> str:
        action = react_step.action
        if action in ("idle", "finish", "report"):
            return "Task step acknowledged"

        tool = get_tool(action)
        if tool is None:
            available = ", ".join(list_available_tools().keys())
            msg = f"Unknown tool: {action}. Available: {available}"
            self._log.error(msg)
            return f"ERROR: {msg}"

        self._log.info(f"Execute: {action} args={react_step.action_args}")
        try:
            result = tool.execute(**react_step.action_args)
            if result.success:
                react_step.status = "success"
                react_step.observation = result.output or "Success"
                return result.output or "Success"
            else:
                react_step.status = "failed"
                react_step.observation = result.error or "Unknown error"
                return f"ERROR: {result.error}"
        except Exception as e:
            react_step.status = "failed"
            react_step.observation = str(e)
            self._log.error(f"Execution exception: {e}")
            return f"ERROR: {e}"

    def _build_decision_prompt(self, goal: str, step, history: str, tools_desc: str) -> str:
        tools_info = tools_desc or "\n".join(
            f"- {name}: {desc}" for name, desc in list_available_tools().items()
        )
        return f"""你是 ReAct 推理代理。根据当前目标和步骤，决定下一步操作。

目标: {goal}
当前步骤: {step.description}
可用工具 (只能选择以下工具之一):
{tools_info}

历史记录与经验:
{history or "无"}

重要规则:
1. action 必须是可用工具列表中的工具名，绝不能使用 "none" 或其他不存在的工具名
2. 搜索论文使用 source="llm"（默认），LLM知识库包含大量论文信息，最可靠
3. 如果历史显示某个操作已失败多次，务必换用不同的工具或参数
4. 获取论文内容使用 fetch_tool 直接访问已知URL，无需多次搜索

输出 JSON:
{{"thought": "推理过程", "action": "工具名", "action_args": {{"参数": "值"}}}}"""

    def _fallback_decide(self, step) -> ReActStep:
        if step.tool_hint:
            return ReActStep(
                thought=f"使用 {step.tool_hint} 执行: {step.description}",
                action=step.tool_hint,
                action_args={"query": step.description} if "search" in step.tool_hint
                else {"url": ""} if "fetch" in step.tool_hint
                else {"paper_info": step.description} if "source" in step.tool_hint
                else {},
            )
        desc = step.description.lower()
        if "搜索" in desc or "search" in desc:
            return ReActStep(thought=f"搜索: {step.description}", action="search_tool",
                             action_args={"query": step.description})
        elif "获取" in desc or "阅读" in desc or "fetch" in desc or "read" in desc:
            return ReActStep(thought=f"获取内容", action="fetch_tool",
                             action_args={"url": ""})
        elif "源码" in desc or "source" in desc or "仓库" in desc or "repo" in desc:
            return ReActStep(thought=f"查找源码", action="source_tool",
                             action_args={"paper_info": step.description})
        return ReActStep(thought=f"执行: {step.description}", action="idle")
