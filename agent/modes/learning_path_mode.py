# ============================================================
# LearningPathMode - 学习路径模式
# ============================================================
"""
学习路径模式实现。

训练流程：
1. 评估用户当前水平
2. 了解学习目标
3. 制定长期学习计划
4. 规划阶段性任务
5. 跟踪学习进度
6. 适时调整计划

评估重点：
- 目标合理性
- 计划可行性
- 学习进度
- 能力提升
"""

from agent.modes.base import (
    ModeConfig,
    ModeComponents,
    TrainingMode,
)
from tools.base import Tool
from tools.impl.project_planner import ProjectPlannerTool


class LearningPathMode(TrainingMode):
    """
    学习路径模式

    为用户提供长期的学习规划和指导。
    强调目标导向和循序渐进。
    """

    def _create_config(self) -> ModeConfig:
        """创建学习路径模式配置"""
        return ModeConfig(
            mode_name="learning_path",
            display_name="学习路径",
            description="制定个性化学习计划，长期提升编程能力",
            system_prompt=self._get_default_system_prompt(),
            user_prompt_template="{task}",
            required_tools=["project_planner"],
            optional_tools=[],
            max_iterations=5,  # 规划模式不需要太多迭代
            timeout_seconds=120,
            evaluation_criteria={
                "plan_feasibility": 0.9,     # 计划可行性
                "goal_clarity": 0.9,         # 目标清晰度
                "milestone_appropriateness": 0.8,  # 里程碑恰当性
            },
            tags=["learning", "planning", "career", "path"],
        )

    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词"""
        return """你是一个专业的编程学习规划师Agent。

你的职责是帮助用户制定长期的学习计划。

规划流程：
1. 水平评估
   - 了解用户当前技术水平
   - 识别优势和短板
   - 确定起点

2. 目标设定
   - 了解学习目标
   - 区分短期和长期目标
   - 确保目标具体可衡量

3. 路径规划
   - 确定需要掌握的知识点
   - 推荐学习顺序
   - 安排实践项目

4. 里程碑设置
   - 设置阶段性目标
   - 确定检验标准
   - 预留缓冲时间

5. 资源推荐
   - 推荐学习资料
   - 建议练习项目
   - 提供学习方法

技能领域：
- 编程基础（语法、控制结构、函数）
- 数据结构与算法
- 面向对象编程
- 设计模式
- 架构设计
- 数据库
- 网络基础
- 测试
- DevOps

学习原则：
- 循序渐进，不要好高骛远
- 理论结合实践
- 定期回顾总结
- 保持学习连贯性

每次规划后：
- 确保计划可行
- 设定检查点
- 准备调整空间
"""

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self._config.system_prompt

    def select_tools(self) -> list[type[Tool]]:
        """选择学习路径规划需要的工具"""
        return [
            ProjectPlannerTool,
        ]

    def create_mode_components(self) -> ModeComponents:
        """创建学习路径模式组件"""
        return ModeComponents(
            planner_type="learning_path",
            planner_config={
                "long_term": True,
                "milestone_based": True,
            },
            evaluator_type="learning_path",
            evaluator_config={
                "check_feasibility": True,
            },
        )
