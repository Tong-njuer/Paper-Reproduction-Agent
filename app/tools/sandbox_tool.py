"""Sandbox preparation and environment planning tool."""

from __future__ import annotations

import json
import os
import uuid
import venv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.tools import BaseTool, ToolResult


class SandboxTool(BaseTool):
    """沙箱目录、环境检测与安装计划工具。"""

    name = "sandbox_tool"
    description = (
        "Prepare isolated run workspace and detect runtime requirements. "
        "Actions: create_workspace, detect_environment, build_install_plan, create_python_venv."
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        action = str(kwargs.get("action", "create_workspace")).strip().lower()

        handlers = {
            "create_workspace": self._create_workspace,
            "detect_environment": self._detect_environment,
            "build_install_plan": self._build_install_plan,
            "create_python_venv": self._create_python_venv,
            "build_sandbox_spec": self._build_sandbox_spec,
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
            return self._error(f"Sandbox tool failed: {exc}", action=action)

    def _create_workspace(self, kwargs: Dict[str, Any]) -> ToolResult:
        base_dir = Path(str(kwargs.get("base_dir", "workspace"))).expanduser().resolve()
        user_id = str(kwargs.get("user_id", "user_1")).strip() or "user_1"
        run_id = str(kwargs.get("run_id", "")).strip() or datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")

        run_root = base_dir / user_id / "runs" / run_id
        dirs = {
            "root": run_root,
            "sources": run_root / "sources",
            "reports": run_root / "reports",
            "logs": run_root / "logs",
            "artifacts": run_root / "artifacts",
            "sandbox": run_root / "sandbox",
        }

        for path in dirs.values():
            path.mkdir(parents=True, exist_ok=True)

        return self._success(
            output=f"Workspace created: {run_root}",
            run_id=run_id,
            user_id=user_id,
            paths={key: str(value) for key, value in dirs.items()},
        )

    def _detect_environment(self, kwargs: Dict[str, Any]) -> ToolResult:
        project_path = Path(str(kwargs.get("project_path", "")).strip()).expanduser().resolve()
        if not str(project_path):
            return self._error("detect_environment requires argument: project_path")
        if not project_path.exists() or not project_path.is_dir():
            return self._error(f"Project path not found: {project_path}")

        manifests = {
            "python": ["requirements.txt", "pyproject.toml", "setup.py", "environment.yml"],
            "node": ["package.json", "pnpm-lock.yaml", "yarn.lock"],
            "java": ["pom.xml", "build.gradle", "gradlew"],
            "rust": ["Cargo.toml"],
            "go": ["go.mod"],
        }

        detected: Dict[str, List[str]] = {}
        for runtime, files in manifests.items():
            hits = []
            for file_name in files:
                path = project_path / file_name
                if path.exists():
                    hits.append(file_name)
            if hits:
                detected[runtime] = hits

        needs_gpu = self._detect_gpu_hint(project_path)
        needs_network = self._detect_network_hint(project_path)

        result = {
            "project_path": str(project_path),
            "detected_runtimes": detected,
            "needs_gpu": needs_gpu,
            "needs_network": needs_network,
        }

        return self._success(output=json.dumps(result, ensure_ascii=False, indent=2), environment=result)

    def _build_install_plan(self, kwargs: Dict[str, Any]) -> ToolResult:
        environment = kwargs.get("environment")
        if not isinstance(environment, dict):
            detected = kwargs.get("detected_runtimes")
            if not isinstance(detected, dict):
                return self._error("build_install_plan requires environment dict or detected_runtimes")
            environment = {"detected_runtimes": detected}

        detected = environment.get("detected_runtimes", {})
        if not isinstance(detected, dict):
            return self._error("Invalid detected_runtimes format")

        commands: List[str] = []

        if "python" in detected:
            commands.extend(
                [
                    "python -m venv .venv",
                    ".venv\\Scripts\\python -m pip install --upgrade pip",
                    ".venv\\Scripts\\python -m pip install -r requirements.txt",
                ]
            )
        if "node" in detected:
            commands.append("npm install")
        if "java" in detected:
            if "pom.xml" in detected.get("java", []):
                commands.append("mvn -q -DskipTests package")
            else:
                commands.append("./gradlew build")
        if "rust" in detected:
            commands.append("cargo build")
        if "go" in detected:
            commands.append("go mod download")

        if not commands:
            commands.append("No known runtime detected; manual setup required")

        return self._success(
            output="\n".join(commands),
            install_commands=commands,
            count=len(commands),
        )

    def _create_python_venv(self, kwargs: Dict[str, Any]) -> ToolResult:
        venv_path = Path(str(kwargs.get("venv_path", ".venv"))).expanduser().resolve()
        with_pip = bool(kwargs.get("with_pip", True))
        clear = bool(kwargs.get("clear", False))

        builder = venv.EnvBuilder(with_pip=with_pip, clear=clear)
        builder.create(venv_path)

        python_executable = venv_path / "Scripts" / "python.exe"
        if not python_executable.exists():
            python_executable = venv_path / "bin" / "python"

        return self._success(
            output=f"Virtual environment created at {venv_path}",
            venv_path=str(venv_path),
            python=str(python_executable),
        )

    def _build_sandbox_spec(self, kwargs: Dict[str, Any]) -> ToolResult:
        spec = {
            "image": str(kwargs.get("image", "python:3.11-slim")),
            "cpu": float(kwargs.get("cpu", 2.0)),
            "memory": str(kwargs.get("memory", "4Gi")),
            "timeout_seconds": int(kwargs.get("timeout_seconds", 3600)),
            "network_policy": str(kwargs.get("network_policy", "allowlist")),
            "allowlist": kwargs.get("allowlist", []),
        }

        return self._success(output=json.dumps(spec, ensure_ascii=False, indent=2), sandbox_spec=spec)

    def _detect_gpu_hint(self, project_path: Path) -> bool:
        hints = ["cuda", "torch.cuda", "tensorflow-gpu", "nvidia"]
        return self._search_in_text_files(project_path, hints, max_files=200)

    def _detect_network_hint(self, project_path: Path) -> bool:
        hints = ["http://", "https://", "requests.get", "wget", "curl", "huggingface"]
        return self._search_in_text_files(project_path, hints, max_files=200)

    def _search_in_text_files(self, root: Path, keywords: List[str], max_files: int) -> bool:
        inspected = 0
        lowered_keywords = [item.lower() for item in keywords]
        for path in root.rglob("*"):
            if inspected >= max_files:
                break
            if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                continue
            inspected += 1
            try:
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
            if any(keyword in text for keyword in lowered_keywords):
                return True
        return False
