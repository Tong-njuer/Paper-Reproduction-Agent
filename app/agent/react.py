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

    # Tools for which args are fully deterministic — skip the costly LLM call
    # and build args directly from step description / step context.
    # Tools for which args are fully deterministic — skip the costly LLM call
    # and build args directly from step description / step context.
    _DETERMINISTIC_TOOLS = {
        "python_env_tool",
        "cleanup_env_tool",
        "execute_session_tool",  # repo_path comes from _enrich_args, not LLM
        "setup_tool",
        "list_workspace_tool",
        "check_repo_tool",
        "config_tool",
        "stats_tool",
        "list_reports_tool",
    }

    def decide(self, goal: str, step: "PlanStep", history: str = "",
               tools_desc: str = "", force_tool: str = "") -> ReActStep:
        # Step always has a tool_hint when we reach decide (summary steps bypass ReAct).
        # Force the planned tool — LLM is only used to determine args.
        planned_tool = force_tool or step.tool_hint
        if not planned_tool or planned_tool not in list_available_tools():
            self._log.warning(f"No valid tool_hint, using fallback")
            return self._fallback_decide(step, goal, history)

        # ── Deterministic tools: skip LLM entirely, use default args ──
        if planned_tool in self._DETERMINISTIC_TOOLS:
            self._log.info(f"Deterministic tool {planned_tool}, skipping LLM call")
            return self._build_forced_step(step, planned_tool, goal, history)

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
                args = self._default_args(step, action, goal, history)
            return ReActStep(
                thought=resp.get("thought", ""),
                action=action,
                action_args=args,
            )
        except Exception as e:
            self._log.error(f"Decision failed: {e}, using fallback")
            return self._fallback_decide(step, goal, history)

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

    # Tool descriptions are long (23 tools).  To reduce prompt size and
    # LLM latency, we only include the description for the *current* tool
    # plus any tools that commonly supply inter-step data.
    _TOOL_HINT_DESCRIPTION_OVERRIDES = {
        "search_tool": "搜索论文或仓库。参数: query(查询词, 纯论文名不要带'复现/跑一下'等动作词), source(数据源, arxiv/web/llm, 默认llm自动组合)",
        "fetch_tool": "获取论文全文或网页内容。参数: url(目标URL)。注意：历史记录中可能包含多个URL，请选择与论文匹配的那个，特别是arXiv ID要匹配。",
        "source_tool": "查找论文的源码仓库。参数: paper_info(论文信息文本，含标题/作者/摘要）。重要: 该工具自己本身会从 paper_info 中提取 URL，你不需要预填已知的 URL。",
        "clone_tool": "克隆源码仓库到本地。参数: repo_url(仓库Git URL)",
        "execute_session_tool": "对话式执行: 自主创建venv、安装依赖、运行项目、诊断错误、修复问题，直到成功。参数: repo_name(仓库名) 或 repo_path(仓库路径)",
    }

    def _build_decision_prompt(self, goal: str, step, history: str,
                               tools_desc: str, step_hint: str = "") -> str:
        # Only show the description for the current tool (plus a few key
        # inter-step tools) to keep the prompt short and fast.
        if step_hint and step_hint in self._TOOL_HINT_DESCRIPTION_OVERRIDES:
            tools_info = f"- {step_hint}: {self._TOOL_HINT_DESCRIPTION_OVERRIDES[step_hint]}"
        elif step_hint:
            all_tools = list_available_tools()
            tools_info = f"- {step_hint}: {all_tools.get(step_hint, '(工具已注册)')}"
        else:
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

当前工具说明:
{tools_info}

历史记录与经验:
{history or "无"}

重要规则:
1. action 字段填空字符串 "" 即可（工具已由计划锁定）
2. action_args 根据当前工具的需要和历史记录中的信息来填充:
   - clone_tool 的 repo_url 从历史记录中已找到的源码地址获取
   - search_tool 的 query 使用步骤描述中的查询词；**重要**: 去掉"复现"、"跑一下"、"帮我"等中文动作前缀，只保留纯论文名或仓库名
   - fetch_tool 的 url 使用你记忆中该论文正确的 arXiv URL；注意 arXiv 搜索有时会返回错误的论文，请从历史记录中**筛选**出对的 arXiv ID
   - source_tool 只需要 paper_info 参数（论文标题/作者/摘要）。从历史记录中提取论文的标题、作者、摘要信息作为 paper_info，不要使用用户原始目标文本
3. 输出 JSON，只包含当前工具需要的参数，不要添加多余参数

