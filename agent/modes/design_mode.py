# ============================================================
# DesignMode - 设计训练模式
# ============================================================
"""
设计训练模式实现。

训练流程：
1. 分析现有代码结构
2. 识别设计问题和坏味道
3. 提出改进方案
4. 应用设计原则/模式
5. 验证改进效果

评估重点：
- SOLID原则符合度
- 设计模式应用恰当性
- 代码可扩展性、可维护性
"""

from agent.modes.base import (
    ModeConfig,
    ModeComponents,
    TrainingMode,
)
from tools.base import Tool
from tools.impl.design_analyzer import DesignAnalyzerTool


class DesignMode(TrainingMode):
    """
    设计训练模式

    专注于OOP设计和架构能力的训练。
    """

    def _create_config(self) -> ModeConfig:
        """创建设计模式配置"""
        return ModeConfig(
            mode_name="design",
            display_name="设计训练",
            description="学习OOP设计和设计模式，提升代码架构能力",
            system_prompt=self._get_default_system_prompt(),
            user_prompt_template="{task}",
            required_tools=["design_analyzer"],
            optional_tools=["code_linter", "run_code"],
            max_iterations=10,
            timeout_seconds=300,
            evaluation_criteria={
                "solid_score": 0.8,        # SOLID原则评分
                "pattern_appropriateness": 0.7,  # 模式应用恰当性
                "improvement_achieved": True,     # 是否达成改进
            },
            tags=["design", "OOP", "architecture", "patterns"],
        )

    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词"""
        return """你是一个专业的软件设计教练Agent。

你的职责是帮助用户提升OOP设计和架构能力。

训练流程：
1. 分析现有代码的结构和设计
2. 识别违反设计原则的地方（SOLID等）
3. 识别可以应用设计模式的场景
4. 提出改进方案
5. 解释为什么这样改进更好
6. 指导用户实施改进
7. 验证改进效果

设计原则（需要应用）：
- SRP: 单一职责原则
- OCP: 开闭原则
- LSP: 里氏替换原则
- ISP: 接口隔离原则
- DIP: 依赖倒置原则

常见设计模式：
- 创建型：Factory, Singleton, Builder
- 结构型：Adapter, Decorator, Facade
- 行为型：Strategy, Observer, Command

在提供指导时：
- 先分析当前设计的问题
- 再提出改进方案
- 解释原理和权衡
- 给出具体实施建议
"""

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self._config.system_prompt

    def select_tools(self) -> list[type[Tool]]:
        """选择设计训练需要的工具"""
        return [
            DesignAnalyzerTool,
        ]

    def create_mode_components(self) -> ModeComponents:
        """创建设计模式组件"""
        return ModeComponents(
            planner_type="design",
            planner_config={
                "focus_areas": ["structure", "relationships", "patterns"],
            },
            evaluator_type="design",
            evaluator_config={
                "check_solid": True,
                "evaluate_pattern_usage": True,
            },
        )
