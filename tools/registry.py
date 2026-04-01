# ============================================================
# ToolRegistry - 工具注册器
# ============================================================
"""
工具注册器。

设计思路：
- 统一的工具管理
- 支持按名称查找
- 工具调用日志
- 可扩展的注册机制
"""

from typing import Any

from tools.base import Tool, ToolResult


class ToolRegistry:
    """
    工具注册器

    管理所有可用的工具。

    功能：
    - 注册/注销工具
    - 按名称获取工具
    - 列出所有工具
    - 验证工具存在
    """

    def __init__(self):
        """初始化注册器"""
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        注册工具

        Args:
            tool: 工具实例

        Raises:
            TypeError: 如果tool不是Tool实例
            ValueError: 如果工具名称已存在
        """
        if not isinstance(tool, Tool):
            raise TypeError(
                f"Tool must be instance of Tool, got {type(tool).__name__}"
            )

        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")

        self._tools[tool.name] = tool

    def register_class(self, tool_class: type[Tool]) -> Tool:
        """
        注册工具类（自动实例化）

        Args:
            tool_class: 工具类

        Returns:
            Tool: 实例化的工具
        """
        tool_instance = tool_class()
        self.register(tool_instance)
        return tool_instance

    def unregister(self, name: str) -> bool:
        """
        注销工具

        Args:
            name: 工具名称

        Returns:
            bool: 是否成功注销
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_tool(self, name: str) -> Tool | None:
        """
        获取工具

        Args:
            name: 工具名称

        Returns:
            Tool: 工具实例，不存在返回None
        """
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """
        检查工具是否存在

        Args:
            name: 工具名称

        Returns:
            bool: 是否存在
        """
        return name in self._tools

    def list_tools(self) -> list[str]:
        """
        列出所有工具名称

        Returns:
            list[str]: 工具名称列表
        """
        return list(self._tools.keys())

    def get_tool_info(self, name: str) -> dict[str, Any] | None:
        """
        获取工具信息

        Args:
            name: 工具名称

        Returns:
            dict: 工具信息（名称、描述、参数等）
        """
        tool = self.get_tool(name)
        if tool is None:
            return None

        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": [
                {
                    "name": p.name,
                    "description": p.description,
                    "type": p.param_type.value,
                    "required": p.required,
                }
                for p in tool.parameters
            ],
            "examples": tool.examples,
        }

    async def execute_tool(
        self, name: str, **kwargs
    ) -> ToolResult:
        """
        执行工具

        快捷方法：获取工具并执行。

        Args:
            name: 工具名称
            **kwargs: 参数

        Returns:
            ToolResult: 执行结果
        """
        tool = self.get_tool(name)
        if tool is None:
            return ToolResult.error_result(f"Tool not found: {name}")

        # 验证参数
        is_valid, error = tool.validate_params(**kwargs)
        if not is_valid:
            return ToolResult.error_result(f"Invalid parameters: {error}")

        return await tool.execute(**kwargs)

    def __contains__(self, name: str) -> bool:
        """支持 'in' 操作符"""
        return name in self._tools

    def __len__(self) -> int:
        """支持 len() 操作符"""
        return len(self._tools)

    def __repr__(self) -> str:
        return f"<ToolRegistry: {len(self._tools)} tools>"


# ============================================================
# 全局注册表
# ============================================================

# 创建全局工具注册表实例
_global_registry: ToolRegistry | None = None


def get_global_registry() -> ToolRegistry:
    """
    获取全局工具注册表

    Returns:
        ToolRegistry: 全局注册表
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
        _register_default_tools(_global_registry)
    return _global_registry


def _register_default_tools(registry: ToolRegistry) -> None:
    """注册默认工具"""
    # 延迟导入，避免循环依赖
    from tools.impl.run_code import RunCodeTool
    from tools.impl.generate_tests import GenerateTestsTool
    from tools.impl.analyze_error import AnalyzeErrorTool
    from tools.impl.code_linter import CodeLinterTool
    from tools.impl.design_analyzer import DesignAnalyzerTool
    from tools.impl.project_planner import ProjectPlannerTool

    # 注册默认工具
    registry.register_class(RunCodeTool)
    registry.register_class(GenerateTestsTool)
    registry.register_class(AnalyzeErrorTool)
    registry.register_class(CodeLinterTool)
    registry.register_class(DesignAnalyzerTool)
    registry.register_class(ProjectPlannerTool)
