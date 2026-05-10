from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ToolResult:
    def __init__(self, success: bool, output: str = "", error: str = "",
                 metadata: Dict[str, Any] = None):
        self.success = success
        self.output = output
        self.error = error
        self.metadata = metadata or {}


class BaseTool(ABC):
    name: str = "base"
    description: str = "Base tool"

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        ...

    def _ok(self, output: str = "", **meta) -> ToolResult:
        return ToolResult(success=True, output=output, metadata=meta)

    def _fail(self, error: str, **meta) -> ToolResult:
        return ToolResult(success=False, error=error, metadata=meta)


TOOL_REGISTRY: Dict[str, BaseTool] = {}


def register_tool(tool: BaseTool, overwrite: bool = False):
    if tool.name in TOOL_REGISTRY and not overwrite:
        raise ValueError(f"Tool already registered: {tool.name}")
    TOOL_REGISTRY[tool.name] = tool


def get_tool(name: str) -> Optional[BaseTool]:
    return TOOL_REGISTRY.get(name)


def list_available_tools() -> Dict[str, str]:
    return {name: t.description for name, t in TOOL_REGISTRY.items()}


def _build_registry():
    from app.tools.search_tool import SearchTool
    from app.tools.fetch_tool import FetchTool
    from app.tools.source_tool import SourceTool
    from app.tools.clone_tool import CloneRepoTool
    from app.tools.setup_tool import SetupTool
    from app.tools.execute_tool import ExecuteTool
    from app.tools.execution_steps import ReadRepoTool, PlanRunTool, RunTool
    from app.tools.execute_session_tool import ExecuteSessionTool
    from app.tools.error_handler_tool import ErrorHandlerTool
    from app.tools._interfaces import ReportTool

    register_tool(SearchTool())
    register_tool(FetchTool())
    register_tool(SourceTool())
    register_tool(CloneRepoTool())
    register_tool(SetupTool())
    register_tool(ExecuteTool())
    register_tool(ReadRepoTool())
    register_tool(PlanRunTool())
    register_tool(RunTool())
    register_tool(ExecuteSessionTool())
    register_tool(ErrorHandlerTool())
    register_tool(ReportTool())


_build_registry()
