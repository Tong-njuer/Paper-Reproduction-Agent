# ============================================================
# AlgorithmMode - 算法训练模式
# ============================================================
"""
算法训练模式实现。

训练流程：
1. 理解题目
2. 分析算法思路
3. 编写代码实现
4. 生成测试用例
5. 运行测试，修复错误
6. 优化性能
7. 最终验证

评估重点：
- 测试用例通过率
- 时间/空间复杂度
- 代码正确性
"""

from dataclasses import dataclass

from agent.modes.base import (
    ModeConfig,
    ModeComponents,
    TrainingMode,
)
from tools.base import Tool
from tools.impl.run_code import RunCodeTool
from tools.impl.generate_tests import GenerateTestsTool
from tools.impl.analyze_error import AnalyzeErrorTool


class AlgorithmMode(TrainingMode):
    """
    算法训练模式

    专门用于算法题目练习和训练。
    """

    def _create_config(self) -> ModeConfig:
        """创建算法模式配置"""
        return ModeConfig(
            mode_name="algorithm",
            display_name="算法训练",
            description="通过算法题目练习提升编程能力",
            system_prompt=self._get_default_system_prompt(),
            user_prompt_template="{task}",
            required_tools=["run_code", "generate_tests", "analyze_error"],
            optional_tools=["code_linter"],
            max_iterations=15,
            timeout_seconds=600,
            evaluation_criteria={
                "test_pass_rate": 1.0,  # 要求100%通过
                "max_complexity": "O(n^2)",
                "min_quality_score": 0.7,
            },
            tags=["algorithm", "coding", "practice"],
        )

    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词"""
        return """你是一个专业的算法教练Agent。

你的职责是帮助用户通过算法题目练习提升编程能力。

训练流程：
1. 首先理解题目要求和示例
2. 分析最优的算法思路
3. 编写清晰、高效的代码
4. 生成全面的测试用例
5. 运行测试并修复发现的问题
6. 优化代码性能
7. 确保代码质量

评估标准：
- 所有测试用例必须通过
- 代码时间复杂度应尽可能低
- 代码需要清晰可读，有必要的注释
- 考虑边界条件和特殊情况

在提供解决方案时：
- 先给出思路分析
- 再给出具体实现
- 最后验证结果
"""

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self._config.system_prompt

    def select_tools(self) -> list[type[Tool]]:
        """选择算法训练需要的工具"""
        return [
            RunCodeTool,
            GenerateTestsTool,
            AnalyzeErrorTool,
        ]

    def create_mode_components(self) -> ModeComponents:
        """创建算法模式组件"""
        return ModeComponents(
            planner_type="algorithm",
            planner_config={
                "strategy": "step_by_step",
                "include_complexity_analysis": True,
            },
            evaluator_type="algorithm",
            evaluator_config={
                "require_all_tests_pass": True,
                "check_time_complexity": True,
                "check_space_complexity": True,
            },
            reflector_type="algorithm",
            reflector_config={
                "focus_on_optimization": True,
            },
        )

    def pre_execute_hook(self, task: str, context: dict) -> dict:
        """执行前钩子：添加算法相关上下文"""
        context["mode"] = "algorithm"
        context["success_criteria"] = self._config.evaluation_criteria
        return context


class AlgorithmPlanner:
    """
    算法计划器

    专门为算法任务设计的计划策略。
    """

    @staticmethod
    def create_plan(task: str, user_level: str) -> dict:
        """
        创建算法训练计划

        Args:
            task: 题目描述
            user_level: 用户水平

        Returns:
            dict: 计划详情
        """
        # 基础步骤
        steps = [
            "理解题目要求和示例",
            "分析算法思路，确定最优方案",
            "编写代码实现",
            "生成测试用例验证",
            "运行测试，修复错误",
            "分析并优化性能",
            "最终验证",
        ]

        # 根据用户水平调整
        if user_level == "beginner":
            steps.insert(2, "理解基础概念（如有需要）")
            steps.append("总结学习要点")
        elif user_level in ("intermediate", "advanced"):
            steps[1] = "分析多种解法，比较优劣"
            steps.insert(5, "尝试进一步优化")

        return {
            "task": task,
            "steps": steps,
            "estimated_time": len(steps) * 5,  # 预估分钟数
        }
