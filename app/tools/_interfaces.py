"""
未来工具的接口占位。

当需要扩展复现功能时，在此实现以下工具:
  - CloneRepoTool: 克隆源码仓库到本地沙箱
  - AnalyzeRepoTool: 分析仓库结构（依赖、入口点、测试）
  - SandboxTool: 创建隔离的复现环境
  - RunTestTool: 执行复现测试并比较指标
  - DocGenTool: 生成复现报告

每个工具需继承 BaseTool，实现 execute(**kwargs) -> ToolResult。
注册方式: 在 app/tools/__init__.py 的 _build_registry() 中添加。
"""

from app.tools import BaseTool, ToolResult


class AnalyzeRepoTool(BaseTool):
    """分析仓库结构和依赖"""
    name = "analyze_tool"
    description = "分析代码仓库结构。参数: repo_path(仓库路径)"

    def execute(self, repo_path: str = ".", **kwargs) -> ToolResult:
        raise NotImplementedError("AnalyzeRepoTool 待实现")


class SandboxTool(BaseTool):
    """创建复现环境"""
    name = "sandbox_tool"
    description = "创建隔离环境。参数: project_path(项目路径)"

    def execute(self, project_path: str = "", **kwargs) -> ToolResult:
        raise NotImplementedError("SandboxTool 待实现")


class RunTestTool(BaseTool):
    """运行复现测试"""
    name = "test_tool"
    description = "运行测试。参数: project_path(项目路径)"

    def execute(self, project_path: str = ".", **kwargs) -> ToolResult:
        raise NotImplementedError("RunTestTool 待实现")


class DocGenTool(BaseTool):
    """生成复现报告"""
    name = "doc_tool"
    description = "生成复现报告。参数: goal(目标), output_path(输出路径)"

    def execute(self, goal: str = "", output_path: str = "./report.md", **kwargs) -> ToolResult:
        raise NotImplementedError("DocGenTool 待实现")
