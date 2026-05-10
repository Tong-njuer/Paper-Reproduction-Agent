from typing import Dict, Any, List, Optional

from app.core.llm import get_llm
from app.core.logging import get_logger
from app.tools import list_available_tools


class PlanStep:
    def __init__(self, step_id: int, description: str, status: str = "pending",
                 depends_on: List[int] = None, tool_hint: str = "",
                 expected_artifact: str = ""):
        self.step_id = step_id
        self.description = description
        self.status = status  # pending, active, done, failed, skipped
        self.depends_on = depends_on or []
        self.tool_hint = tool_hint
        self.expected_artifact = expected_artifact
        self.result: Optional[str] = None
        self.retry_count: int = 0
        self.max_retries: int = 3

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id, "description": self.description,
            "status": self.status, "depends_on": self.depends_on,
            "tool_hint": self.tool_hint, "expected_artifact": self.expected_artifact,
            "result": self.result,
            "retry_count": self.retry_count,
        }


class Plan:
    def __init__(self, goal: str, steps: List[PlanStep] = None):
        self.goal = goal
        self.steps = steps or []
        self.current_idx = 0
        self.status = "active"  # active, completed, failed

    def get_next_step(self, allow_retry: bool = True) -> Optional[PlanStep]:
        # First, return any pending step (including retried ones)
        for step in self.steps:
            if step.status == "pending":
                return step
        # If allowing retry, return a failed step that still has retries left
        if allow_retry:
            for step in self.steps:
                if step.status == "failed" and step.retry_count < step.max_retries:
                    return step
        return None

    def mark_done(self, step_id: int, result: str = ""):
        for s in self.steps:
            if s.step_id == step_id:
                s.status = "done"
                s.result = result
                s.retry_count = 0
                return

    def mark_failed(self, step_id: int, error: str = ""):
        for s in self.steps:
            if s.step_id == step_id:
                s.status = "failed"
                s.result = error
                s.retry_count += 1
                return

    def retry_step(self, step_id: int):
        """Reset a failed step back to pending for in-place retry (only if failed)."""
        for s in self.steps:
            if s.step_id == step_id and s.status == "failed" and s.retry_count < s.max_retries:
                s.status = "pending"
                return True
        return False

    def skip_step(self, step_id: int, reason: str = ""):
        """Mark a step as skipped (max retries exhausted, non-critical)."""
        for s in self.steps:
            if s.step_id == step_id:
                s.status = "skipped"
                s.result = reason or "Max retries exhausted"
                return

    def has_step(self, tool_hint: str) -> bool:
        """Check if any step has the given tool_hint."""
        return any(s.tool_hint == tool_hint for s in self.steps)

    def is_complete(self) -> bool:
        return all(s.status in ("done", "failed", "skipped") for s in self.steps)

    def completed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == "done")

    def to_dict(self) -> dict:
        return {
            "goal": self.goal, "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
        }


REPRODUCTION_PLAN = [
    PlanStep(step_id=1, description="搜索论文，获取论文标题、作者、摘要和链接",
             tool_hint="search_tool"),
    PlanStep(step_id=2, description="获取并阅读论文全文内容，提取关键信息（方法、实验、代码链接）",
             tool_hint="fetch_tool"),
    PlanStep(step_id=3, description="从论文内容和引用中查找源码仓库地址",
             tool_hint="source_tool"),
    PlanStep(step_id=4, description="汇总报告：论文信息与源码地址",
             tool_hint=""),
]

FULL_REPRODUCTION_PLAN = [
    PlanStep(step_id=1, description="搜索论文，获取论文标题、作者、摘要和链接",
             tool_hint="search_tool"),
    PlanStep(step_id=2, description="获取并阅读论文全文内容，提取关键信息（方法、实验、代码链接）",
             tool_hint="fetch_tool"),
    PlanStep(step_id=3, description="从论文内容和引用中查找源码仓库地址",
             tool_hint="source_tool"),
    PlanStep(step_id=4, description="克隆源码仓库到本地工作区",
             tool_hint="clone_tool"),
    PlanStep(step_id=5, description="对话式配置与执行：LLM创建venv、安装依赖、运行项目，观察输出、诊断错误、修复问题，直到成功或确认无法运行",
             tool_hint="execute_session_tool"),
    PlanStep(step_id=6, description="汇总报告：论文信息、源码地址、本地路径、环境配置与执行结果",
             tool_hint=""),
]

