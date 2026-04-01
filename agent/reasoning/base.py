# ============================================================
# ReasoningEngine - 推理引擎基类
# ============================================================
"""
推理引擎的抽象基类。

设计思路：
- 推理引擎负责"思考"决策，不直接执行
- 输入：当前状态、计划、上下文
- 输出：推理结果（思考内容、动作、参数）
- 支持多种推理模式（ReAct、Reflexion等）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from tools.registry import ToolRegistry


@dataclass
class ReasoningContext:
    """
    推理上下文

    包含推理所需的所有信息。
    """
    # 当前状态
    plan: "Plan"                      # 当前执行计划
    current_step_index: int = 0       # 当前步骤索引

    # 历史信息
    previous_thoughts: list[str] = field(default_factory=list)   # 之前的思考
    previous_actions: list[str] = field(default_factory=list)    # 之前的动作
    previous_observations: list[str] = field(default_factory=list)  # 之前的观察

    # 反思历史（Reflexion用）
    reflections: list[str] = field(default_factory=list)        # 历史反思

    # 环境信息
    tool_registry: ToolRegistry | None = None                    # 工具注册器
    user_profile: dict[str, Any] | None = None                   # 用户画像

    # 配置
    max_reasoning_steps: int = 5                                  # 最大推理步数


@dataclass
class ReasoningResult:
    """
    推理结果

    包含推理引擎的完整输出。
    """
    # 思考内容
    thought: str                       # 思考过程描述

    # 动作决策
    action: str | None                 # 要执行的动作（工具名）
    action_params: dict[str, Any] | None  # 动作参数

    # 状态
    is_finish: bool = False           # 是否应该结束
    need_more_reasoning: bool = False # 是否需要更多推理

    # 元数据
    confidence: float = 1.0           # 决策置信度 (0-1)
    reasoning_steps: int = 1          # 推理步数
    metadata: dict[str, Any] = field(default_factory=dict)


class ReasoningEngine(ABC):
    """
    推理引擎抽象基类

    定义推理功能的通用接口。
    具体的推理逻辑由子类实现。

    设计原则：
    - 推理与执行分离
    - 支持可插拔的推理策略
    - 每次推理都是独立的
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """推理引擎名称"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """推理引擎描述"""
        pass

    @abstractmethod
    async def think(
        self,
        context: ReasoningContext,
    ) -> ReasoningResult:
        """
        执行推理

        主入口方法，根据上下文进行推理。

        Args:
            context: 推理上下文

        Returns:
            ReasoningResult: 推理结果
        """
        pass

    # ============================================================
    # 可选的钩子方法（可重写）
    # ============================================================

    async def think_step(
        self,
        context: ReasoningContext,
        step: int,
    ) -> ReasoningResult:
        """
        单步推理

        在复杂推理过程中，每一步的推理。
        默认实现调用 think()，可被子类重写。

        Args:
            context: 推理上下文
            step: 当前步数

        Returns:
            ReasoningResult: 推理结果
        """
        return await self.think(context)

    async def reset(self) -> None:
        """
        重置推理引擎状态

        在新的推理任务开始前调用。
        """
        pass
