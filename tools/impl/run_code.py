# ============================================================
# RunCodeTool - 代码执行工具
# ============================================================
"""
run_code 工具实现。

功能：
- 在隔离环境中执行代码
- 支持多种语言
- 超时控制
- 错误捕获和输出

使用Docker实现隔离执行。
"""

import time
from dataclasses import dataclass
from typing import Any

from tools.base import Tool, ToolParameter, ParameterType, ToolResult


@dataclass
class CodeExecutionConfig:
    """代码执行配置"""
    language: str = "python"
    timeout_seconds: int = 30
    memory_limit_mb: int = 256
    enable_network: bool = False


class RunCodeTool(Tool):
    """
    代码执行工具

    在隔离环境中执行代码。
    目前支持 Python，后续可扩展其他语言。

    设计考虑：
    - 使用Docker容器实现隔离
    - 支持超时控制
    - 捕获stdout/stderr
    - 返回执行结果和错误信息
    """

    def __init__(self, docker_runner: Any = None):
        """
        初始化run_code工具

        Args:
            docker_runner: Docker执行器实例（可选）
        """
        self.docker_runner = docker_runner

    @property
    def name(self) -> str:
        return "run_code"

    @property
    def description(self) -> str:
        return (
            "在隔离环境中执行代码。支持Python等多种语言。"
            "返回代码的输出结果或错误信息。"
            "用于验证代码正确性。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="code",
                description="要执行的代码",
                param_type=ParameterType.CODE,
                required=True,
            ),
            ToolParameter(
                name="language",
                description="编程语言 (python/java/javascript/go)",
                param_type=ParameterType.STRING,
                required=False,
                default="python",
                enum_values=["python", "java", "javascript", "go"],
            ),
            ToolParameter(
                name="timeout",
                description="超时时间（秒）",
                param_type=ParameterType.INTEGER,
                required=False,
                default=30,
                min_value=1,
                max_value=300,
            ),
            ToolParameter(
                name="test_input",
                description="标准输入数据（可选）",
                param_type=ParameterType.STRING,
                required=False,
            ),
        ]

    @property
    def examples(self) -> list[dict[str, Any]]:
        return [
            {
                "description": "执行Python代码",
                "code": "print('Hello, World!')",
                "language": "python",
            },
            {
                "description": "执行带输入的代码",
                "code": "n = int(input())\nprint(n * 2)",
                "language": "python",
                "test_input": "5",
            },
        ]

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: int = 30,
        test_input: str | None = None,
        **kwargs
    ) -> ToolResult:
        """
        执行代码

        Args:
            code: 要执行的代码
            language: 编程语言
            timeout: 超时时间
            test_input: 标准输入

        Returns:
            ToolResult: 执行结果
        """
        start_time = time.time()

        # 如果没有Docker运行器，使用模拟执行
        if self.docker_runner is None:
            return await self._execute_mock(code, language, test_input, start_time)

        try:
            # 使用Docker执行
            result = await self.docker_runner.run(
                code=code,
                language=language,
                timeout=timeout,
                stdin=test_input,
            )

            execution_time = (time.time() - start_time) * 1000

            if result.success:
                return ToolResult.success_result(
                    output=result.output,
                    execution_time_ms=execution_time,
                    language=language,
                )
            else:
                return ToolResult.error_result(
                    error=result.error or "Execution failed",
                    output=result.output or "",
                    execution_time_ms=execution_time,
                    language=language,
                )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            return ToolResult.error_result(
                error=f"Execution error: {str(e)}",
                execution_time_ms=execution_time,
            )

    async def _execute_mock(
        self,
        code: str,
        language: str,
        test_input: str | None,
        start_time: float,
    ) -> ToolResult:
        """
        模拟执行（用于测试或无Docker环境）

        注意：实际使用时应使用真实的Docker执行器。
        """
        # 简化实现：直接尝试执行Python代码
        import io
        import sys

        execution_time = None

        try:
            if language == "python":
                # 重定向输出
                old_stdout = sys.stdout
                old_stderr = sys.stderr
                sys.stdout = io.StringIO()
                sys.stderr = io.StringIO()

                try:
                    exec(code, {"__name__": "__main__"})
                    output = sys.stdout.getvalue()
                    error_output = sys.stderr.getvalue()
                finally:
                    sys.stdout = old_stdout
                    sys.stderr = old_stderr

                execution_time = (time.time() - start_time) * 1000

                if error_output:
                    return ToolResult.error_result(
                        error=error_output,
                        output=output,
                        execution_time_ms=execution_time,
                    )

                return ToolResult.success_result(
                    output=output or "Code executed (no output)",
                    execution_time_ms=execution_time,
                )
            else:
                execution_time = (time.time() - start_time) * 1000
                return ToolResult.error_result(
                    error=f"Unsupported language: {language}",
                    execution_time_ms=execution_time,
                )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            return ToolResult.error_result(
                error=f"{type(e).__name__}: {str(e)}",
                execution_time_ms=execution_time,
            )