SETUP_ONLY_PLAN = [
    PlanStep(step_id=1, description="对话式配置与执行：LLM创建venv、安装依赖、运行项目，观察输出、诊断错误、修复问题，直到成功或确认无法运行",
             tool_hint="execute_session_tool"),
    PlanStep(step_id=2, description="汇总报告：环境配置结果与执行结果",
             tool_hint=""),
]

EXECUTE_ONLY_PLAN = [
    PlanStep(step_id=1, description="对话式配置与执行：LLM创建venv、安装依赖、运行项目，观察输出、诊断错误、修复问题，直到成功或确认无法运行",
             tool_hint="execute_session_tool"),
    PlanStep(step_id=2, description="汇总报告：执行结果与项目信息",
             tool_hint=""),
]

REPO_REPRODUCTION_PLAN = [
    PlanStep(step_id=1, description="搜索目标仓库，获取GitHub仓库URL与基本信息",
             tool_hint="search_tool"),
    PlanStep(step_id=2, description="克隆源码仓库到本地工作区",
             tool_hint="clone_tool"),
    PlanStep(step_id=3, description="对话式配置与执行：LLM创建venv、安装依赖、运行项目，观察输出、诊断错误、修复问题，直到成功或确认无法运行",
             tool_hint="execute_session_tool"),
    PlanStep(step_id=4, description="汇总报告：项目信息、源码地址、本地路径、环境配置与执行结果",
             tool_hint=""),
]


