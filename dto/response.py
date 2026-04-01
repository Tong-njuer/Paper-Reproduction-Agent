# ============================================================
# 响应 DTO
# ============================================================
"""
API响应数据结构定义。

用于返回给前端或外部系统的响应数据。
"""

from dataclasses import dataclass, field
from typing import Any

from dto.trace import Trace


@dataclass
class AgentResponse:
    """
    Agent执行响应

    包含Agent执行的结果和Trace。
    """
    # 是否成功
    success: bool
    # 输出内容
    output: str
    # Trace记录
    trace: Trace | None = None
    # 错误信息（如果失败）
    error: str | None = None
    # 附加元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "output": self.output,
            "trace": self.trace.to_dict() if self.trace else None,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class StepResponse:
    """
    单步响应

    用于实时展示Agent执行过程。
    """
    step_id: str
    step_number: int
    # 推理信息
    thought: str
    action: str | None
    # 状态
    status: str  # pending, running, completed, failed
    # 观察结果
    observation: str | None = None
    # 执行结果
    tool_output: str | None = None
    # 反思
    reflection: str | None = None
    # 时间戳
    timestamp: str | None = None


@dataclass
class ModeInfo:
    """
    模式信息

    描述一个训练模式的基本信息。
    """
    mode_name: str
    display_name: str
    description: str
    tags: list[str] = field(default_factory=list)
    available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode_name": self.mode_name,
            "display_name": self.display_name,
            "description": self.description,
            "tags": self.tags,
            "available": self.available,
        }


@dataclass
class TimelineResponse:
    """
    Timeline展示响应

    用于前端Timeline组件展示。
    """
    trace_id: str
    total_steps: int
    current_step: int
    status: str  # running, completed, failed
    steps: list[dict[str, Any]]
