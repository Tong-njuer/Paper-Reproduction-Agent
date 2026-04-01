# ============================================================
# ProjectMode - 项目引导模式
# ============================================================
"""
项目引导模式实现。

训练流程：
1. 理解项目需求和目标
2. 进行技术选型讨论
3. 制定项目计划
4. 逐步实现功能模块
5. 进行代码整合
6. 测试和修复
7. 项目总结

评估重点：
- 需求理解完整性
- 架构设计合理性
- 模块划分清晰度
- 代码组织规范性
"""

from agent.modes.base import (
    ModeConfig,
    ModeComponents,
    TrainingMode,
)
from tools.base import Tool
from tools.impl.project_planner import ProjectPlannerTool
from tools.impl.run_code import RunCodeTool


class ProjectMode(TrainingMode):
    """
    项目引导模式

    指导用户从零开始完成一个完整的项目。
    强调系统化思维和工程实践。
    """

    def _create_config(self) -> ModeConfig:
        """创建项目模式配置"""
        return ModeConfig(
            mode_name="project",
            display_name="项目引导",
            description="从0到1逐步完成完整项目，学习项目工程实践",
            system_prompt=self._get_default_system_prompt(),
            user_prompt_template="{task}",
            required_tools=["project_planner", "run_code"],
            optional_tools=["code_linter", "generate_tests"],
            max_iterations=20,
            timeout_seconds=900,  # 15分钟
            evaluation_criteria={
                "functionality_complete": 0.9,  # 功能完整性
                "code_organization": 0.8,        # 代码组织
                "documentation": 0.7,            # 文档
            },
            tags=["project", "engineering", "fullstack"],
        )

    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词"""
        return """你是一个专业的项目教练Agent。

你的职责是指导用户完成一个完整的项目。

训练流程：
1. 需求分析
   - 理解项目目标和需求
   - 识别核心功能和优先级
   - 确认技术约束

2. 项目规划
   - 确定技术栈
   - 制定里程碑
   - 拆分任务模块

3. 逐步实现
   - 从核心功能开始
   - 每步完成可运行的部分
   - 及时测试和修复

4. 代码整合
   - 确保模块间协作正常
   - 统一代码风格
   - 添加必要注释

5. 项目收尾
   - 功能验证
   - 代码优化
   - 编写README

工程实践要点：
- 保持代码简洁
- 模块间低耦合
- 及时测试
- 记录决策

每次只推进一个模块，完成后再进行下一步。
"""

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self._config.system_prompt

    def select_tools(self) -> list[type[Tool]]:
        """选择项目引导需要的工具"""
        return [
            ProjectPlannerTool,
            RunCodeTool,
        ]

    def create_mode_components(self) -> ModeComponents:
        """创建项目模式组件"""
        return ModeComponents(
            planner_type="project",
            planner_config={
                "milestone_based": True,
                "task_size": "small",  # 小任务分块
            },
            evaluator_type="project",
            evaluator_config={
                "check_functionality": True,
                "check_organization": True,
            },
        )
