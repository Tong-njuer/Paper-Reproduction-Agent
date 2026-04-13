# ============================================================
# 上下文管理模块
# ============================================================
# 管理 Agent 的对话和执行上下文。
# 提供对当前状态和历史的结构化访问。
#
# Console Output: Agent 执行过程中的上下文更新
# ============================================================

from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class StepContext(BaseModel):
    """
    单步执行的上下文。

    Attributes:
        step_id: 唯一步骤标识符
        thought: 该步骤的 Agent 推理
        action: 执行的操作（工具名称）
        action_args: 传递给操作的参数
        observation: 操作结果
        timestamp: 发生时间
    """
    step_id: int
    thought: str = ""
    action: str = ""
    action_args: Dict[str, Any] = Field(default_factory=dict)
    observation: str = ""
    result: str = "pending"  # pending, success, failure
    timestamp: datetime = Field(default_factory=datetime.now)


class ExecutionContext(BaseModel):
    """
    Agent 运行的总体执行上下文。

    跟踪执行的完整历史和当前状态。

    Attributes:
        goal: 原始目标
        plan: 当前计划（子目标列表）
        steps: 所有执行步骤的历史
        current_step: 当前步骤索引
        status: 总体状态（running, completed, failed, terminated）
        metadata: 额外的上下文数据
    """
    goal: str
    plan: List[Dict[str, Any]] = Field(default_factory=list)
    steps: List[StepContext] = Field(default_factory=list)
    current_step: int = 0
    status: str = "initialized"  # initialized, running, completed, failed, terminated
    consecutive_failures: int = 0
    total_tokens_used: int = 0
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def add_step(
        self,
        thought: str,
        action: str,
        action_args: Dict[str, Any],
        observation: str,
        result: str = "pending",
    ) -> StepContext:
        """
        添加一个新步骤到执行历史。

        Args:
            thought: Agent 的推理
            action: 执行的操作
            action_args: 操作参数
            observation: 结果观察
            result: 步骤结果状态

        Returns:
            StepContext: 新创建的步骤
        """
        step = StepContext(
            step_id=len(self.steps),
            thought=thought,
            action=action,
            action_args=action_args,
            observation=observation,
            result=result,
        )
        self.steps.append(step)
        self.current_step = len(self.steps)
        return step

    def update_last_step(self, observation: str, result: str) -> None:
        """
        更新最新步骤的观察和结果。

        Args:
            observation: 最终观察
            result: 步骤结果（success/failure）
        """
        if self.steps:
            self.steps[-1].observation = observation
            self.steps[-1].result = result

    def increment_failures(self) -> None:
        """增加连续失败计数器。"""
        self.consecutive_failures += 1

    def reset_failures(self) -> None:
        """重置连续失败计数器。"""
        self.consecutive_failures = 0

    def mark_complete(self, status: str = "completed") -> None:
        """
        标记执行完成。

        Args:
            status: 最终状态（completed, failed, terminated）
        """
        self.status = status
        self.end_time = datetime.now()

    def get_duration(self) -> float:
        """
        获取执行持续时间（秒）。

        Returns:
            float: 持续时间（秒）
        """
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    def print_summary(self) -> None:
        """
        Print a summary of the execution context.
        Useful for debugging and logging.
        """
        print("\n" + "=" * 60)
        print("[STAT] Execution Context Summary")
        print("=" * 60)

        print(f"\n[GOAL] Goal: {self.goal}")

        print(f"\n[PROGRESS] Status: {self.status.upper()}")
        print(f"   Current Step:  {self.current_step}")
        print(f"   Total Steps:   {len(self.steps)}")
        print(f"   Failures:      {self.consecutive_failures}")
        print(f"   Duration:      {self.get_duration():.2f}s")
        print(f"   Tokens Used:   {self.total_tokens_used}")

        if self.plan:
            print(f"\n[INFO] Plan ({len(self.plan)} items):")
            for i, item in enumerate(self.plan[:5]):
                print(f"   {i+1}. {item.get('description', 'N/A')}")
            if len(self.plan) > 5:
                print(f"   ... and {len(self.plan) - 5} more")

        if self.steps:
            print(f"\n[NOTE] Recent Steps:")
            for step in self.steps[-3:]:
                status_icon = "[OK]" if step.result == "success" else "[X]" if step.result == "failure" else "[WAIT]"
                print(f"   {status_icon} Step {step.step_id}: {step.action}")
                if step.thought:
                    print(f"      Thought: {step.thought[:50]}...")

        print("\n" + "=" * 60 + "\n")


# ============================================================
# Context Manager (Singleton)
# ============================================================
_context: Optional[ExecutionContext] = None


def create_context(goal: str) -> ExecutionContext:
    """
    创建新的执行上下文。

    Args:
        goal: 此执行的目标

    Returns:
        ExecutionContext: 新上下文实例
    """
    global _context
    _context = ExecutionContext(goal=goal)
    print(f"\n[NEW] Execution Context Created")
    print(f"   Goal: {goal}")
    return _context


def get_context() -> Optional[ExecutionContext]:
    """
    Get the current execution context.

    Returns:
        ExecutionContext or None if not created
    """
    return _context


def clear_context() -> None:
    """清除当前执行上下文。"""
    global _context
    _context = None
