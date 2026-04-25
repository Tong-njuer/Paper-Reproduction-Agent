"""Testing and validation execution tool."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

from app.tools import BaseTool, ToolResult


class TestTool(BaseTool):
    """执行静态检查、单测、烟雾测试与指标对比。"""

    name = "test_tool"
    description = (
        "Run validation commands for reproduction. "
        "Actions: run_command, run_static_checks, run_unit_tests, run_smoke_test, compare_metrics."
    )

    _DEFAULT_TIMEOUT_SECONDS = 300

    def execute(self, **kwargs: Any) -> ToolResult:
        action = str(kwargs.get("action", "run_command")).strip().lower()
        handlers = {
            "run_command": self._run_command,
            "run_static_checks": self._run_static_checks,
            "run_unit_tests": self._run_unit_tests,
            "run_smoke_test": self._run_smoke_test,
            "compare_metrics": self._compare_metrics,
        }

        handler = handlers.get(action)
        if handler is None:
            return self._error(
                f"Unsupported action: {action}",
                supported_actions=sorted(handlers.keys()),
            )

        try:
            return handler(kwargs)
        except Exception as exc:  # pragma: no cover
            return self._error(f"Test tool failed: {exc}", action=action)

    def _run_command(self, kwargs: Dict[str, Any]) -> ToolResult:
        command = str(kwargs.get("command", "")).strip()
        cwd = Path(str(kwargs.get("cwd", "."))).expanduser().resolve()
        timeout = self._coerce_timeout(kwargs.get("timeout", self._DEFAULT_TIMEOUT_SECONDS))

        if not command:
            return self._error("run_command requires argument: command")
        if not cwd.exists() or not cwd.is_dir():
            return self._error(f"Working directory not found: {cwd}")

        started = time.perf_counter()
        process = subprocess.run(
            command,
            cwd=str(cwd),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        payload = {
            "command": command,
            "cwd": str(cwd),
            "timeout": timeout,
            "return_code": process.returncode,
            "stdout": (process.stdout or "").strip(),
            "stderr": (process.stderr or "").strip(),
            "duration_ms": elapsed_ms,
        }

        if process.returncode == 0:
            return self._success(output=json.dumps(payload, ensure_ascii=False, indent=2), result=payload)

        return self._error(
            f"Command failed with return code {process.returncode}",
            result=payload,
            retryable=False,
        )

    def _run_static_checks(self, kwargs: Dict[str, Any]) -> ToolResult:
        project_path = Path(str(kwargs.get("project_path", "."))).expanduser().resolve()
        timeout = self._coerce_timeout(kwargs.get("timeout", 180))

        if not project_path.exists() or not project_path.is_dir():
            return self._error(f"Project path not found: {project_path}")

        commands = [
            "python -m compileall -q .",
        ]

        reports: List[Dict[str, Any]] = []
        all_success = True
        for command in commands:
            result = self._execute_shell(command=command, cwd=project_path, timeout=timeout)
            reports.append(result)
            if result["return_code"] != 0:
                all_success = False

        output = json.dumps(reports, ensure_ascii=False, indent=2)
        if all_success:
            return self._success(output=output, reports=reports)

        return self._error("Static checks failed", reports=reports)

    def _run_unit_tests(self, kwargs: Dict[str, Any]) -> ToolResult:
        project_path = Path(str(kwargs.get("project_path", "."))).expanduser().resolve()
        timeout = self._coerce_timeout(kwargs.get("timeout", self._DEFAULT_TIMEOUT_SECONDS))

        command = str(kwargs.get("command", "")).strip()
        if not command:
            command = self._guess_test_command(project_path)

        result = self._execute_shell(command=command, cwd=project_path, timeout=timeout)
        output = json.dumps(result, ensure_ascii=False, indent=2)

        if result["return_code"] == 0:
            return self._success(output=output, result=result)

        return self._error("Unit tests failed", result=result)

    def _run_smoke_test(self, kwargs: Dict[str, Any]) -> ToolResult:
        project_path = Path(str(kwargs.get("project_path", "."))).expanduser().resolve()
        timeout = self._coerce_timeout(kwargs.get("timeout", 120))

        command = str(kwargs.get("command", "")).strip()
        if not command:
            command = "python -c \"print('smoke_test_ok')\""

        result = self._execute_shell(command=command, cwd=project_path, timeout=timeout)
        output = json.dumps(result, ensure_ascii=False, indent=2)

        if result["return_code"] == 0:
            return self._success(output=output, result=result)

        return self._error("Smoke test failed", result=result)

    def _compare_metrics(self, kwargs: Dict[str, Any]) -> ToolResult:
        expected = kwargs.get("expected")
        actual = kwargs.get("actual")
        tolerance = float(kwargs.get("tolerance", 0.02))

        if not isinstance(expected, dict) or not isinstance(actual, dict):
            return self._error("compare_metrics requires dict arguments: expected and actual")

        comparison: Dict[str, Any] = {}
        passed = True

        for metric, expected_value in expected.items():
            actual_value = actual.get(metric)
            if actual_value is None:
                comparison[metric] = {
                    "expected": expected_value,
                    "actual": None,
                    "status": "missing",
                }
                passed = False
                continue

            try:
                expected_float = float(expected_value)
                actual_float = float(actual_value)
            except (TypeError, ValueError):
                is_equal = expected_value == actual_value
                comparison[metric] = {
                    "expected": expected_value,
                    "actual": actual_value,
                    "status": "pass" if is_equal else "mismatch",
                }
                if not is_equal:
                    passed = False
                continue

            diff = abs(actual_float - expected_float)
            allowed = abs(expected_float) * tolerance
            status = "pass" if diff <= allowed else "out_of_range"
            if status != "pass":
                passed = False

            comparison[metric] = {
                "expected": expected_float,
                "actual": actual_float,
                "difference": diff,
                "allowed": allowed,
                "status": status,
            }

        output = json.dumps(comparison, ensure_ascii=False, indent=2)
        if passed:
            return self._success(output=output, passed=True, comparison=comparison)

        return self._error("Metric comparison failed", passed=False, comparison=comparison)

    def _guess_test_command(self, project_path: Path) -> str:
        if (project_path / "pytest.ini").exists() or (project_path / "tests").exists():
            return "python -m unittest discover -s tests -v"
        return "python -m unittest -v"

    def _execute_shell(self, command: str, cwd: Path, timeout: int) -> Dict[str, Any]:
        started = time.perf_counter()
        result = subprocess.run(
            command,
            cwd=str(cwd),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)

        return {
            "command": command,
            "cwd": str(cwd),
            "timeout": timeout,
            "return_code": result.returncode,
            "stdout": (result.stdout or "").strip(),
            "stderr": (result.stderr or "").strip(),
            "duration_ms": duration_ms,
        }

    def _coerce_timeout(self, value: Any) -> int:
        try:
            timeout = int(value)
        except (TypeError, ValueError):
            return self._DEFAULT_TIMEOUT_SECONDS
        return max(1, min(timeout, 3600))
