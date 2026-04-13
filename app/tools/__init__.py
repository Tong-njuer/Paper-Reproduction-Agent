# ============================================================
# Tools Package (Reserved for Implementation)
# ============================================================
# 此包预留用于工具实现。
# 工具是 Agent 可以执行的操作。
#
# Planned Tools:
#   - code_tool: 代码执行和测试
#   - wiki_tool: Wikipedia/文档查找
#   - schedule_tool: 计划管理
#   - learning_path_tool: 学习路径规划
#
# Currently: Placeholder only, tools not implemented
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel


class ToolResult(BaseModel):
    """
    Standardized result format for all tool executions.

    Attributes:
        success: Whether the tool execution succeeded
        output: The output data if successful
        error: Error message if failed
        metadata: Additional execution metadata
    """
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}


class BaseTool(ABC):
    """
    Abstract base class for all tools.

    All tool implementations must inherit from this class
    and implement the execute method.
    """

    # Tool metadata - override in subclasses
    name: str = "base_tool"
    description: str = "Base tool placeholder"

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with given arguments.

        Args:
            **kwargs: Tool-specific arguments

        Returns:
            ToolResult: Standardized result object
        """
        pass

    def validate_args(self, **kwargs) -> bool:
        """
        Validate input arguments before execution.

        Args:
            **kwargs: Arguments to validate

        Returns:
            bool: True if arguments are valid
        """
        return True


# ============================================================
# Placeholder implementations - to be expanded later
# ============================================================

class CodeToolPlaceholder(BaseTool):
    """Placeholder for code execution tool"""
    name = "code_tool"
    description = "Execute code and return results"

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=False,
            error="CodeTool not yet implemented - reserved for future development"
        )


class WikiToolPlaceholder(BaseTool):
    """Placeholder for wiki/documentation lookup tool"""
    name = "wiki_tool"
    description = "Search and retrieve documentation"

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=False,
            error="WikiTool not yet implemented - reserved for future development"
        )


class ScheduleToolPlaceholder(BaseTool):
    """Placeholder for schedule management tool"""
    name = "schedule_tool"
    description = "Manage schedules and timelines"

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=False,
            error="ScheduleTool not yet implemented - reserved for future development"
        )


class LearningPathToolPlaceholder(BaseTool):
    """Placeholder for learning path planning tool"""
    name = "learning_path_tool"
    description = "Plan and track learning paths"

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=False,
            error="LearningPathTool not yet implemented - reserved for future development"
        )


# ============================================================
# Tool Registry
# ============================================================
# Central registry for all available tools.
# Add new tools here as they are implemented.

TOOL_REGISTRY: Dict[str, BaseTool] = {
    "code_tool": CodeToolPlaceholder(),
    "wiki_tool": WikiToolPlaceholder(),
    "schedule_tool": ScheduleToolPlaceholder(),
    "learning_path_tool": LearningPathToolPlaceholder(),
}


def get_tool(tool_name: str) -> Optional[BaseTool]:
    """
    Retrieve a tool by name from the registry.

    Args:
        tool_name: Name of the tool to retrieve

    Returns:
        BaseTool if found, None otherwise
    """
    return TOOL_REGISTRY.get(tool_name)


def list_available_tools() -> Dict[str, str]:
    """
    List all available tools and their descriptions.

    Returns:
        Dict mapping tool names to descriptions
    """
    return {name: tool.description for name, tool in TOOL_REGISTRY.items()}
