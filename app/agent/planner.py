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


class Planner:
    def __init__(self):
        self._llm = get_llm()
        self._log = get_logger("planner")

    def create_plan(self, goal: str, context: str = "") -> Plan:
        self._log.info(f"Creating plan for: {goal[:80]}")
        if self._is_reproduction_goal(goal):
            plan = self._create_reproduction_plan(goal)
        else:
            plan = self._create_generic_plan(goal, context)
        return plan

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

    def _is_reproduction_goal(self, goal: str) -> bool:
        keywords = ["复现", "reproduce", "reproduction", "论文", "paper"]
        return any(kw in goal.lower() for kw in keywords)

    def _create_reproduction_plan(self, goal: str) -> Plan:
        return Plan(goal=goal, steps=[
            PlanStep(step_id=s.step_id, description=s.description,
                     tool_hint=s.tool_hint, expected_artifact=s.expected_artifact)
            for s in REPRODUCTION_PLAN
        ])

    def _create_generic_plan(self, goal: str, context: str) -> Plan:
        prompt = f"""你是任务规划器。请将以下目标分解为 3-5 个可执行步骤。

目标: {goal}
上下文: {context or "无"}

输出 JSON:
{{"steps": [{{"step_id": 1, "description": "...", "tool_hint": "..."}}]}}"""
        try:
            resp = self._llm.generate_structured(prompt)
            steps = self._parse_steps(resp.get("steps", []))
            return Plan(goal=goal, steps=steps)
        except Exception as e:
            self._log.error(f"LLM plan failed: {e}, using fallback")
            return Plan(goal=goal, steps=[
                PlanStep(step_id=1, description=f"分析目标: {goal}"),
                PlanStep(step_id=2, description="搜索相关信息"),
                PlanStep(step_id=3, description="执行并报告结果"),
            ])

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
