# ============================================================
# RefactorMode - 重构模式
# ============================================================
"""
重构模式实现。

训练流程：
1. 分析现有代码
2. 识别代码坏味道
3. 制定重构计划
4. 实施重构（小步进行）
5. 确保测试通过
6. 验证改进效果

评估重点：
- 坏味道识别准确性
- 重构策略合理性
- 测试覆盖率保持
- 改进效果
"""

from agent.modes.base import (
    ModeConfig,
    ModeComponents,
    TrainingMode,
)
from tools.base import Tool
from tools.impl.code_linter import CodeLinterTool
from tools.impl.analyze_error import AnalyzeErrorTool
from tools.impl.run_code import RunCodeTool


class RefactorMode(TrainingMode):
    """
    重构模式

    帮助用户改进现有代码的质量。
    强调渐进式改进和测试保障。
    """

    def _create_config(self) -> ModeConfig:
        """创建重构模式配置"""
        return ModeConfig(
            mode_name="refactor",
            display_name="代码重构",
            description="识别代码问题，学习重构技巧，提升代码质量",
            system_prompt=self._get_default_system_prompt(),
            user_prompt_template="{task}",
            required_tools=["code_linter", "run_code"],
            optional_tools=["analyze_error"],
            max_iterations=10,
            timeout_seconds=300,
            evaluation_criteria={
                "bad_smells_removed": 0.8,   # 坏味道消除率
                "tests_kept_passing": True,   # 测试保持通过
                "quality_improvement": 0.3,  # 质量提升幅度
            },
            tags=["refactor", "code quality", "clean code"],
        )

    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词"""
        return """你是一个专业的代码重构教练Agent。

你的职责是帮助用户改进现有代码的质量。

重构原则：
1. 小步进行
   - 每次只做一个改动
   - 每次重构后运行测试
   - 确保代码始终可运行

2. 有测试保障
   - 重构前确保有测试
   - 重构后测试必须通过
   - 不要删除测试

3. 渐进式改进
   - 先处理明显的坏味道
   - 再优化整体结构
   - 最后提升代码优雅度

常见代码坏味道：
- Long Method（过长方法）
- Large Class（过大类）
- Duplicate Code（重复代码）
- Long Parameter List（过长参数列表）
- Divergent Change（发散式变化）
- Shotgun Surgery（霰弹式修改）
- Feature Envy（特性依恋）
- Data Clumps（数据泥团）
- Primitive Obsession（基本类型偏执）
- Switch Statements（switch语句）
- Parallel Inheritance（平行继承）
- Lazy Class（冗余类）
- Speculative Generality（夸夸其谈的未来性）

重构技巧：
- Extract Method（提取方法）
- Inline Method（内联方法）
- Extract Variable（提取变量）
- Move Method（移动方法）
- Rename（重命名）
- Introduce Parameter Object（引入参数对象）

每次重构后：
- 运行测试验证
- 确认改进效果
- 解释改进了什么
"""

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self._config.system_prompt

    def select_tools(self) -> list[type[Tool]]:
        """选择重构需要的工具"""
        return [
            CodeLinterTool,
            AnalyzeErrorTool,
            RunCodeTool,
        ]

    def create_mode_components(self) -> ModeComponents:
        """创建重构模式组件"""
        return ModeComponents(
            planner_type="refactor",
            planner_config={
                "small_steps": True,
                "test_first": True,
            },
            evaluator_type="refactor",
            evaluator_config={
                "check_smells_removed": True,
                "require_tests_pass": True,
            },
            reflector_type="refactor",
            reflector_config={
                "focus_on_patterns": True,
            },
        )
