# ============================================================
# Reflector - 反思与调整
# ============================================================
"""
Reflector负责反思机制，从执行历史中学习并调整策略。

职责：
1. 分析执行历史
2. 识别成功模式和失败原因
3. 总结经验教训
4. 提出策略调整建议

设计思路：
- Reflexion是Agent自我改进的关键
- 基于最近的执行历史进行分析
- 可选的深度反思（不每次都触发）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Reflection:
    """
    反思结果

    包含反思分析的完整结果。
    """
    # 反思类型
    reflection_type: str               # "quick" | "deep"

    # 分析结果
    success_patterns: list[str]        # 成功的模式
    failure_reasons: list[str]         # 失败原因
    lessons_learned: list[str]         # 学到的教训

    # 策略调整
    strategy_adjustments: list[str]    # 策略调整建议
    tools_to_avoid: list[str] = field(default_factory=list)  # 应避免的工具
    tools_to_try: list[str] = field(default_factory=list)   # 可以尝试的工具

    # 元数据
    based_on_steps: int                # 基于的步骤数
    timestamp: Any = None              # 反思时间


class Reflector(ABC):
    """
    Reflector抽象基类

    定义反思功能的通用接口。

    设计原则：
    - 反思是可选的（可配置）
    - 支持快速反思和深度反思
    - 分析结果用于指导后续决策
    """

    def __init__(self, enable_deep_reflection: bool = False):
        """
        初始化Reflector

        Args:
            enable_deep_reflection: 是否启用深度反思
        """
        self.enable_deep_reflection = enable_deep_reflection
        self._reflection_history: list[Reflection] = []

    async def reflect(
        self,
        recent_steps: list,  # list[Step]
        reflection_type: str = "quick",
    ) -> Reflection:
        """
        执行反思

        主入口方法，分析最近的执行历史。

        Args:
            recent_steps: 最近的执行步骤（通常3-5步）
            reflection_type: 反思类型，"quick"或"deep"

        Returns:
            Reflection: 反思结果
        """
        # 1. 分析执行历史
        analysis = await self._analyze_execution(recent_steps)

        # 2. 生成反思结果
        reflection = await self._generate_reflection(
            analysis,
            reflection_type,
            len(recent_steps),
        )

        # 3. 保存到历史
        self._reflection_history.append(reflection)

        return reflection

    async def quick_reflect(self, steps: list) -> Reflection:
        """
        快速反思

        基于少量步骤的快速分析。

        Args:
            steps: 执行步骤

        Returns:
            Reflection: 反思结果
        """
        return await self.reflect(steps, "quick")

    async def deep_reflect(self, steps: list) -> Reflection:
        """
        深度反思

        更全面的分析，考虑更多历史和上下文。
        仅在连续失败等情况下触发。

        Args:
            steps: 执行步骤

        Returns:
            Reflection: 反思结果
        """
        return await self.reflect(steps, "deep")

    # ============================================================
    # 抽象方法 - 子类实现
    # ============================================================

    @abstractmethod
    async def _analyze_execution(
        self, steps: list
    ) -> "ExecutionAnalysis":
        """
        分析执行历史

        识别成功模式、失败原因等。

        Args:
            steps: 执行步骤列表

        Returns:
            ExecutionAnalysis: 分析结果
        """
        pass

    @abstractmethod
    async def _generate_reflection(
        self,
        analysis: "ExecutionAnalysis",
        reflection_type: str,
        based_on_steps: int,
    ) -> Reflection:
        """
        生成反思结果

        基于分析结果生成具体的反思内容。

        Args:
            analysis: 执行分析结果
            reflection_type: 反思类型
            based_on_steps: 基于的步骤数

        Returns:
            Reflection: 反思结果
        """
        pass

    @property
    def reflection_history(self) -> list[Reflection]:
        """获取反思历史"""
        return self._reflection_history.copy()


# ============================================================
# 分析数据结构
# ============================================================

@dataclass
class ExecutionAnalysis:
    """
    执行分析结果

    包含对执行历史的分析结果。
    """
    # 基本统计
    total_steps: int                  # 总步骤数
    successful_steps: int             # 成功步骤数
    failed_steps: int                # 失败步骤数

    # 工具使用分析
    tools_used: list[str]             # 使用过的工具
    tool_success_rates: dict[str, float]  # 各工具成功率

    # 错误分析
    common_errors: list[str]          # 常见错误
    error_patterns: list[str]         # 错误模式

    # 成功分析
    successful_actions: list[str]      # 成功的动作
    success_factors: list[str]        # 成功因素

    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================
# 具体Reflector实现（示例）
# ============================================================

class ReflexionReflector(Reflector):
    """
    Reflexion风格的反思器

    基于Reflexion论文的实现：
    - 维护执行历史
    - 识别失败模式
    - 生成自我改进建议
    """

    async def _analyze_execution(
        self, steps: list
    ) -> ExecutionAnalysis:
        """
        分析执行历史

        识别成功和失败模式。

        Args:
            steps: 执行步骤

        Returns:
            ExecutionAnalysis: 分析结果
        """
        # 简化实现
        # TODO: 接入LLM进行深入分析

        tools_used = []
        successful_steps = 0
        failed_steps = 0

        for step in steps:
            if hasattr(step, 'tool_name') and step.tool_name:
                tools_used.append(step.tool_name)
            if hasattr(step, 'status'):
                if step.status == "completed":
                    successful_steps += 1
                elif step.status == "failed":
                    failed_steps += 1

        return ExecutionAnalysis(
            total_steps=len(steps),
            successful_steps=successful_steps,
            failed_steps=failed_steps,
            tools_used=list(set(tools_used)),
            tool_success_rates={},
            common_errors=[],
            error_patterns=[],
            successful_actions=[],
            success_factors=[],
        )

    async def _generate_reflection(
        self,
        analysis: ExecutionAnalysis,
        reflection_type: str,
        based_on_steps: int,
    ) -> Reflection:
        """生成反思结果"""
        # 简化实现
        # TODO: 基于分析结果生成有意义的反思

        if analysis.failed_steps > 0:
            return Reflection(
                reflection_type=reflection_type,
                success_patterns=["保持当前的问题分析方法"],
                failure_reasons=["执行过程中出现错误"],
                lessons_learned=["下次应更仔细地检查边界条件"],
                strategy_adjustments=["考虑换一种解题思路"],
                based_on_steps=based_on_steps,
                timestamp=self._get_current_time(),
            )
        else:
            return Reflection(
                reflection_type=reflection_type,
                success_patterns=["执行过程顺利"],
                failure_reasons=[],
                lessons_learned=["当前方法有效，可以复用"],
                strategy_adjustments=[],
                based_on_steps=based_on_steps,
                timestamp=self._get_current_time(),
            )

    @staticmethod
    def _get_current_time():
        """获取当前时间"""
        from datetime import datetime
        return datetime.now()
