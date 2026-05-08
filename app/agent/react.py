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
               tools_desc: str = "", force_tool: str = "") -> ReActStep:
        # Step always has a tool_hint when we reach decide (summary steps bypass ReAct).
        # Force the planned tool — LLM is only used to determine args.
        planned_tool = force_tool or step.tool_hint
        if not planned_tool or planned_tool not in list_available_tools():
            self._log.warning(f"No valid tool_hint, using fallback")
            return self._fallback_decide(step)

        prompt = self._build_decision_prompt(
            goal, step, history, tools_desc,
            step_hint=planned_tool,
        )
        try:
            resp = self._llm.generate_structured(prompt)
            # Always use the planned tool — LLM's action field is ignored
            action = planned_tool
            args = resp.get("action_args", {})
            # If LLM put args under a wrong key or nested, try to fix
            if not args and isinstance(resp, dict):
                # Sometimes LLM puts everything inline
                args = {k: v for k, v in resp.items()
                        if k not in ("thought", "action", "step_id") and v}
            if not isinstance(args, dict):
                args = {}
            # If LLM gave empty args, use defaults
            if not args:
                args = self._default_args(step, action)
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

    def _build_decision_prompt(self, goal: str, step, history: str,
                               tools_desc: str, step_hint: str = "") -> str:
        tools_info = tools_desc or "\n".join(
            f"- {name}: {desc}" for name, desc in list_available_tools().items()
        )
        hint_line = (
            f"\n**当前工具已锁定: {step_hint}** — 你只需要推理并生成合适的 action_args 参数。"
            if step_hint else ""
        )
        return f"""你是 ReAct 推理代理。根据当前目标和步骤，生成合适的工具调用参数。

目标: {goal}
当前步骤: {step.description}{hint_line}

可用工具信息:
{tools_info}

历史记录与经验:
{history or "无"}

重要规则:
1. action 字段填空字符串 "" 即可（工具已由计划锁定）
2. action_args 必须根据历史记录中的信息来填充:
   - run_tool 的 command 参数从上一步 plan_run_tool 的输出中提取完整命令
   - clone_tool 的 repo_url 从历史记录中已找到的源码地址获取
   - search_tool 的 query 使用步骤描述中的查询词
   - fetch_tool 的 url 从历史记录中已找到的URL获取
   - setup_tool/read_repo_tool/plan_run_tool 通常不需要参数（自动检测仓库）
3. 从历史记录中提取信息时，注意提取完整内容（如完整命令、完整URL）

输出 JSON:
{{"thought": "推理过程", "action": "", "action_args": {{"参数": "值"}}}}"""

    @staticmethod
    def _first_url(text: str) -> str:
        import re
        urls = re.findall(r'https?://[^\s<>",{}|\\^`\[\]]+', text)
        return urls[0] if urls else ""

    def _build_forced_step(self, step, force_tool: str) -> ReActStep:
        """Build a ReAct step using the forced tool, no LLM needed."""
        return ReActStep(
            thought=f"[计划步骤] 使用 {force_tool} 执行: {step.description}",
            action=force_tool,
            action_args=self._default_args(step, force_tool),
        )

    def _default_args(self, step, tool_name: str) -> dict:
        """Build default args for a tool based on step description."""
        desc = step.description.lower()
        if tool_name == "search_tool":
            return {"query": step.description}
        elif tool_name == "fetch_tool":
            return {"url": ""}
        elif tool_name == "source_tool":
            return {"paper_info": step.description}
        elif tool_name == "clone_tool":
            repo_url = self._first_url(step.description)
            return {"repo_url": repo_url}
        elif tool_name == "setup_tool":
            return {}
        elif tool_name == "read_repo_tool":
            return {}
        elif tool_name == "plan_run_tool":
            return {}
        elif tool_name == "run_tool":
            return {"command": ""}
        elif tool_name == "execute_tool":
            return {}
        return {}

    def _fallback_decide(self, step) -> ReActStep:
        if step.tool_hint:
            hint = step.tool_hint
            if hint == "search_tool":
                args = {"query": step.description}
            elif hint == "fetch_tool":
                args = {"url": ""}
            elif hint == "source_tool":
                args = {"paper_info": step.description}
            elif hint == "clone_tool":
                args = {"repo_url": self._first_url(step.description)}
            elif hint == "read_repo_tool":
                args = {}
            elif hint == "plan_run_tool":
                args = {}
            elif hint == "run_tool":
                args = {"command": ""}
            elif hint == "setup_tool":
                args = {}
            elif hint == "execute_tool":
                args = {"repo_path": "", "timeout": 600}
            else:
                args = {}
            return ReActStep(
                thought=f"使用 {hint} 执行: {step.description}",
                action=hint,
                action_args=args,
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
        elif "克隆" in desc or "clone" in desc:
            repo_url = self._first_url(step.description)
            return ReActStep(thought=f"克隆仓库", action="clone_tool",
                             action_args={"repo_url": repo_url})
        elif "配置" in desc or "setup" in desc or "环境" in desc or "依赖" in desc:
            return ReActStep(thought=f"配置环境", action="setup_tool", action_args={})
        elif "规划" in desc or "plan run" in desc or "确定.*命令" in desc:
            return ReActStep(thought=f"规划执行命令", action="plan_run_tool", action_args={})
        elif any(kw in desc for kw in ["执行", "运行", "execute", "run", "复现脚本"]):
            return ReActStep(thought=f"执行复现", action="run_tool", action_args={})
        elif "分析" in desc and ("仓库" in desc or "repo" in desc):
            return ReActStep(thought=f"分析仓库", action="read_repo_tool", action_args={})
        return ReActStep(thought=f"执行: {step.description}", action="idle")
