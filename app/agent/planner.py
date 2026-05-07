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
        self.status = status  # pending, active, done, failed
        self.depends_on = depends_on or []
        self.tool_hint = tool_hint
        self.expected_artifact = expected_artifact
        self.result: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id, "description": self.description,
            "status": self.status, "depends_on": self.depends_on,
            "tool_hint": self.tool_hint, "expected_artifact": self.expected_artifact,
            "result": self.result,
        }


class Plan:
    def __init__(self, goal: str, steps: List[PlanStep] = None):
        self.goal = goal
        self.steps = steps or []
        self.current_idx = 0
        self.status = "active"  # active, completed, failed

    def get_next_step(self) -> Optional[PlanStep]:
        for step in self.steps:
            if step.status == "pending":
                return step
        return None

    def mark_done(self, step_id: int, result: str = ""):
        for s in self.steps:
            if s.step_id == step_id:
                s.status = "done"
                s.result = result
                return

    def mark_failed(self, step_id: int, error: str = ""):
        for s in self.steps:
            if s.step_id == step_id:
                s.status = "failed"
                s.result = error
                return

    def is_complete(self) -> bool:
        return all(s.status in ("done", "failed") for s in self.steps)

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
    PlanStep(step_id=5, description="汇总报告：论文信息、源码地址与本地路径",
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
- 复现论文(完整) → 搜论文→读论文→找源码→克隆→报告
- 搜索/查询论文 → 搜论文→读论文→找源码→报告
- 直接克隆仓库 → 克隆→报告
- 简单问答 → 1步直接回答

重要:
- 每步都需要 tool_hint 指定工具名（search_tool/fetch_tool/source_tool/clone_tool）
- 最后一步始终是汇总报告（tool_hint为空字符串）
- 避免多余步骤，但至少要包含 执行步+报告步 两步
- 如果目标中已有URL（github.com等），直接使用而不要重新搜索
- 如果用户给仓库URL要查论文 → fetch_tool访问仓库页面→search_tool搜索论文→汇总报告

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
2. 考虑备选方案（如更换搜索源、直接访问已知论文网站等）
3. 保留已有的成功结果不重复

输出 JSON: {{"steps": [{{"step_id": 1, "description": "...", "tool_hint": "..."}}]}}"""

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
        new_steps = [
            PlanStep(step_id=len(kept) + 1,
                     description=f"重试: {failed.description}（使用备选方式）",
                     tool_hint=failed.tool_hint),
            PlanStep(step_id=len(kept) + 2, description="汇总已有结果并报告"),
        ]
        return Plan(goal=plan.goal, steps=kept + new_steps)
