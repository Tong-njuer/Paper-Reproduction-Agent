"""Tools package.

该模块定义工具统一基类、标准返回结构与注册中心。
所有工具都应返回 ToolResult，供 ReAct/Agent 编排层消费。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Tool 执行结果的标准格式。"""

    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseTool(ABC):
    """所有工具的抽象基类。"""

    name: str = "base_tool"
    description: str = "Base tool"

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具主逻辑。"""

    def validate_args(self, **kwargs: Any) -> bool:
        """参数校验钩子，子类可重写。"""
        return True

    def _error(self, message: str, **metadata: Any) -> ToolResult:
        """统一错误返回，避免各工具重复模板代码。"""
        return ToolResult(success=False, error=message, metadata=metadata)

    def _success(self, output: Optional[str] = None, **metadata: Any) -> ToolResult:
        """统一成功返回。"""
        return ToolResult(success=True, output=output, metadata=metadata)


def _build_registry() -> Dict[str, BaseTool]:
    """构建工具注册表。

    放在函数中是为了避免包导入顺序导致的循环依赖问题。
    """

    from app.tools.code_tool import CodeTool
    from app.tools.doc_tool import DocTool
    from app.tools.learning_path_tool import LearningPathTool
    from app.tools.paper_tool import PaperTool
    from app.tools.repo_index_tool import RepoIndexTool
    from app.tools.sandbox_tool import SandboxTool
    from app.tools.schedule_tool import ScheduleTool
    from app.tools.source_tool import SourceTool
    from app.tools.test_tool import TestTool
    from app.tools.wiki_tool import WikiTool

    return {
        "paper_tool": PaperTool(),
        "source_tool": SourceTool(),
        "repo_index_tool": RepoIndexTool(),
        "sandbox_tool": SandboxTool(),
        "test_tool": TestTool(),
        "doc_tool": DocTool(),
        "code_tool": CodeTool(),
        "wiki_tool": WikiTool(),
        "schedule_tool": ScheduleTool(),
        "learning_path_tool": LearningPathTool(),
    }


TOOL_REGISTRY: Dict[str, BaseTool] = _build_registry()


def register_tool(tool: BaseTool, overwrite: bool = False) -> None:
    """注册新工具。

    Args:
        tool: 工具实例
        overwrite: 已存在同名工具时是否覆盖
    """

    if tool.name in TOOL_REGISTRY and not overwrite:
        raise ValueError(f"Tool already exists: {tool.name}")
    TOOL_REGISTRY[tool.name] = tool


def get_tool(tool_name: str) -> Optional[BaseTool]:
    """按名称获取工具。"""
    return TOOL_REGISTRY.get(tool_name)


def list_available_tools() -> Dict[str, str]:
    """获取所有可用工具及描述。"""
    return {name: tool.description for name, tool in TOOL_REGISTRY.items()}


__all__ = [
    "BaseTool",
    "ToolResult",
    "TOOL_REGISTRY",
    "register_tool",
    "get_tool",
    "list_available_tools",
]
