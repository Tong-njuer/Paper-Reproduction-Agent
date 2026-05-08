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
    PlanStep(step_id=5, description="阅读仓库源码（README/requirements等）并配置Python虚拟环境，安装依赖",
             tool_hint="setup_tool"),
    PlanStep(step_id=6, description="阅读仓库README与入口文件，分析项目结构、框架与预期输出",
             tool_hint="read_repo_tool"),
    PlanStep(step_id=7, description="根据仓库分析结果，确定精确的执行命令（脚本路径+参数）",
             tool_hint="plan_run_tool"),
    PlanStep(step_id=8, description="在虚拟环境中执行复现命令，捕获stdout/stderr输出",
             tool_hint="run_tool"),
    PlanStep(step_id=9, description="汇总报告：论文信息、源码地址、本地路径、环境配置与执行结果",
             tool_hint=""),
]

SETUP_ONLY_PLAN = [
    PlanStep(step_id=1, description="阅读仓库源码（README、requirements等），确定复现目标，创建venv并安装依赖",
             tool_hint="setup_tool"),
    PlanStep(step_id=2, description="汇总报告：环境配置结果与复现目标",
             tool_hint=""),
]

EXECUTE_ONLY_PLAN = [
    PlanStep(step_id=1, description="阅读仓库README与入口文件，分析项目结构、框架与预期输出",
             tool_hint="read_repo_tool"),
    PlanStep(step_id=2, description="根据仓库分析结果，确定精确的执行命令（脚本路径+参数）",
             tool_hint="plan_run_tool"),
    PlanStep(step_id=3, description="在虚拟环境中执行复现命令，捕获stdout/stderr输出",
             tool_hint="run_tool"),
    PlanStep(step_id=4, description="汇总报告：执行结果与项目信息",
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
        try:
            plan = self._llm_plan(goal, context)
            if plan and plan.steps:
                self._log.info(f"LLM plan: {len(plan.steps)} steps")
                return plan
        except Exception as e:
            self._log.warning(f"LLM planning failed: {e}, using fallback")
        return self._fallback_plan(goal)

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
- 给仓库URL找对应论文 → 访问仓库页面→提取论文链接→搜索论文→报告
- 给论文信息找源码 → 搜论文→读论文→找源码→报告
- 复现论文(完整) → 搜论文→读论文→找源码→克隆→配置环境→阅读仓库→规划命令→执行→报告
- 搜索/查询论文 → 搜论文→读论文→找源码→报告
- 直接克隆仓库 → 克隆→报告
- 配置环境（指定仓库或workspace中已有仓库）→ 阅读源码+创建venv+安装依赖→报告
- 执行/运行（workspace中已有仓库且环境已配好）→ 阅读仓库→规划命令→执行→报告
- 简单问答 → 1步直接回答

重要:
- 每步都需要 tool_hint 指定工具名（search_tool/fetch_tool/source_tool/clone_tool/setup_tool/read_repo_tool/plan_run_tool/run_tool/execute_tool）
- 最后一步始终是汇总报告（tool_hint为空字符串）
- 避免多余步骤，但至少要包含 执行步+报告步 两步
- 如果目标中已有URL（github.com等），直接使用而不要重新搜索
- 如果用户给仓库URL要查论文 → fetch_tool访问仓库页面→search_tool搜索论文→汇总报告
- 如果用户是"配置环境"且未指定仓库名，用setup_tool自动检测workspace中的仓库
- 执行/运行类的目标应拆为三步: read_repo_tool(分析仓库) → plan_run_tool(确定命令) → run_tool(执行)
- execute_tool 是旧版一体化执行工具，新计划请优先使用 read_repo_tool+plan_run_tool+run_tool

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

        # Repo URL + paper intent → fetch repo page first, then search paper
        if self._has_repo_url(goal) and self._has_paper_intent(lower):
            return self._create_repo_to_paper_plan(goal)

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

        # Full reproduction
        if any(kw in lower for kw in ["复现", "reproduce", "复刻"]):
            return Plan(goal=goal, steps=[
                PlanStep(step_id=s.step_id, description=s.description,
                         tool_hint=s.tool_hint, expected_artifact=s.expected_artifact)
                for s in FULL_REPRODUCTION_PLAN
            ])

        # Search / query
        if any(kw in lower for kw in ["搜索", "search", "查询", "query",
                                       "找", "论文", "paper", "克隆", "clone"]):
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
   - 缺少Python包/模块 → setup_tool (安装依赖)
   - 需要分析仓库 → read_repo_tool
   - 需要确定执行命令 → plan_run_tool
   - 需要执行脚本 → run_tool
   - 需要查找信息 → search_tool (仅用于学术论文搜索)
   - 不要用 search_tool 搜索安装方法或验证文件
4. **不要重复已完成的工作** (如已克隆的仓库不要再克隆)
5. **最后一步必须是无 tool_hint 的汇总报告步骤**

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
