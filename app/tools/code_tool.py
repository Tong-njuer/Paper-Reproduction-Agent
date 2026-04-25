"""Code execution tool with safety guardrails."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from app.tools import BaseTool, ToolResult


class CodeTool(BaseTool):
    """在受控条件下执行命令并返回结构化结果。"""

    name = "code_tool"
    description = (
        "Execute shell command with timeout and workspace controls. "
        "Args: command (required), timeout, cwd, env, allow_dangerous."
    )

    _MAX_TIMEOUT_SECONDS = 600
    _DEFAULT_TIMEOUT_SECONDS = 30

    # 常见危险命令片段，默认拦截。
    _DANGEROUS_PATTERNS = [
        "rm -rf /",
        "rm -rf ~",
        "shutdown",
        "reboot",
        "mkfs",
        "dd if=",
        "format ",
        "del /f /s /q",
        "Remove-Item -Recurse -Force",
    ]

    def execute(self, **kwargs: Any) -> ToolResult:
        command = str(kwargs.get("command", "")).strip()
        timeout = self._coerce_timeout(kwargs.get("timeout", self._DEFAULT_TIMEOUT_SECONDS))
        env = kwargs.get("env")
        allow_dangerous = bool(kwargs.get("allow_dangerous", False))

        if not command:
            return self._error("Missing required argument: command")

        if not allow_dangerous and self._is_dangerous(command):
            return self._error(
                "Blocked potentially dangerous command. Set allow_dangerous=true to override.",
                blocked=True,
                command=command,
            )

        try:
            cwd = self._resolve_cwd(kwargs.get("cwd"))
            run_env = self._build_env(env)
        except ValueError as exc:
            return self._error(str(exc), command=command)

        started = time.perf_counter()
        try:
            process = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd),
                env=run_env,
                timeout=timeout,
                capture_output=True,
                text=True,
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)

            output = (process.stdout or "").strip()
            stderr = (process.stderr or "").strip()

            metadata: Dict[str, Any] = {
                "command": command,
                "cwd": str(cwd),
                "timeout": timeout,
                "returncode": process.returncode,
                "stdout": output,
                "stderr": stderr,
                "elapsed_ms": elapsed_ms,
            }

            if process.returncode == 0:
                return self._success(output=output or "Command executed successfully.", **metadata)

            return self._error(
                f"Command failed with return code {process.returncode}.",
                **metadata,
            )

        except subprocess.TimeoutExpired as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            stdout = (exc.stdout or "").strip() if exc.stdout else ""
            stderr = (exc.stderr or "").strip() if exc.stderr else ""
            return self._error(
                f"Command timed out after {timeout} seconds.",
                command=command,
                cwd=str(cwd),
                timeout=timeout,
                stdout=stdout,
                stderr=stderr,
                elapsed_ms=elapsed_ms,
                retryable=True,
            )
        except Exception as exc:  # pragma: no cover - 防御性兜底
            return self._error(
                f"Unexpected execution error: {exc}",
                command=command,
                cwd=str(cwd),
                timeout=timeout,
            )

    def _coerce_timeout(self, value: Any) -> int:
        try:
            timeout = int(value)
        except (TypeError, ValueError):
            return self._DEFAULT_TIMEOUT_SECONDS

        if timeout <= 0:
            return self._DEFAULT_TIMEOUT_SECONDS
        return min(timeout, self._MAX_TIMEOUT_SECONDS)

    def _resolve_cwd(self, cwd: Optional[Any]) -> Path:
        if cwd is None:
            return Path.cwd()

        target = Path(str(cwd)).expanduser().resolve()
        if not target.exists() or not target.is_dir():
            raise ValueError(f"Invalid cwd: {cwd}")
        return target

    def _build_env(self, env: Optional[Any]) -> Dict[str, str]:
        if env is None:
            return dict(os.environ)

        if not isinstance(env, dict):
            raise ValueError("Argument env must be a dict[str, str]")

        merged_env = dict(os.environ)
        for key, value in env.items():
            merged_env[str(key)] = str(value)
        return merged_env

    def _is_dangerous(self, command: str) -> bool:
        lowered = command.lower()
        return any(pattern.lower() in lowered for pattern in self._DANGEROUS_PATTERNS)
