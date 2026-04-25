# ============================================================
# 规划器模块
# ============================================================
# 负责将高层目标分解为可执行的子任务。
# 支持基于执行反馈的动态重新规划。
#
# Console Output:
#   - Plan generation
#   - Plan updates and replanning
#   - Step details
# ============================================================

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.core.llm import get_llm
from app.core.context import ExecutionContext


class PlanStep(BaseModel):
    """
    计划中的单个步骤。

    Attributes:
        step_id: 此步骤的唯一标识符
        description: 人类可读的描述
        status: 当前状态（pending, in_progress, completed, failed, skipped）
        depends_on: 此步骤依赖的 step_id 列表
        result: 执行结果（如果完成）
    """
    step_id: int
    description: str
    status: str = "pending"
    depends_on: List[int] = Field(default_factory=list)
    result: Optional[str] = None
    tool_hint: Optional[str] = None
    expected_artifact: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    fallback_strategy: Optional[str] = None


class Plan(BaseModel):
    """
    包含多个步骤的计划。

    Attributes:
        goal: 此计划针对的原始目标
        steps: 计划步骤列表
        current_step_index: 下一个要执行的步骤索引
        status: 总体计划状态
        needs_replan: 是否建议重新规划
    """
    goal: str
    steps: List[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    status: str = "initialized"
    needs_replan: bool = False
    replan_reason: Optional[str] = None

    def get_next_step(self) -> Optional[PlanStep]:
        """
        获取下一个要执行的待处理步骤。

        Returns:
            PlanStep 或 None（如果没有待处理步骤）
        """
        for step in self.steps:
            if step.status == "pending":
                return step
        return None

    def mark_step_complete(self, step_id: int, result: str) -> None:
        """
        将步骤标记为完成。

        Args:
            step_id: 要标记的步骤 ID
            result: 执行结果
        """
        for step in self.steps:
            if step.step_id == step_id:
                step.status = "completed"
                step.result = result
                break

    def mark_step_failed(self, step_id: int, error: str) -> None:
        """
        将步骤标记为失败。

        Args:
            step_id: 失败步骤的 ID
            error: 错误消息
        """
        for step in self.steps:
            if step.step_id == step_id:
                step.status = "failed"
                step.result = error
                break
        self.needs_replan = True
        self.replan_reason = f"Step {step_id} failed: {error}"

    def is_complete(self) -> bool:
        """
        检查所有步骤是否完成。

        Returns:
            bool: 所有步骤是否完成
        """
        return all(step.status in ("completed", "skipped", "failed") for step in self.steps)

    def print_plan(self) -> None:
        """
        Print the current plan to console.
        """
        print("\n" + "-" * 50)
        print(f"[INFO] Plan for: {self.goal[:60]}...")
        print("-" * 50)

        for step in self.steps:
            # Status icon
            icons = {
                "pending": "[WAIT]",
                "in_progress": "[RETRY]",
                "completed": "[OK]",
                "failed": "[X]",
                "skipped": "[SKIP]",
            }
            icon = icons.get(step.status, "[?]")

            # Indent based on depth
            indent = "  " if step.depends_on else ""

            print(f"{icon} {indent}Step {step.step_id}: {step.description}")

            if step.tool_hint:
                print(f"   {indent}Tool Hint: {step.tool_hint}")
            if step.expected_artifact:
                print(f"   {indent}Expected Artifact: {step.expected_artifact}")
            if step.acceptance_criteria:
                print(f"   {indent}Acceptance: {step.acceptance_criteria[:80]}...")

            if step.result:
                print(f"   {indent}Result: {step.result[:50]}...")

        if self.needs_replan:
            print(f"\n[!]  Replanning needed: {self.replan_reason}")

        print("-" * 50 + "\n")


class Planner:
    """
    规划器模块，用于目标分解。

    使用 LLM 将高层目标分解为可执行的步骤。

    Attributes:
        llm: 用于生成计划的 LLM 接口
    """

    def __init__(self):
        """Initialize the Planner."""
        self.llm = get_llm()
        print("[BRAIN] Planner initialized")

    def create_plan(self, goal: str, context: Optional[ExecutionContext] = None) -> Plan:
        """
        为给定目标创建新计划。

        Args:
            goal: 要计划的高层目标
            context: 额外的上下文（可选）

        Returns:
            Plan: 生成的计划
        """
        print(f"\n[NOTE] Planner: Creating plan for goal: {goal[:80]}...")

        # Build prompt for plan generation
        prompt = self._build_plan_prompt(goal, context)

        # Generate plan using LLM
        if self.llm.is_available():
            try:
                response = self.llm.generate_structured(prompt)
                steps = self._parse_plan_response(response)
            except Exception as e:
                print(f"[!]  LLM plan generation failed: {e}, using fallback")
                steps = self._create_fallback_plan(goal)
        else:
            # Demo mode - create simple plan
            steps = self._create_demo_plan(goal)

        plan = Plan(goal=goal, steps=steps)
        plan.print_plan()

        return plan

    def replan(self, plan: Plan, reason: str, context: ExecutionContext) -> Plan:
        """
        基于执行反馈创建新计划。

        Args:
            plan: 当前计划
            reason: 需要重新规划的原因
            context: 当前执行上下文

        Returns:
            Plan: 新的修订计划
        """
        print(f"\n[RETRY] Planner: Replanning due to: {reason}")
        print(f"   Completed steps: {len([s for s in plan.steps if s.status == 'completed'])}")
        print(f"   Failed steps: {len([s for s in plan.steps if s.status == 'failed'])}")

        # Build prompt for replanning
        prompt = self._build_replan_prompt(plan, reason, context)

        # Generate new plan
        if self.llm.is_available():
            try:
                response = self.llm.generate_structured(prompt)
                new_steps = self._parse_plan_response(response)
            except Exception as e:
                print(f"[!]  LLM replan failed: {e}, using fallback")
                new_steps = self._create_recovery_plan(plan, reason)
        else:
            new_steps = self._create_recovery_plan(plan, reason)

        # Keep completed steps, replace remaining
        completed_steps = [s for s in plan.steps if s.status == "completed"]
        new_plan = Plan(
            goal=plan.goal,
            steps=completed_steps + new_steps,
            current_step_index=len(completed_steps),
        )

        new_plan.print_plan()
        return new_plan

    def _build_plan_prompt(self, goal: str, context: Optional[ExecutionContext]) -> str:
        """
        构建计划生成的提示。

        Args:
            goal: 要计划的目标
            context: 可选的执行上下文

        Returns:
            str: 格式化的提示
        """
        base_prompt = f"""You are a planning agent. Given the following goal, break it down into specific, executable steps.

Goal: {goal}

Requirements:
1. Each step should be atomic and achievable in one action
2. Steps should be ordered logically (dependencies first)
3. Focus on the essential steps needed to achieve the goal
4. Do NOT specify HOW to do things, only WHAT to do
5. Include tool_hint and expected_artifact for each step when possible
6. Include acceptance_criteria and fallback_strategy for high-risk steps

Output format (JSON):
{{
    "steps": [
        {{
          "step_id": 1,
          "description": "Step description",
          "depends_on": [],
          "tool_hint": "paper_tool",
          "expected_artifact": "paper_spec.json",
          "acceptance_criteria": "...",
          "fallback_strategy": "..."
        }}
    ]
}}
"""

        if any(keyword in goal.lower() for keyword in ["论文", "paper", "reproduce", "复现"]):
            base_prompt += """

Domain Hint (paper reproduction):
- Prefer lifecycle steps: paper ingestion -> source acquisition -> repo analysis -> sandbox prep -> testing -> documentation.
- Prefer tool hints from: paper_tool, source_tool, repo_index_tool, sandbox_tool, test_tool, doc_tool.
"""

        if context and context.metadata.get("history"):
            base_prompt += f"\n\nPrevious attempts context:\n{context.metadata['history']}"

        return base_prompt

    def _build_replan_prompt(self, plan: Plan, reason: str, context: ExecutionContext) -> str:
        """
        构建重新规划的提示。

        Args:
            plan: 当前计划
            reason: 需要重新规划的原因
            context: 执行上下文

        Returns:
            str: 格式化的提示
        """
        failed_steps = [s for s in plan.steps if s.status == "failed"]
        completed_steps = [s for s in plan.steps if s.status == "completed"]

        prompt = f"""You are a replanning agent. The current plan failed and needs adjustment.

Original Goal: {plan.goal}

Reason for replanning: {reason}

Completed Steps:
{self._format_steps(completed_steps)}

Failed Steps:
{self._format_steps(failed_steps)}

Create a revised plan that:
1. Keeps the completed steps as-is
2. Modifies or replaces the failed steps
3. Adds new steps if needed to overcome the failure
4. Focuses on what went wrong and how to fix it

Output format (JSON):
{{
    "steps": [
        {{"step_id": 1, "description": "Step description", "depends_on": []}}
    ]
}}
"""
        return prompt

    def _format_steps(self, steps: List[PlanStep]) -> str:
        """Format steps for prompt."""
        if not steps:
            return "None"
        return "\n".join(
            f"- Step {s.step_id}: {s.description} (Result: {s.result})"
            for s in steps
        )

    def _parse_plan_response(self, response: Dict[str, Any]) -> List[PlanStep]:
        """
        Parse LLM response into PlanStep objects.

        Args:
            response: LLM JSON response

        Returns:
            List of PlanStep objects
        """
        steps = []
        for item in response.get("steps", []):
            steps.append(
                PlanStep(
                    step_id=item.get("step_id", len(steps) + 1),
                    description=item.get("description", "No description"),
                    depends_on=item.get("depends_on", []),
                    tool_hint=item.get("tool_hint"),
                    expected_artifact=item.get("expected_artifact"),
                    acceptance_criteria=item.get("acceptance_criteria"),
                    fallback_strategy=item.get("fallback_strategy"),
                )
            )
        return steps

    def _create_fallback_plan(self, goal: str) -> List[PlanStep]:
        """
        Create simple fallback plan when LLM unavailable.

        Args:
            goal: The goal

        Returns:
            List of PlanStep objects
        """
        return [
            PlanStep(step_id=1, description=f"Analyze goal: {goal[:50]}..."),
            PlanStep(step_id=2, description="Break down into sub-tasks"),
            PlanStep(step_id=3, description="Execute sub-tasks sequentially"),
            PlanStep(step_id=4, description="Verify results and conclude"),
        ]

    def _create_demo_plan(self, goal: str) -> List[PlanStep]:
        """Create a demo plan for demonstration mode."""
        return [
            PlanStep(step_id=1, description=f"[DEMO] Understand: {goal[:50]}..."),
            PlanStep(step_id=2, description="[DEMO] Create sub-plan"),
            PlanStep(step_id=3, description="[DEMO] Execute step 1"),
            PlanStep(step_id=4, description="[DEMO] Execute step 2"),
            PlanStep(step_id=5, description="[DEMO] Verify completion"),
        ]

    def _create_recovery_plan(self, plan: Plan, reason: str) -> List[PlanStep]:
        """
        Create recovery plan after failure.

        Args:
            plan: Current plan
            reason: Failure reason

        Returns:
            List of new PlanStep objects
        """
        return [
            PlanStep(step_id=len(plan.steps) + 1, description=f"Address failure: {reason[:50]}..."),
            PlanStep(step_id=len(plan.steps) + 2, description="Retry failed step with alternative approach"),
            PlanStep(step_id=len(plan.steps) + 3, description="Verify recovery and continue"),
        ]
