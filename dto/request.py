# ============================================================
# 请求 DTO
# ============================================================
"""
API请求数据结构定义。

用于接收前端或外部系统的请求数据。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRequest:
    """
    Agent执行请求

    发起一个Agent任务的请求格式。
    """
    # 任务描述
    task: str
    # 训练模式
    mode: str = "algorithm"
    # 会话ID
    session_id: str = "default"
    # 用户ID
    user_id: str = "anonymous"
    # 附加参数
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        """
        转换为Agent执行的上下文

        Returns:
            dict: 上下文字典
        """
        return {
            "task": self.task,
            "mode": self.mode,
            "session_id": self.session_id,
            "user_id": self.user_id,
            **self.parameters,
        }


@dataclass
class UserProfileUpdate:
    """
    用户画像更新请求

    更新用户信息和技能水平。
    """
    user_id: str
    # 基本信息
    username: str | None = None
    email: str | None = None
    # 学习偏好
    preferred_mode: str | None = None
    preferred_language: str | None = None
    difficulty_preference: str | None = None
    # 技能更新
    skill_updates: dict[str, float] | None = None  # category -> score