class Planner:
    def __init__(self):
        self._llm = get_llm()
        self._log = get_logger("planner")

    # ------------------------------------------------------------------
    # Primary: LLM-driven planning
    # ------------------------------------------------------------------

    def create_plan(self, goal: str, context: str = "") -> Plan:
        self._log.info(f"Creating plan for: {goal[:80]}")
        # Try keyword-based deterministic matching first.
        # If it returns a specific plan (one with real tool_hint assignments),
        # use it directly — don't let the LLM override with a wrong plan.
        fallback = self._fallback_plan(goal)
        if fallback and fallback.steps and self._is_specific_plan(fallback):
            self._log.info(f"Keyword-matched plan: {len(fallback.steps)} steps")
            return fallback

        # Ambiguous intent — let LLM create the plan.
        try:
            plan = self._llm_plan(goal, context)
            if plan and plan.steps:
                self._log.info(f"LLM plan: {len(plan.steps)} steps")
                return plan
        except Exception as e:
            self._log.warning(f"LLM planning failed: {e}, using fallback")
        return fallback

    @staticmethod
    def _is_specific_plan(plan) -> bool:
        """Return True if the plan has concrete tool assignments (not a generic fallback)."""
        if not plan or not plan.steps:
            return False
        for s in plan.steps:
            if s.tool_hint and s.tool_hint not in ("", "report", "report_tool"):
                return True
        return False

    def _llm_plan(self, goal: str, context: str) -> Plan:
        tools_desc = "\n".join(
            f"- {n}: {d}" for n, d in list_available_tools().items()
        )
        prompt = f"""你是任务规划器。分析用户意图，创建最精简的执行计划。

用户目标: {goal}
上下文: {context or "无"}

可用工具:
{tools_desc}

根据用户意图选择计划模式:

## 核心复现流程
- 给仓库URL找对应论文 → 访问仓库页面→提取论文链接→搜索论文→报告
- 给论文信息找源码 → 搜论文→读论文→找源码→报告
- 复现论文(完整) → 搜论文→读论文→找源码→克隆→execute_session_tool配置与执行→报告
- 复现指定项目/仓库 → search_tool搜索仓库URL→clone_tool克隆→execute_session_tool配置与执行→报告
- 复现<仓库URL> → clone_tool克隆→execute_session_tool配置与执行→报告
- 搜索/查询论文 → 搜论文→读论文→找源码→报告
- 直接克隆仓库 → 克隆→报告

## 辅助工具（单步完成，无需多步计划）
- 列出/查看工作区中的仓库 → 单步: list_workspace_tool
- 列出/查看历史报告 → 单步: list_reports_tool
- 查看某份具体报告（如"查看报告 report_xxx"） → 单步: view_report_tool
- 搜索历史报告（如"找一下关于ML-From-Scratch的报告"、"搜索报告xxx"） → 单步: search_reports_tool
- 删除某份报告 → 单步: delete_report_tool
- 检查/分析某个仓库状态 → 单步: check_repo_tool
- 清理工作区/删除仓库/释放空间 → 单步: workspace_cleanup_tool
- 查看当前配置/设置 → 单步: config_tool
- 查看系统统计/成功率 → 单步: stats_tool
- 列出工作区+查看统计 → 两步: list_workspace_tool → stats_tool

**关键判断**: 如果用户目标是「查询/管理已保存的报告」或「查看工作区/仓库状态」或「查看配置/统计」，这些都是辅助查询，用单步对应工具即可。

规划优先级（从高到低）:
1. 用户明确说"复现"/"reproduce" → 必须用核心复现流程（至少: clone→execute_session_tool→报告）
2. 用户只要求"配置环境"/"执行"/"跑一下"（已知仓库存在）→ 单步 execute_session_tool
3. 用户要求"搜索论文"/"找论文" → 搜论文→读论文→找源码→报告
4. 辅助查询/管理 → 单步对应工具

重要:
- 每步都需要 tool_hint 指定工具名
- 辅助查询工具单步即可，最后不需要汇总报告步骤
- 核心复现流程最后一步始终是汇总报告（tool_hint为空字符串）
- "复现"意图必须包含 clone_tool + execute_session_tool，不能缩减为单步
- 如果目标中已有URL，clone步骤直接使用该URL
- setup_tool、read_repo_tool、plan_run_tool、run_tool、execute_tool 是旧版工具，已弃用，不要使用

输出 JSON:
{{"steps": [{{"step_id": 1, "description": "...", "tool_hint": "search_tool"}}]}}"""
        resp = self._llm.generate_structured(prompt)
        steps = self._parse_steps(resp.get("steps", []))
        return Plan(goal=goal, steps=steps) if steps else None

    # ------------------------------------------------------------------
    # Fallback: keyword-based (deterministic, no LLM call)
    # ------------------------------------------------------------------

    def _fallback_plan(self, goal: str) -> Plan:
        lower = goal.lower()

        # ------------------------------------------------------------------
        # Auxiliary tools (simple single-step queries) — detect BEFORE generic
        # keywords so "找报告" doesn't become a paper search.
        # ------------------------------------------------------------------
        aux = self._detect_auxiliary_intent(lower)
        if aux:
            tool_name, desc = aux
            return Plan(goal=goal, steps=[
                PlanStep(step_id=1, description=desc, tool_hint=tool_name),
            ])

        # Repo URL + paper intent → fetch repo page first, then search paper
        if self._has_repo_url(goal) and self._has_paper_intent(lower):
            return self._create_repo_to_paper_plan(goal)

        # Reproduction — distinguish "复现论文" from "复现项目/仓库"
        if any(kw in lower for kw in ["复现", "reproduce", "复刻"]):
            if self._has_paper_intent(lower):
                return Plan(goal=goal, steps=[
                    PlanStep(step_id=s.step_id, description=s.description,
                             tool_hint=s.tool_hint, expected_artifact=s.expected_artifact)
                    for s in FULL_REPRODUCTION_PLAN
                ])
            elif self._has_repo_url(goal):
                return Plan(goal=goal, steps=[
                    PlanStep(step_id=1, description="克隆源码仓库到本地工作区",
                             tool_hint="clone_tool"),
                    PlanStep(step_id=2, description="对话式配置与执行：LLM创建venv、安装依赖、运行项目",
                             tool_hint="execute_session_tool"),
                    PlanStep(step_id=3, description="汇总报告：项目信息、源码地址、环境配置与执行结果",
                             tool_hint=""),
                ])
            else:
                return Plan(goal=goal, steps=[
                    PlanStep(step_id=s.step_id, description=s.description,
                             tool_hint=s.tool_hint, expected_artifact=s.expected_artifact)
                    for s in REPO_REPRODUCTION_PLAN
                ])

        # Repo URL → direct clone
        if self._has_repo_url(goal):
            return Plan(goal=goal, steps=[
                PlanStep(step_id=1, description="克隆源码仓库到本地工作区",
                         tool_hint="clone_tool"),
                PlanStep(step_id=2, description="验证克隆结果并报告本地路径",
                         tool_hint=""),
            ])

        # Setup / configure environment (standalone)
        if self._has_setup_intent(lower):
            return Plan(goal=goal, steps=[
                PlanStep(step_id=s.step_id, description=s.description,
                         tool_hint=s.tool_hint, expected_artifact=s.expected_artifact)
                for s in SETUP_ONLY_PLAN
            ])

        # Execute / run (standalone — workspace already has repo + venv)
        if self._has_execute_intent(lower):
            return Plan(goal=goal, steps=[
                PlanStep(step_id=s.step_id, description=s.description,
                         tool_hint=s.tool_hint, expected_artifact=s.expected_artifact)
                for s in EXECUTE_ONLY_PLAN
            ])

        # Search / query — only match when it's NOT about reports (aux tools handle reports)
        if any(kw in lower for kw in ["搜索论文", "search paper", "查询论文",
                                       "找论文", "paper", "arxiv"]):
            return Plan(goal=goal, steps=[
                PlanStep(step_id=s.step_id, description=s.description,
                         tool_hint=s.tool_hint, expected_artifact=s.expected_artifact)
                for s in REPRODUCTION_PLAN
            ])
        if any(kw in lower for kw in ["克隆", "clone"]):
            return Plan(goal=goal, steps=[
                PlanStep(step_id=s.step_id, description=s.description,
                         tool_hint=s.tool_hint, expected_artifact=s.expected_artifact)
                for s in REPRODUCTION_PLAN
            ])

        # Generic
        return Plan(goal=goal, steps=[
            PlanStep(step_id=1, description=f"分析并执行: {goal[:80]}"),
            PlanStep(step_id=2, description="汇总并报告结果"),
        ])

    def _has_repo_url(self, goal: str) -> bool:
        import re
        return bool(re.search(
            r'https?://(github|gitlab|bitbucket|gitee|huggingface)\.com/[\w.-]+/[\w.-]+',
            goal
        ))

    @staticmethod
    def _has_setup_intent(lower: str) -> bool:
        # Direct keyword matches
        if any(kw in lower for kw in [
            "配置环境", "setup environment", "环境配置",
            "安装依赖", "配置依赖", "setup env",
        ]):
            return True
        # "配置" + "环境" appearing anywhere in the message
        if "配置" in lower and "环境" in lower:
            return True
        # "setup" or "configure" + "env" in English
        if any(kw in lower for kw in ["setup", "configure"]) and \
           any(kw in lower for kw in ["env", "environment", "依赖", "环境"]):
            return True
        return False

    @staticmethod
    def _has_execute_intent(lower: str) -> bool:
        """Detect standalone execution intent (repo + venv already exist)."""
        import re
        exec_kw = [
            "执行", "运行", "execute", "run script", "run the",
            "复现执行", "跑一下", "跑一遍", "跑起来",
            "exec ", "executing", "running",
        ]
        if any(kw in lower for kw in exec_kw):
            return True
        # Broader regex: run/running + target, exec + target, 执行/运行
        if re.search(
            r'\b(?:run(?:ning)?|exec(?:ute)?)\s+(?:the\s+)?'
            r'(?:script|code|model|demo|train|eval|repo|project|复现)',
            lower
        ):
            return True
        if re.search(r'\b(?:运行|执行)(?:复现|脚本|模型)?', lower):
            return True
        return False

    @staticmethod
    def _has_paper_intent(lower: str) -> bool:
        return any(kw in lower for kw in [
            "论文", "paper", "原文", "文章", "arxiv", "文献", "doi",
        ])

    @staticmethod
    def _detect_auxiliary_intent(lower: str) -> tuple:
        """Detect auxiliary/simple-query intents. Returns (tool_name, description) or None."""
        import re

        # --- Report management ---
        # "搜索报告" / "找一下关于X的报告" / "search report"
        if any(kw in lower for kw in ["搜索报告", "查找报告", "搜报告",
                                       "search report", "find report"]) \
                or re.search(r'找.*报告|关于.*报告|搜.*报告', lower):
            # Try to extract a search query from the goal
            query_match = re.search(
                r'(?:关于|about|搜索|查找|搜|找).{0,5}?[报告|report].{0,3}?[：:\s]*([^\s，,。.]{2,40})',
                lower
            )
            if not query_match:
                # Also try: "找一下 X 的报告" / "关于 X 的报告"
                query_match = re.search(
                    r'(?:关于|about)\s*([^\s，,。.]{2,40})',
                    lower
                )
            if query_match:
                query = query_match.group(1).strip()
                return ("search_reports_tool", f"搜索历史报告中与 '{query}' 相关的记录")
            return ("list_reports_tool", "列出所有已保存的历史报告")

        # "列出报告" / "有哪些报告" / "报告列表"
        if any(phrase in lower for phrase in [
            "列出报告", "报告列表", "有哪些报告", "查看报告列表",
            "历史报告", "已保存的报告", "所有报告",
            "list report", "view reports", "all reports",
        ]):
            return ("list_reports_tool", "列出所有已保存的历史报告")

        # "查看报告 <id>" / "查看某份报告" / "查看 X 报告"
        # Strategy: first try to find a report_ ID anywhere in the message.
        # If found, route to view_report_tool for the full report content.
        id_match = re.search(r'(report_\w+)', lower)
        if id_match and any(kw in lower for kw in ["查看", "view", "打开", "看", "显示"]):
            rid = id_match.group(1)
            return ("view_report_tool", f"查看报告 {rid} 的完整内容")

        # Match "查看<name>报告" / "查看<name>的报告" — search by goal name
        view_match = re.search(
            r'(?:查看|view|打开|看|显示)\s*([^\s，,。]{2,40})\s*(?:的|的)?报告',
            lower
        )
        if view_match:
            name = view_match.group(1).strip()
            # Strip trailing noise: 的, 详细, 完整, 最新
            name = re.sub(r'[的之](?:详细|完整|全部|最新|最近)?$', '', name)
            # Filter out noise words that aren't real report names
            if name and name not in ("一下", "一个", "这个", "那个", "全部", "所有",
                                      "历史", "完整", "最新", "最近"):
                # If the cleaned name looks like a report ID, view directly
                if re.match(r'^report_\w+', name):
                    return ("view_report_tool", f"查看报告 {name} 的完整内容")
                return ("search_reports_tool", f"搜索与 '{name}' 相关的历史报告")

        # "删除报告 <id>"
        if any(kw in lower for kw in ["删除报告", "删掉报告", "delete report"]):
            id_match = re.search(r'(report_\w+)', lower)
            if id_match:
                rid = id_match.group(1)
                return ("delete_report_tool", f"删除报告 {rid}")
            return ("list_reports_tool", "列出报告以便选择要删除的报告")

        # --- Workspace management ---
        # "列出工作区" / "查看工作区" / "工作区里有什么"
        if any(phrase in lower for phrase in [
            "列出工作区", "查看工作区", "工作区里有什么", "工作区有什么",
            "有哪些仓库", "仓库列表", "列出仓库", "查看仓库列表",
            "list workspace", "view workspace", "what's in workspace",
        ]):
            return ("list_workspace_tool", "列出工作区中所有已克隆的仓库及状态")

        # "检查仓库" / "查看仓库状态" / "分析仓库"
        if any(kw in lower for kw in [
            "检查仓库", "查看仓库", "分析仓库", "仓库状态",
            "仓库详情", "仓库信息",
            "check repo", "inspect repo", "repo status", "repo info",
        ]):
            # Try to extract repo name
            name_match = re.search(
                r'(?:仓库|repo|检查|查看|分析|状态)\s*[：:]*\s*([a-zA-Z0-9_.-]{2,40})',
                lower
            )
            if name_match:
                name = name_match.group(1)
                return ("check_repo_tool", f"深度检查仓库 {name} 的状态")
            return ("check_repo_tool", "检查工作区中唯一仓库的状态")

        # "清理工作区" / "删除仓库" / "释放空间"
        if any(kw in lower for kw in [
            "清理工作区", "删除仓库", "释放空间", "清空工作区",
            "clean workspace", "cleanup", "remove repo", "free space",
        ]):
            # Try to extract repo name
            name_match = re.search(
                r'(?:仓库|repo|删除|remove)\s*[：:]*\s*([a-zA-Z0-9_.-]{2,40})',
                lower
            )
            if name_match:
                name = name_match.group(1)
                return ("workspace_cleanup_tool", f"从工作区删除仓库 {name}")
            return ("workspace_cleanup_tool", "查看工作区仓库及磁盘占用，选择清理目标")

        # --- System info ---
        # "查看配置" / "系统配置" / "当前设置"
        if any(phrase in lower for phrase in [
            "查看配置", "系统配置", "当前配置", "当前设置",
            "什么配置", "配置是什么", "用的什么模型",
            "view config", "show config", "current config",
            "settings", "configuration",
        ]):
            return ("config_tool", "查看当前Agent系统的全部配置")

        # "查看统计" / "系统状态" / "成功率" / "统计数据"
        if any(phrase in lower for phrase in [
            "查看统计", "统计信息", "系统统计", "统计数据",
            "成功率", "系统状态", "运行统计",
            "view stats", "show stats", "statistics",
            "dashboard", "系统概览",
        ]):
            return ("stats_tool", "查看Agent系统统计数据（报告数、成功率、常见错误等）")

        return None

    def _create_repo_to_paper_plan(self, goal: str) -> Plan:
        """User gave a repo URL and wants to find the associated paper."""
        return Plan(goal=goal, steps=[
            PlanStep(step_id=1, description="访问仓库页面，从README/文档中提取论文链接",
                     tool_hint="fetch_tool"),
            PlanStep(step_id=2, description="根据提取的论文链接获取论文详细信息",
                     tool_hint="search_tool"),
            PlanStep(step_id=3, description="汇总报告：仓库信息与对应论文",
                     tool_hint=""),
        ])

    # ------------------------------------------------------------------
    # Replanning
    # ------------------------------------------------------------------

    def replan(self, plan: Plan, failed_step: PlanStep, error: str) -> Plan:
        self._log.info(f"Replanning after step {failed_step.step_id} failed: {error[:80]}")
        try:
            prompt = self._build_replan_prompt(plan, failed_step, error)
            resp = self._llm.generate_structured(prompt)
            new_steps = self._parse_steps(resp.get("steps", []))
            kept = [s for s in plan.steps if s.status == "done"]
            new_plan = Plan(goal=plan.goal, steps=kept + new_steps)
            self._log.info(f"Replan result: kept={len(kept)}, new={len(new_steps)}")
            return new_plan
        except Exception as e:
            self._log.error(f"Replan failed: {e}, using fallback")
            return self._fallback_replan(plan, failed_step, error)

    def _build_replan_prompt(self, plan: Plan, failed: PlanStep, error: str) -> str:
        done = [s for s in plan.steps if s.status == "done"]
        pending = [s for s in plan.steps if s.status == "pending"]
        return f"""当前计划执行中步骤 {failed.step_id} 失败。

原始目标: {plan.goal}
已完成步骤: {', '.join(f'{s.step_id}:{s.description}' for s in done) if done else '无'}
失败步骤: {failed.step_id}: {failed.description}
错误: {error}

请生成替代步骤，注意:
1. 分析失败原因并调整策略
2. 保留已有的成功结果不重复
3. **工具选择必须匹配任务类型**:
   - 需要克隆仓库 → clone_tool (repo_url 必须从历史记录中已找到的URL获取，绝不能编造)
   - 需要配置环境/安装依赖/执行脚本 → execute_session_tool (对话式配置与执行，LLM自主创建venv、安装依赖、诊断pip错误、运行项目)
   - 需要查找信息 → search_tool (仅用于学术论文搜索)
   - 不要用 search_tool 搜索安装方法或验证文件
   - setup_tool、read_repo_tool、plan_run_tool、run_tool 是旧版工具，已弃用
4. **失败的步骤必须重新尝试，不能跳过**: 如果 clone_tool 失败，替代方案中必须包含 clone_tool 重试（使用正确的URL），不能在仓库不存在的情况下跳到 setup_tool 或 run_tool
5. **不要重复已成功的工作** — 已克隆成功的仓库不要再次克隆；未成功的则必须重试
6. **最后一步必须是无 tool_hint 的汇总报告步骤**

输出 JSON: {{"steps": [{{"step_id": 1, "description": "...", "tool_hint": "setup_tool"}}]}}"""

    def _parse_steps(self, items: List[dict]) -> List[PlanStep]:
        steps = []
        for item in items:
            steps.append(PlanStep(
                step_id=item.get("step_id", len(steps) + 1),
                description=item.get("description", "No description"),
                tool_hint=item.get("tool_hint", ""),
                expected_artifact=item.get("expected_artifact", ""),
            ))
        return steps

    def _fallback_replan(self, plan: Plan, failed: PlanStep, error: str) -> Plan:
        kept = [s for s in plan.steps if s.status == "done"]
        next_id = len(kept) + 1
        new_steps = [
            PlanStep(step_id=next_id,
                     description=f"重试: {failed.description}（使用备选方式）",
                     tool_hint=failed.tool_hint),
            PlanStep(step_id=next_id + 1,
                     description="汇总报告：当前所有步骤结果",
                     tool_hint=""),
        ]
        return Plan(goal=plan.goal, steps=kept + new_steps)
