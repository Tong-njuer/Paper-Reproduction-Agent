# ============================================================
# Evaluator - 评估结果
# ============================================================
"""
Evaluator负责评估执行结果和代码质量。

职责：
1. 验证代码正确性（通过测试等）
2. 评估代码质量
3. 判断是否满足成功标准
4. 提供改进建议

设计思路：
- Evaluator是Agent的"裁判"角色
- 评估标准可配置、可扩展
- 支持多维度评估（正确性、效率、可读性等）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agent.base import Plan, StepResult, EvaluationResult


@dataclass
class EvaluationCriteria:
    """
    评估标准

    定义评估的具体维度和方法。
    """
    # 评估维度
    dimensions: list[str] = field(default_factory=lambda: [
        "correctness",    # 正确性
        "efficiency",     # 效率
        "code_quality",   # 代码质量
    ])

    # 各维度的权重
    weights: dict[str, float] = field(default_factory=lambda: {
        "correctness": 0.5,
        "efficiency": 0.3,
        "code_quality": 0.2,
    })

    # 正确性标准
    require_all_tests_pass: bool = True   # 是否要求所有测试通过
    min_test_coverage: float = 0.8        # 最低测试覆盖率

    # 效率标准
    max_time_complexity: str = "O(n^2)"   # 最高时间复杂度
    max_execution_time_ms: int = 5000    # 最大执行时间

    # 质量标准
    min_quality_score: float = 0.7        # 最低质量分数


@dataclass
class EvaluationReport:
    """
    评估报告

    详细的评估结果，包含各维度得分和建议。
    """
    # 总体评估
    is_satisfactory: bool                # 是否满足要求
    overall_score: float                 # 综合评分 (0-1)

    # 各维度评分
    dimension_scores: dict[str, float]   # 各维度得分

    # 详细结果
    test_results: dict[str, Any]         # 测试结果详情
    quality_report: dict[str, Any]       # 质量报告

    # 改进建议
    suggestions: list[str]               # 改进建议列表
    critical_issues: list[str]           # 关键问题（必须修复）

    # 元数据
    evaluation_method: str                # 评估方法
    metadata: dict[str, Any] = field(default_factory=dict)


class Evaluator(ABC):
    """
    Evaluator抽象基类

    定义评估功能的通用接口。
    具体的评估逻辑由子类实现。
    """

    def __init__(self, criteria: EvaluationCriteria | None = None):
        """
        初始化Evaluator

        Args:
            criteria: 评估标准（可选，使用默认标准）
        """
        self.criteria = criteria or EvaluationCriteria()

    async def evaluate(
        self,
        step_result: StepResult,
        plan: Plan,
        context: dict[str, Any],
    ) -> EvaluationResult:
        """
        评估步骤结果

        在每个步骤执行后调用，快速判断是否继续或调整。

        Args:
            step_result: 步骤执行结果
            plan: 当前计划
            context: 执行上下文

        Returns:
            EvaluationResult: 评估结果
        """
        # 执行详细评估
        report = await self._perform_evaluation(step_result, plan, context)

        # 转换为简化结果
        return EvaluationResult(
            is_satisfactory=report.is_satisfactory,
            need_replan=report.is_satisfactory and len(report.critical_issues) > 0,
            feedback=self._generate_feedback(report),
            score=report.overall_score,
        )

    async def final_evaluate(
        self,
        plan: Plan,
        context: dict[str, Any],
    ) -> EvaluationResult:
        """
        最终评估

        在Agent执行完成后调用，进行最终判定。

        Args:
            plan: 最终计划
            context: 执行上下文

        Returns:
            EvaluationResult: 最终评估结果
        """
        # 获取最后几步的结果进行评估
        # 简化实现
        return EvaluationResult(
            is_satisfactory=True,
            need_replan=False,
            feedback="任务完成",
            score=1.0,
            output="已完成",
        )

    # ============================================================
    # 抽象方法 - 子类实现
    # ============================================================

    @abstractmethod
    async def _perform_evaluation(
        self,
        step_result: StepResult,
        plan: Plan,
        context: dict[str, Any],
    ) -> EvaluationReport:
        """
        执行详细评估

        子类实现具体的评估逻辑。

        Args:
            step_result: 步骤结果
            plan: 当前计划
            context: 上下文

        Returns:
            EvaluationReport: 详细评估报告
        """
        pass

    def _generate_feedback(self, report: EvaluationReport) -> str:
        """
        生成评估反馈

        将评估报告转换为自然语言反馈。

        Args:
            report: 评估报告

        Returns:
            str: 反馈文本
        """
        if report.is_satisfactory:
            return "评估通过。" + " ".join(report.suggestions[:2])
        else:
            return "评估未通过。" + " ".join(report.critical_issues[:2])


# ============================================================
# 具体Evaluator实现（示例）
# ============================================================

class AlgorithmEvaluator(Evaluator):
    """
    算法训练评估器

    专门评估算法训练场景：
    - 测试用例通过率
    - 时间复杂度
    - 代码正确性
    """

    async def _perform_evaluation(
        self,
        step_result: StepResult,
        plan: Plan,
        context: dict[str, Any],
    ) -> EvaluationReport:
        """执行算法评估"""
        # TODO: 实现具体的评估逻辑
        # 1. 获取测试结果
        # 2. 分析代码质量
        # 3. 计算各维度得分

        # 简化实现
        return EvaluationReport(
            is_satisfactory=True,
            overall_score=0.85,
            dimension_scores={
                "correctness": 0.9,
                "efficiency": 0.8,
                "code_quality": 0.85,
            },
            test_results={"passed": 5, "failed": 0},
            quality_report={},
            suggestions=["可以考虑使用更高效的数据结构"],
            critical_issues=[],
            evaluation_method="algorithm",
        )
