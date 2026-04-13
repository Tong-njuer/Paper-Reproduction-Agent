# ============================================================
# 状态管理器模块
# ============================================================
# 管理和跟踪 Agent 的内部状态。
# 提供状态转换、历史和可视化。
#
# Console Output:
#   - State transitions
#   - Current status
#   - State history
# ============================================================

from typing import Dict, Any, List, Optional
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class AgentState(str, Enum):
    """
    Agent 可能的状态。

    States:
        IDLE: 初始状态，无任务
        PLANNING: 创建或更新计划
        EXECUTING: 运行操作
        REFLECTING: 执行自我反思
        REPLANNING: 调整计划
        COMPLETED: 任务成功完成
        FAILED: 任务失败
        TERMINATED: 任务终止（最大步数等）
    """
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


class StateTransition(BaseModel):
    """
    记录状态转换。

    Attributes:
        from_state: 先前状态
        to_state: 新状态
        timestamp: 转换发生时间
        reason: 转换原因
    """
    from_state: str
    to_state: str
    timestamp: datetime = Field(default_factory=datetime.now)
    reason: str = ""


class StateManager:
    """
    管理 Agent 状态和转换。

    跟踪:
    - 当前状态
    - 状态历史（转换）
    - 状态特定元数据

    Attributes:
        current_state: 当前 Agent 状态
        state_history: 所有状态转换的历史
        metadata: 额外的状态特定数据
    """

    # 有效的状态转换
    VALID_TRANSITIONS: Dict[AgentState, List[AgentState]] = {
        AgentState.IDLE: [AgentState.PLANNING],
        AgentState.PLANNING: [AgentState.EXECUTING, AgentState.IDLE],
        AgentState.EXECUTING: [AgentState.REFLECTING, AgentState.PLANNING, AgentState.COMPLETED, AgentState.FAILED],
        AgentState.REFLECTING: [AgentState.EXECUTING, AgentState.REPLANNING, AgentState.FAILED],
        AgentState.REPLANNING: [AgentState.EXECUTING, AgentState.FAILED],
        AgentState.COMPLETED: [AgentState.IDLE],
        AgentState.FAILED: [AgentState.IDLE],
        AgentState.TERMINATED: [AgentState.IDLE],
    }

    def __init__(self):
        """Initialize the State Manager."""
        self.current_state = AgentState.IDLE
        self.state_history: List[StateTransition] = []
        self.metadata: Dict[str, Any] = {}
        self._step_count: int = 0
        self._retry_count: int = 0

        print("[STAT] State Manager initialized")
        self._log_transition(AgentState.IDLE, AgentState.IDLE, "System initialized")

    @property
    def step_count(self) -> int:
        """Get current step count."""
        return self._step_count

    def increment_step(self) -> None:
        """Increment step counter."""
        self._step_count += 1

    def reset_step(self) -> None:
        """Reset step counter."""
        self._step_count = 0

    @property
    def retry_count(self) -> int:
        """Get current retry count."""
        return self._retry_count

    def increment_retry(self) -> None:
        """Increment retry counter."""
        self._retry_count += 1

    def reset_retry(self) -> None:
        """Reset retry counter."""
        self._retry_count = 0

    def transition_to(
        self,
        new_state: AgentState,
        reason: str = "",
        force: bool = False,
    ) -> bool:
        """
        转换到新状态。

        Args:
            new_state: 目标状态
            reason: 此转换发生的原因
            force: 跳过验证（谨慎使用）

        Returns:
            bool: 转换是否成功
        """
        old_state = self.current_state

        # Validate transition
        if not force:
            valid_targets = self.VALID_TRANSITIONS.get(self.current_state, [])
            if new_state not in valid_targets:
                print(f"[!]  Invalid transition: {old_state} -> {new_state}")
                print(f"   Valid targets from {old_state}: {valid_targets}")
                return False

        # Execute transition
        self.current_state = new_state
        self._log_transition(old_state, new_state, reason)

        # Update metadata
        self.metadata["last_transition"] = {
            "from": old_state.value,
            "to": new_state.value,
            "reason": reason,
            "time": datetime.now().isoformat(),
        }

        return True

    def _log_transition(
        self,
        from_state: AgentState,
        to_state: AgentState,
        reason: str = "",
    ) -> None:
        """
        Log a state transition.

        Args:
            from_state: Previous state
            to_state: New state
            reason: Transition reason
        """
        transition = StateTransition(
            from_state=from_state.value,
            to_state=to_state.value,
            reason=reason,
        )
        self.state_history.append(transition)

        # Print transition
        if from_state != to_state:
            print(f"\n[RETRY] State Transition:")
            print(f"   {from_state.value} -> {to_state.value}")
            if reason:
                print(f"   Reason: {reason}")

    def is_terminal_state(self) -> bool:
        """
        Check if current state is a terminal state.

        Returns:
            bool: True if in terminal state
        """
        return self.current_state in [
            AgentState.COMPLETED,
            AgentState.FAILED,
            AgentState.TERMINATED,
        ]

    def should_terminate(self, max_steps: int = 50) -> bool:
        """
        Check if agent should terminate.

        Args:
            max_steps: Maximum allowed steps

        Returns:
            bool: True if should terminate
        """
        if self.is_terminal_state():
            return True
        if self._step_count >= max_steps:
            print(f"\n[STOP] Termination: Max steps reached ({max_steps})")
            return True
        return False

    def get_state_summary(self) -> Dict[str, Any]:
        """
        Get a summary of current state.

        Returns:
            Dict with state information
        """
        return {
            "current_state": self.current_state.value,
            "step_count": self._step_count,
            "retry_count": self._retry_count,
            "is_terminal": self.is_terminal_state(),
            "metadata": self.metadata,
            "transition_count": len(self.state_history),
        }

    def print_state(self) -> None:
        """
        Print current state to console.
        """
        print("\n" + "=" * 50)
        print("[STAT] Agent State")
        print("=" * 50)
        print(f"   Current State: {self.current_state.value.upper()}")
        print(f"   Step Count:    {self._step_count}")
        print(f"   Retry Count:   {self._retry_count}")
        print(f"   Terminal:      {self.is_terminal_state()}")

        if self.metadata.get("last_transition"):
            lt = self.metadata["last_transition"]
            print(f"\n   Last Transition:")
            print(f"      {lt['from']} -> {lt['to']}")
            print(f"      Reason: {lt['reason']}")

        if self.state_history:
            print(f"\n   Recent History:")
            for t in self.state_history[-3:]:
                print(f"      {t.from_state} -> {t.to_state}: {t.reason[:30]}")

        print("=" * 50 + "\n")

    def reset(self) -> None:
        """
        Reset state manager to initial state.
        """
        old_state = self.current_state
        self.current_state = AgentState.IDLE
        self.state_history.clear()
        self.metadata.clear()
        self._step_count = 0
        self._retry_count = 0

        print("[STAT] State Manager reset")
        self._log_transition(old_state, AgentState.IDLE, "Reset")
