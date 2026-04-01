# ============================================================
# ProjectPlannerTool - 项目规划工具
# ============================================================
"""
project_planner 工具实现。

功能：
- 分析项目需求
- 拆解任务
- 制定计划
- 估算工作量
"""

from typing import Any

from tools.base import Tool, ToolParameter, ParameterType, ToolResult


class ProjectPlannerTool(Tool):
    """
    项目规划工具

    帮助分析和规划项目：
    - 需求理解
    - 任务拆分
    - 里程碑设置
    - 工作量估算
    """

    @property
    def name(self) -> str:
        return "project_planner"

    @property
    def description(self) -> str:
        return (
            "分析和规划项目，将大任务拆分为可执行的小任务，"
            "制定里程碑计划，估算工作量。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="project_description",
                description="项目描述或需求",
                param_type=ParameterType.STRING,
                required=True,
            ),
            ToolParameter(
                name="constraints",
                description="约束条件（如时间、技术栈）",
                param_type=ParameterType.STRING,
                required=False,
            ),
            ToolParameter(
                name="planning_level",
                description="规划详细程度",
                param_type=ParameterType.STRING,
                required=False,
                default="medium",
                enum_values=["high", "medium", "low"],
            ),
        ]

    async def execute(
        self,
        project_description: str,
        constraints: str | None = None,
        planning_level: str = "medium",
        **kwargs
    ) -> ToolResult:
        """
        规划项目

        Args:
            project_description: 项目描述
            constraints: 约束条件
            planning_level: 规划详细程度

        Returns:
            ToolResult: 项目计划
        """
        try:
            result = await self._create_plan(
                project_description=project_description,
                constraints=constraints,
                planning_level=planning_level,
            )

            return ToolResult.success_result(
                output=result,
                metadata={"planning_level": planning_level},
            )

        except Exception as e:
            return ToolResult.error_result(
                error=f"Planning error: {str(e)}"
            )

    async def _create_plan(
        self,
        project_description: str,
        constraints: str | None,
        planning_level: str,
    ) -> str:
        """创建项目计划"""
        # TODO: 实现真实的项目规划
        # 使用LLM分析需求，生成合理的任务拆分

        lines = [
            "## 项目计划",
            "",
            f"**项目描述**: {project_description}",
            "",
            f"**约束条件**: {constraints or '无特殊限制'}",
            "",
            "---",
            "",
            "### 阶段划分",
            "",
            "#### 阶段1: 需求分析和设计",
            "- 详细需求分析",
            "- 技术选型",
            "- 架构设计",
            "- 预计时长: 1-2天",
            "",
            "#### 阶段2: 核心功能开发",
            "- 搭建项目框架",
            "- 实现核心模块",
            "- 预计时长: 3-5天",
            "",
            "#### 阶段3: 功能完善和测试",
            "- 功能开发",
            "- 单元测试",
            "- 集成测试",
            "- 预计时长: 2-3天",
            "",
            "#### 阶段4: 优化和部署",
            "- 性能优化",
            "- 文档编写",
            "- 部署上线",
            "- 预计时长: 1-2天",
            "",
            "### 任务列表",
            "",
            "| ID | 任务 | 优先级 | 预计工时 | 依赖 |",
            "|----|------|--------|----------|------|",
            "| 1 | 需求分析 | 高 | 4h | - |",
            "| 2 | 技术选型 | 高 | 2h | 1 |",
            "| 3 | 架构设计 | 高 | 4h | 2 |",
            "| 4 | 项目搭建 | 中 | 2h | 3 |",
            "",
            "### 总预计工时: 约1-2周",
        ]

        return "\n".join(lines)
