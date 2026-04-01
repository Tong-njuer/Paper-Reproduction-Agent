# ============================================================
# DockerRunner - Docker代码执行器
# ============================================================
"""
Docker代码执行器。

在Docker容器中隔离执行代码。
"""

import docker
from dataclasses import dataclass

from execution.base import CodeRunner, ExecutionResult


class DockerRunner(CodeRunner):
    """
    Docker代码执行器

    使用Docker容器执行代码，确保隔离性。

    注意：
    - 需要Docker守护进程运行
    - 容器使用后会被删除
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        timeout: int = 30,
    ):
        """
        初始化Docker运行器

        Args:
            image: Docker镜像
            timeout: 默认超时时间
        """
        self.image = image
        self.timeout = timeout
        self._client = None

    @property
    def client(self) -> docker.DockerClient:
        """获取Docker客户端"""
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    async def run(
        self,
        code: str,
        language: str,
        timeout: int = 30,
        stdin: str | None = None,
    ) -> ExecutionResult:
        """
        在Docker容器中执行代码

        Args:
            code: 代码
            language: 语言
            timeout: 超时
            stdin: 输入

        Returns:
            ExecutionResult: 结果
        """
        # 根据语言选择执行命令
        cmd = self._get_command(language, code)

        try:
            # 启动容器
            container = self.client.containers.run(
                image=self.image,
                command=cmd,
                detach=True,
                mem_limit="256m",
                cpu_period=100000,
                cpu_quota=50000,  # 50% CPU
            )

            # 等待执行结果
            try:
                result = container.wait(timeout=timeout)
                output = container.logs().decode("utf-8")

                return ExecutionResult(
                    success=result["StatusCode"] == 0,
                    output=output,
                    exit_code=result["StatusCode"],
                )
            finally:
                # 清理容器
                container.remove(force=True)

        except docker.errors.NotFound:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Docker image not found: {self.image}",
            )
        except docker.errors.APIError as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Docker API error: {str(e)}",
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution error: {str(e)}",
            )

    def _get_command(self, language: str, code: str) -> str:
        """获取执行命令"""
        # TODO: 实现更多语言的支持
        if language == "python":
            import base64
            encoded = base64.b64encode(code.encode()).decode()
            return f"python -c \"import base64; exec(base64.b64decode('{encoded}').decode())\""
        elif language == "javascript":
            return f"node -e '{code}'"
        else:
            return f"echo 'Unsupported language: {language}'"
