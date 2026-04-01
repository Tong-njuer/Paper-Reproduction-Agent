# ============================================================
# Execution 基类
# ============================================================
"""
代码执行器基类。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    output: str
    error: str | None = None
    exit_code: int = 0


class CodeRunner(ABC):
    """代码执行器抽象基类"""

    @abstractmethod
    async def run(
        self,
        code: str,
        language: str,
        timeout: int = 30,
        stdin: str | None = None,
    ) -> ExecutionResult:
        """
        执行代码

        Args:
            code: 代码
            language: 语言
            timeout: 超时时间
            stdin: 标准输入

        Returns:
            ExecutionResult: 执行结果
        """
        pass
