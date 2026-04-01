# ============================================================
# Trace 数据结构
# ============================================================
"""
Trace 数据结构定义。

记录Agent执行的全过程：
- 包含所有步骤
- 支持可视化
- 可用于评估和分析
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class StepStatus(Enum):
    """步骤状态枚举"""
    PENDING = "pending"              # 等待执行
    RUNNING = "running"             # 执行中
    COMPLETED = "completed"          # 已完成
    FAILED = "failed"               # 执行失败


@dataclass
class Step:
    """
    Agent执行中的单一步骤

    对应 ReAct 循环中的 Thought/Action/Observation。
    """
    # 基本信息
    step_id: str                     # 步骤唯一ID
    trace_id: str                    # 所属Trace ID

    # 推理信息
    thought: str                     # 思考内容
    action: str | None               # 执行的动作（工具名）
    action_input: dict[str, Any]     # 动作输入参数

    # 工具调用
    tool_name: str | None = None    # 调用的工具名
    tool_input: dict[str, Any] | None = None  # 工具输入
    tool_output: Any | None = None  # 工具输出

    # 状态
    status: StepStatus = StepStatus.PENDING
    observation: str = ""           # 观察结果
    error: str | None = None        # 错误信息

    # 反思（可选）
    reflection: str | None = None   # 反思内容

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    def complete(self, result: Any = None) -> None:
        """标记步骤完成"""
        self.status = StepStatus.COMPLETED
        self.completed_at = datetime.now()
        if result:
            self.tool_output = result

    def fail(self, error: str) -> None:
        """标记步骤失败"""
        self.status = StepStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

    def add_reflection(self, reflection: str) -> None:
        """添加反思"""
        self.reflection = reflection

    @property
    def duration_ms(self) -> float | None:
        """计算耗时（毫秒）"""
        if self.completed_at and self.created_at:
            return (self.completed_at - self.created_at).total_seconds() * 1000
        return None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "step_id": self.step_id,
            "trace_id": self.trace_id,
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "tool_name": self.tool_name,
            "observation": self.observation,
            "status": self.status.value,
            "error": self.error,
            "reflection": self.reflection,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
        }


@dataclass
class Trace:
    """
    完整的执行Trace

    记录一次Agent执行的完整过程。
    包含多个Step和元信息。
    """
    # 基本信息
    trace_id: str                     # 唯一标识
    session_id: str                   # 会话ID
    user_id: str                      # 用户ID

    # 上下文
    mode: str                         # 训练模式
    task_description: str             # 任务描述
    user_level: str = "beginner"     # 用户水平

    # 执行步骤
    steps: list[Step] = field(default_factory=list)

    # 最终结果
    final_output: str | None = None
    success: bool = False

    # 元数据
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    # 统计信息
    tool_usage: dict[str, int] = field(default_factory=dict)
    error_count: int = 0

    def add_step(self, step: Step) -> None:
        """添加步骤"""
        self.steps.append(step)
        # 更新工具使用统计
        if step.tool_name:
            self.tool_usage[step.tool_name] = self.tool_usage.get(step.tool_name, 0) + 1
        # 更新错误计数
        if step.status == StepStatus.FAILED:
            self.error_count += 1

    def recent_steps(self, n: int = 5) -> list[Step]:
        """获取最近N个步骤"""
        return self.steps[-n:] if self.steps else []

    def complete(self, output: str, success: bool) -> None:
        """标记Trace完成"""
        self.final_output = output
        self.success = success
        self.completed_at = datetime.now()

    @property
    def total_duration_seconds(self) -> float | None:
        """计算总耗时（秒）"""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "mode": self.mode,
            "task_description": self.task_description,
            "user_level": self.user_level,
            "steps": [s.to_dict() for s in self.steps],
            "final_output": self.final_output,
            "success": self.success,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_duration_seconds": self.total_duration_seconds,
            "tool_usage": self.tool_usage,
            "error_count": self.error_count,
        }


@dataclass
class TraceTimeline:
    """
    Timeline展示数据

    用于前端Timeline组件的优化数据结构。
    分离了概要和详情，减少数据传输量。
    """
    trace_id: str
    total_steps: int

    # 步骤概要（用于Timeline）
    steps_summary: list["StepSummary"]

    # 统计信息
    statistics: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepSummary:
    """步骤概要 - 用于Timeline展示"""
    step_id: int                     # 序号（从1开始）
    thought_preview: str              # 思考预览（截取）
    action_preview: str               # 动作预览
    tool_name: str | None             # 工具名
    status: str
    duration_ms: float | None
