from enum import Enum
from datetime import datetime
from typing import List

from app.core.logging import get_logger


class AgentState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"


VALID_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.IDLE: {AgentState.PLANNING},
    AgentState.PLANNING: {AgentState.EXECUTING, AgentState.FAILED},
    AgentState.EXECUTING: {AgentState.EXECUTING, AgentState.REFLECTING, AgentState.COMPLETED, AgentState.FAILED},
    AgentState.REFLECTING: {AgentState.EXECUTING, AgentState.REPLANNING, AgentState.FAILED},
    AgentState.REPLANNING: {AgentState.PLANNING, AgentState.EXECUTING, AgentState.FAILED},
    AgentState.COMPLETED: set(),
    AgentState.FAILED: set(),
}


class StateTransition:
    def __init__(self, from_state: AgentState, to_state: AgentState, reason: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        self.timestamp = datetime.now()
        self.reason = reason


class StateManager:
    def __init__(self, max_steps: int = 10):
        self.current_state = AgentState.IDLE
        self.history: List[StateTransition] = []
        self._max_steps = max_steps
        self._step_count = 0
        self._retry_count = 0
        self._log = get_logger("state")

    def transition_to(self, target: AgentState, reason: str = "") -> bool:
        if target not in VALID_TRANSITIONS.get(self.current_state, set()):
            self._log.warning(f"Forcing invalid transition: {self.current_state.value} -> {target.value}")
            t = StateTransition(self.current_state, target, f"{reason} [forced]")
        else:
            t = StateTransition(self.current_state, target, reason)
        self.history.append(t)
        self._log.info(f"{self.current_state.value} -> {target.value} | {reason}")
        self.current_state = target
        return True

    def step(self):
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count

    def increment_retry(self):
        self._retry_count += 1

    def reset_retry(self):
        self._retry_count = 0

    @property
    def retry_count(self) -> int:
        return self._retry_count

    def should_terminate(self) -> bool:
        if self.current_state in (AgentState.COMPLETED, AgentState.FAILED):
            return True
        if self._step_count >= self._max_steps:
            self._log.warning(f"Max steps ({self._max_steps}) reached")
            return True
        return False

    def is_terminal(self) -> bool:
        return self.current_state in (AgentState.COMPLETED, AgentState.FAILED)

    def reset(self):
        self.current_state = AgentState.IDLE
        self.history.clear()
        self._step_count = 0
        self._retry_count = 0

    def summary(self) -> dict:
        return {
            "state": self.current_state.value,
            "steps": self._step_count,
            "retries": self._retry_count,
            "transitions": len(self.history),
        }
