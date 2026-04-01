# ============================================================
# Planner - 训练计划制定
# ============================================================
"""
Planner负责分析和拆解任务，制定训练计划。

职责：
1. 理解用户任务需求
2. 评估用户当前水平
3. 制定分步骤的训练计划
4. 根据执行情况动态调整计划

设计思路：
- Planner是Agent的核心组件之一
- 计划制定依赖于用户画像和任务分析
- 支持动态调整（当评估反馈需要重新计划时）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agent.base import Plan


@dataclass
class PlanningContext:
    """
    计划制定的上下文信息

    包含制定计划所需的所有参考信息。
    """
    task: str                          # 用户任务
    user_level: "UserLevel"            # 用户水平
    user_strengths: list[str] = field(default_factory=list)  # 用户优势
    user_weaknesses: list[str] = field(default_factory=list) # 用户弱点
    mode: str = "algorithm"            # 当前模式
    previous_plan: Plan | None = None  # 之前的计划（如果有）
    previous_feedback: str = ""        # 之前计划的反馈（用于调整）


class Planner(ABC):
    """
    Planner抽象基类

    定义计划制定的通用接口。
    具体的规划策略由子类实现。

    使用示例：
    ```python
    class AlgorithmPlanner(Planner):
        def _create_planning_strategy(self) -> PlanningStrategy:
            return AlgorithmPlanningStrategy()

        async def _analyze_task(self, context: PlanningContext) -> TaskAnalysis:
            # 算法特定的Task分析
            ...
    ```
    """

    def __init__(self):
        """初始化Planner"""
        self._strategies = {}

    async def create_plan(
        self, task: str, context: dict[str, Any]
    ) -> Plan:
        """
        创建执行计划

        这是Planner的主入口方法：
        1. 构建PlanningContext
        2. 分析任务
        3. 生成计划

        Args:
            task: 用户任务描述
            context: 额外上下文（从外部传入）

        Returns:
            Plan: 生成的执行计划
        """
        # 构建上下文
        planning_context = self._build_context(task, context)

        # 分析任务
        analysis = await self._analyze_task(planning_context)

        # 生成计划
        plan = await self._generate_plan(analysis, planning_context)

        return plan

    async def adjust_plan(
        self,
        current_plan: Plan,
        feedback: str,
        context: dict[str, Any]
    ) -> Plan:
        """
        调整现有计划

        当执行评估显示需要重新计划时调用。
        基于反馈对原计划进行调整。

        Args:
            current_plan: 当前计划
            feedback: 评估反馈
            context: 上下文

        Returns:
            Plan: 调整后的新计划
        """
        planning_context = self._build_context(
            current_plan.task,
            context
        )
        planning_context.previous_plan = current_plan
        planning_context.previous_feedback = feedback

        # 分析问题所在
        analysis = await self._analyze_adjustment(planning_context)

        # 生成新计划
        return await self._generate_plan(analysis, planning_context)

    def _build_context(
        self, task: str, context: dict[str, Any]
    ) -> PlanningContext:
        """构建PlanningContext"""
        from agent.user_model import UserLevel

        return PlanningContext(
            task=task,
            user_level=context.get("user_level", UserLevel.BEGINNER),
            mode=context.get("mode", "algorithm"),
        )

    # ============================================================
    # 抽象方法 - 子类实现
    # ============================================================

    @abstractmethod
    async def _analyze_task(
        self, context: PlanningContext
    ) -> "TaskAnalysis":
        """
        分析任务

        理解任务目标，评估难度，识别关键点。

        Args:
            context: 计划上下文

        Returns:
            TaskAnalysis: 任务分析结果
        """
        pass

    @abstractmethod
    async def _generate_plan(
        self, analysis: "TaskAnalysis", context: PlanningContext
    ) -> Plan:
        """
        生成计划

        基于任务分析结果，生成具体的执行计划。

        Args:
            analysis: 任务分析结果
            context: 计划上下文

        Returns:
            Plan: 执行计划
        """
        pass

    async def _analyze_adjustment(
        self, context: PlanningContext
    ) -> "TaskAnalysis":
        """
        分析计划调整需求

        当需要重新计划时，分析问题所在。
        默认实现调用 _analyze_task，可被子类重写。

        Args:
            context: 包含之前计划反馈的上下文

        Returns:
            TaskAnalysis: 调整后的分析
        """
        return await self._analyze_task(context)


# ============================================================
# 任务分析结果
# ============================================================

@dataclass
class TaskAnalysis:
    """
    任务分析结果

    包含对用户任务的详细分析。
    """
    task_type: str                     # 任务类型（algorithm/design/project/refactor）
    difficulty: str                   # 难度级别（easy/medium/hard）
    key_points: list[str]              # 关键点/知识点
    estimated_steps: int              # 预估步骤数
    required_tools: list[str]         # 需要的工具
    success_criteria: list[str]       # 成功的评判标准
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================
# 具体Planner实现（示例）
# ============================================================

class AlgorithmPlanner(Planner):
    """
    算法训练Planner

    专门为算法训练场景设计的Planner。
    生成"读题→分析→实现→测试→优化"的计划。
    """

    async def _analyze_task(
        self, context: PlanningContext
    ) -> TaskAnalysis:
        """分析算法任务"""
        # TODO: 调用LLM分析任务
        # 这里返回简化实现
        return TaskAnalysis(
            task_type="algorithm",
            difficulty="medium",
            key_points=["数组遍历", "边界条件处理"],
            estimated_steps=5,
            required_tools=["run_code", "generate_tests", "analyze_error"],
            success_criteria=["通过所有测试用例", "时间复杂度<O(n^2)"],
        )

    async def _generate_plan(
        self, analysis: TaskAnalysis, context: PlanningContext
    ) -> Plan:
        """生成算法训练计划"""
        steps = [
            "理解题目要求和示例",
            "分析算法思路，确定最优方案",
            "编写代码实现",
            "生成测试用例验证",
            "分析错误并修复（如有）",
            "优化性能（如需要）",
            "最终验证",
        ]

        return Plan(
            task=context.task,
            goal=f"完成算法训练：{context.task}",
            steps=steps,
            metadata={
                "task_analysis": analysis,
                "mode": "algorithm",
            },
        )
