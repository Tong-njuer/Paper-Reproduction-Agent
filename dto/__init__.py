# ============================================================
# dto/ 模块 - 数据传输对象
# ============================================================
"""
DTO模块。

定义API请求/响应的数据结构。
使用Pydantic进行验证。
"""

from dto.request import AgentRequest, UserProfileUpdate
from dto.response import AgentResponse, StepResponse, ModeInfo
from dto.trace import Trace, Step, StepStatus, TraceTimeline

__all__ = [
    "AgentRequest",
    "UserProfileUpdate",
    "AgentResponse",
    "StepResponse",
    "ModeInfo",
    "Trace",
    "Step",
    "StepStatus",
    "TraceTimeline",
]
