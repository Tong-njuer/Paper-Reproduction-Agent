# ============================================================
# Executor - 执行任务
# ============================================================
"""
Executor负责实际执行任务和工具调用。

职责：
1. 管理工具调用
2. 处理执行结果
3. 维护执行状态
4. 错误处理和重试

设计思路：
- Executor专注于"执行"，不负责思考决策
- 与工具层解耦，通过ToolRegistry获取工具
- 支持超时控制和错误重试
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from tools.base import ToolResult
from tools.registry import ToolRegistry


@dataclass
class ExecutionContext:
    """
    执行上下文

    包含执行所需的环境信息。
    """
    trace_id: str                      # Trace ID
    step_id: str                       # 当前步骤ID
    user_id: str                       # 用户ID
    session_id: str                    # 会话ID
    metadata: dict[str, Any]          # 附加数据


class Executor(ABC):
    """
    Executor抽象基类

    定义任务执行的通用接口。

    设计原则：
    - 执行器与推理解耦
    - 统一的错误处理
    - 详细的执行日志
    """

    def __init__(self, tool_registry: ToolRegistry):
        """
        初始化Executor

        Args:
            tool_registry: 工具注册器，用于获取工具实例
        """
        self.tool_registry = tool_registry
        self._execution_history: list[ExecutionRecord] = []

    async def execute(
        self,
        action: str,
        params: dict[str, Any],
        context: ExecutionContext | None = None,
    ) -> ToolResult:
        """
        执行动作

        主入口方法，执行指定的工具调用：
        1. 查找工具
        2. 调用执行
        3. 记录日志
        4. 返回结果

        Args:
            action: 动作名称（工具名）
            params: 动作参数
            context: 执行上下文（可选）

        Returns:
            ToolResult: 执行结果
        """
        # 1. 获取工具
        tool = self.tool_registry.get_tool(action)
        if tool is None:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool not found: {action}",
                metadata={},
            )

        # 2. 记录执行开始
        record = ExecutionRecord(
            tool_name=action,
            params=params,
            context=context,
            started_at=self._get_current_time(),
        )

        try:
            # 3. 执行工具
            result = await self._execute_tool(tool, params)

            # 4. 记录完成
            record.completed_at = self._get_current_time()
            record.result = result
            record.success = result.success

            return result

        except Exception as e:
            # 错误处理
            record.completed_at = self._get_current_time()
            record.error = str(e)
            record.success = False

            return ToolResult(
                success=False,
                output="",
                error=f"Execution error: {str(e)}",
                metadata={"exception": type(e).__name__},
            )

        finally:
            # 保存执行记录
            self._execution_history.append(record)

    async def _execute_tool(
        self,
        tool: Any,  # Tool基类
        params: dict[str, Any],
    ) -> ToolResult:
        """
        执行单个工具

        可被子类重写以定制执行行为（如重试、超时等）。

        Args:
            tool: 工具实例
            params: 参数

        Returns:
            ToolResult: 执行结果
        """
        return await tool.execute(**params)

    @property
    def execution_history(self) -> list["ExecutionRecord"]:
        """获取执行历史"""
        return self._execution_history.copy()

    @staticmethod
    def _get_current_time():
        """获取当前时间"""
        from datetime import datetime
        return datetime.now()


@dataclass
class ExecutionRecord:
    """
    执行记录

    记录一次工具调用的完整信息。
    用于日志、分析和调试。
    """
    tool_name: str                     # 工具名
    params: dict[str, Any]             # 调用参数
    context: ExecutionContext | None   # 执行上下文
    started_at: Any                    # 开始时间
    completed_at: Any | None = None    # 完成时间
    result: ToolResult | None = None   # 执行结果
    error: str | None = None           # 错误信息
    success: bool = False              # 是否成功

    @property
    def duration(self) -> float | None:
        """获取执行耗时（秒）"""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