输出 JSON:
{{"thought": "推理过程", "action": "", "action_args": {{"参数": "值"}}}}"""

    @staticmethod
    def _first_url(text: str) -> str:
        import re
        urls = re.findall(r'https?://[^\s<>",{}|\\^`\[\]]+', text)
        return urls[0] if urls else ""

    @staticmethod
    def _extract_paper_info_from_history(history: str) -> str:
        """Extract paper title, authors, and abstract from historical context.

        Scans the history string for patterns commonly found in paper search
        results (title, authors, abstract). Returns a concise paper_info string
        suitable for source_tool.
        """
        if not history:
            return ""
        import re
        lines = []
        # Look for "标题:" / "Title:" pattern
        title_match = re.search(r'(?:标题|Title)[：:]\s*(.+?)(?:\n|$)', history)
        if title_match:
            lines.append(f"Title: {title_match.group(1).strip()[:200]}")
        # Look for "作者:" / "Authors:" pattern
        author_match = re.search(r'(?:作者|Authors?)[：:]\s*(.+?)(?:\n|$)', history)
        if author_match:
            lines.append(f"Authors: {author_match.group(1).strip()[:300]}")
        # Look for "年份:" / "Year:" pattern
        year_match = re.search(r'(?:年份|Year)[：:]\s*(.+?)(?:\n|$)', history)
        if year_match:
            lines.append(f"Year: {year_match.group(1).strip()}")
        # Look for "摘要:" / "Abstract:" or the first sentence of the abstract
        abstract_match = re.search(r'(?:摘要|Abstract)[：:]\s*(.+?)(?:\n\n|$)', history, re.DOTALL)
        if abstract_match:
            abstract = abstract_match.group(1).strip()[:1000]
            lines.append(f"Abstract: {abstract}")
        if lines:
            return " | ".join(lines)
        return ""

    def _build_forced_step(self, step, force_tool: str, goal: str = "", history: str = "") -> ReActStep:
        """Build a ReAct step using the forced tool, no LLM needed.

        For deterministic tools, this bypasses the expensive LLM call entirely.
        Args are derived from step description and inter-step context.
        """
        args = self._default_args(step, force_tool, goal, history)
        # For python_env_tool, derive repo_path from history if available
        if force_tool == "python_env_tool" and not args.get("repo_path") and not args.get("repo_name"):
            url = self._first_url(history)
            if url:
                # Try to extract repo name from URL
                repo_name = url.rstrip("/").split("/")[-1]
                if repo_name.endswith(".git"):
                    repo_name = repo_name[:-4]
                if repo_name and not repo_name.startswith("http"):
                    args["repo_name"] = repo_name
        return ReActStep(
            thought=f"[计划步骤] 使用 {force_tool} 执行: {step.description}",
            action=force_tool,
            action_args=args,
        )

    def _default_args(self, step, tool_name: str, goal: str = "", history: str = "") -> dict:
        """Build default args for a tool based on step description."""
        import re
        desc = step.description.lower()
        if tool_name == "search_tool":
            is_repo_search = any(kw in desc or kw in goal.lower() for kw in ["github", "源码", "仓库", "repo"])
            return {"query": goal if goal else step.description,
                    "source": "llm" if is_repo_search else "arxiv"}
        elif tool_name == "fetch_tool":
            return {"url": self._first_url(history) if history else ""}
        elif tool_name == "source_tool":
            # Try to find paper info from history first (more informative than goal)
            paper_info = self._extract_paper_info_from_history(history) or goal
            return {"paper_info": paper_info}
        elif tool_name == "fetch_tool":
            # If history has a paper URL, use it; otherwise fall through to empty
            url = self._first_url(history) if history else ""
            return {"url": url}
        elif tool_name == "clone_tool":
            repo_url = self._first_url(history) if history else self._first_url(step.description)
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
        # --- Auxiliary tools ---
        elif tool_name == "view_report_tool":
            rid = re.search(r'(report_\w+)', step.description)
            return {"report_id": rid.group(1) if rid else ""}
        elif tool_name == "search_reports_tool":
            return {"query": step.description}
        elif tool_name == "list_reports_tool":
            return {}
        elif tool_name == "delete_report_tool":
            rid = re.search(r'(report_\w+)', step.description)
            return {"report_id": rid.group(1) if rid else ""}
        elif tool_name == "list_workspace_tool":
            return {}
        elif tool_name == "check_repo_tool":
            return {"repo_name": step.description}
        elif tool_name == "workspace_cleanup_tool":
            name_match = re.search(r'(?:仓库|repo|删除|remove)\s*[：:]*\s*([a-zA-Z0-9_.-]{2,40})', desc)
            return {"repo_name": name_match.group(1) if name_match else ""}
        elif tool_name == "config_tool":
            return {}
        elif tool_name == "stats_tool":
            return {}
        elif tool_name == "error_handler_tool":
            return {}
        elif tool_name == "execute_session_tool":
            return {}
        elif tool_name == "python_env_tool":
            # Determine action from step description.
            # IMPORTANT: Do NOT default repo_name/path here — that comes
            # from orchestrator._enrich_args which has the actual clone result.
            if "清理" in desc or "cleanup" in desc:
                return {"action": "cleanup"}
            if "查找" in desc or "find" in desc:
                return {"action": "find_python"}
            if "配置" in desc or "创建" in desc or "setup" in desc:
                return {"action": "setup"}
            return {"action": "recon"}
        elif tool_name == "cleanup_env_tool":
            if "所有" in desc or "全部" in desc or "all" in desc:
                return {"action": "clean_all"}
            return {"action": "remove_venv"}
        return {}

    def _fallback_decide(self, step, goal: str = "", history: str = "") -> ReActStep:
        import re
        if step.tool_hint:
            hint = step.tool_hint
            if hint == "search_tool":
                is_repo_search = any(kw in step.description.lower() or kw in goal.lower() for kw in ["github", "源码", "仓库", "repo"])
                args = {"query": goal if goal else step.description,
                        "source": "llm" if is_repo_search else "arxiv"}
            elif hint == "fetch_tool":
                args = {"url": self._first_url(history) if history else ""}
            elif hint == "source_tool":
                args = {"paper_info": goal if goal else step.description}
            elif hint == "clone_tool":
                args = {"repo_url": self._first_url(history) if history else self._first_url(step.description)}
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
            # --- Auxiliary tools ---
            elif hint == "view_report_tool":
                rid = re.search(r'(report_\w+)', step.description)
                args = {"report_id": rid.group(1) if rid else ""}
            elif hint == "search_reports_tool":
                args = {"query": step.description}
            elif hint == "list_reports_tool":
                args = {}
            elif hint == "delete_report_tool":
                rid = re.search(r'(report_\w+)', step.description)
                args = {"report_id": rid.group(1) if rid else ""}
            elif hint == "list_workspace_tool":
                args = {}
            elif hint == "check_repo_tool":
                args = {"repo_name": step.description}
            elif hint == "workspace_cleanup_tool":
                name_match = re.search(
                    r'(?:仓库|repo|删除|remove)\s*[：:]*\s*([a-zA-Z0-9_.-]{2,40})',
                    step.description.lower()
                )
                args = {"repo_name": name_match.group(1) if name_match else ""}
            elif hint == "config_tool":
                args = {}
            elif hint == "stats_tool":
                args = {}
            elif hint == "error_handler_tool":
                args = {}
            elif hint == "execute_session_tool":
                args = {}
            elif hint == "python_env_tool":
                desc_lower = step.description.lower()
                # Only set action — repo_name/path will be injected by
                # orchestrator._enrich_args from clone step context.
                if "清理" in desc_lower or "cleanup" in desc_lower:
                    args = {"action": "cleanup"}
                elif "查找" in desc_lower or "find" in desc_lower:
                    args = {"action": "find_python"}
                elif "配置" in desc_lower or "创建" in desc_lower or "setup" in desc_lower:
                    args = {"action": "setup"}
                else:
                    args = {"action": "recon"}
            elif hint == "cleanup_env_tool":
                desc_lower = step.description.lower()
                if "所有" in desc_lower or "全部" in desc_lower or "all" in desc_lower:
                    args = {"action": "clean_all"}
                else:
                    args = {"action": "remove_venv"}
            else:
                args = {}
            return ReActStep(
                thought=f"使用 {hint} 执行: {step.description}",
                action=hint,
                action_args=args,
            )
        desc = step.description.lower()
        if "搜索" in desc or "search" in desc:
            is_repo_search = any(kw in desc or kw in goal.lower() for kw in ["github", "源码", "仓库", "repo"])
            return ReActStep(thought=f"搜索: {step.description}", action="search_tool",
                             action_args={"query": goal if goal else step.description,
                                          "source": "llm" if is_repo_search else "arxiv"})
        elif "获取" in desc or "阅读" in desc or "fetch" in desc or "read" in desc:
            return ReActStep(thought=f"获取内容", action="fetch_tool",
                             action_args={"url": self._first_url(history) if history else ""})
        elif "源码" in desc or "source" in desc or "仓库" in desc or "repo" in desc:
            return ReActStep(thought=f"查找源码", action="source_tool",
                             action_args={"paper_info": goal if goal else step.description})
        elif "克隆" in desc or "clone" in desc:
            repo_url = self._first_url(history) if history else self._first_url(step.description)
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
        elif any(kw in desc for kw in ["环境侦察", "python 版本", "python_env"]):
            if "清理" in desc or "cleanup" in desc:
                return ReActStep(thought="清理虚拟环境", action="python_env_tool",
                                 action_args={"action": "cleanup"})
            return ReActStep(thought="环境侦察", action="python_env_tool",
                             action_args={"action": "recon"})
        elif any(kw in desc for kw in ["清理环境", "cleanup env", "cleanup_env"]):
            return ReActStep(thought="清理环境", action="cleanup_env_tool", action_args={})
        return ReActStep(thought=f"执行: {step.description}", action="idle")
