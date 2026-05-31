"""
CleanupEnvTool — 清理复现环境

职责:
- 删除指定仓库的虚拟环境 (.venv)
- 删除工作区中所有虚拟环境
- 清理 pip 缓存
- 清理临时文件

与 WorkspaceCleanupTool 的区别:
WorkspaceCleanupTool 删除整个仓库（代码），
CleanupEnvTool 只清理环境配置（venv、缓存等），保留代码。
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from app.core.config import get_config
from app.core.logging import get_logger
from app.tools import BaseTool, ToolResult


VENV_DIR = ".venv"


class CleanupEnvTool(BaseTool):
    name = "cleanup_env_tool"
    description = (
        "清理复现环境工具：删除虚拟环境、清理 pip 缓存、清理临时文件。"
        "参数: action(remove_venv|clean_all|clean_pip_cache|status), "
        "repo_name(仓库名) 或 repo_path(仓库路径)"
    )

    def __init__(self):
        self._log = get_logger("cleanup_env")

    @property
    def workspace_dir(self) -> Path:
        return Path(get_config().agent.workspace_dir).resolve()

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def execute(self, action: str = "status", repo_name: str = "",
                repo_path: str = "", **kwargs) -> ToolResult:
        if action == "remove_venv":
            return self._remove_venv(repo_name, repo_path)
        elif action == "clean_all":
            return self._clean_all()
        elif action == "clean_pip_cache":
            return self._clean_pip_cache()
        elif action == "status":
            return self._status()
        else:
            return self._fail(
                f"未知 action: {action}，支持: remove_venv, clean_all, clean_pip_cache, status"
            )

    # ------------------------------------------------------------------
    # Action: remove_venv — delete .venv from a specific repo
    # ------------------------------------------------------------------

    def _remove_venv(self, repo_name: str, repo_path: str) -> ToolResult:
        """Remove the virtual environment from a specific repository."""
        # Resolve repo
        if repo_path:
            target = Path(repo_path).resolve()
        elif repo_name:
            target = self.workspace_dir / repo_name
        else:
            return self._fail("需要指定 repo_name 或 repo_path。使用 action=status 查看工作区状态。")

        if not target.exists():
            return self._fail(f"仓库路径不存在: {target}")

        if not (target / ".git").exists():
            return self._fail(f"'{target.name}' 不是 git 仓库，拒绝操作。")

        venv_path = target / VENV_DIR
        if not venv_path.exists():
            return self._ok(
                output=f"仓库 '{target.name}' 中没有虚拟环境 ({VENV_DIR})。",
                repo_name=target.name,
            )

        # Verify it's actually a venv
        if not (venv_path / "pyvenv.cfg").exists() and not (venv_path / "Scripts" / "python.exe").exists() and not (venv_path / "bin" / "python").exists():
            return self._fail(f"'{venv_path}' 不是有效的虚拟环境，拒绝删除。")

        try:
            size = self._dir_size(venv_path)
            shutil.rmtree(venv_path)
            self._log.info(f"Removed venv at {venv_path}, freed {size} bytes")
            return self._ok(
                output=(
                    f"✅ 已删除虚拟环境\n"
                    f"  - 仓库: {target.name}\n"
                    f"  - 路径: {venv_path}\n"
                    f"  - 释放空间: {self._fmt_size(size)}"
                ),
                repo_name=target.name,
                freed_size=size,
            )
        except Exception as e:
            return self._fail(f"删除虚拟环境失败: {e}", repo_name=target.name)

    # ------------------------------------------------------------------
    # Action: clean_all — remove all venvs in workspace
    # ------------------------------------------------------------------

    def _clean_all(self) -> ToolResult:
        """Remove all virtual environments in the workspace."""
        ws = self.workspace_dir
        if not ws.exists():
            return self._ok(output="工作区为空（目录不存在）。")

        repos = self._list_repos()
        if not repos:
            return self._ok(output="工作区中无仓库，无需清理。")

        cleaned = []
        errors = []
        total_freed = 0

        for repo in repos:
            venv_path = repo / VENV_DIR
            if venv_path.exists():
                try:
                    size = self._dir_size(venv_path)
                    shutil.rmtree(venv_path)
                    cleaned.append((repo.name, size))
                    total_freed += size
                    self._log.info(f"Cleaned venv: {repo.name} ({self._fmt_size(size)})")
                except Exception as e:
                    errors.append(f"{repo.name}: {e}")

        lines = [f"## 环境清理报告", f""]
        if cleaned:
            lines.append(f"已清理 {len(cleaned)} 个虚拟环境:")
            for name, size in cleaned:
                lines.append(f"  - {name}: {self._fmt_size(size)}")
            lines.append(f"总释放空间: {self._fmt_size(total_freed)}")
        else:
            lines.append("所有仓库均无虚拟环境，无需清理。")

        if errors:
            lines.append(f"\n失败 {len(errors)} 个:")
            for err in errors:
                lines.append(f"  - {err}")

        return self._ok(
            output="\n".join(lines),
            cleaned=[name for name, _ in cleaned],
            total_freed=total_freed,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Action: clean_pip_cache — clear pip cache
    # ------------------------------------------------------------------

    def _clean_pip_cache(self) -> ToolResult:
        """Clear the pip cache to free disk space."""
        try:
            # Try to use `pip cache purge`
            result = subprocess.run(
                [sys.executable, "-m", "pip", "cache", "purge"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                output = result.stdout.strip() or "pip 缓存已清理。"
                return self._ok(output=output)
            else:
                # Fallback: manually remove pip cache directory
                if sys.platform == "win32":
                    cache_dir = Path(os.environ.get(
                        "LOCALAPPDATA", ""
                    )) / "pip" / "cache"
                else:
                    cache_dir = Path.home() / ".cache" / "pip"

                if cache_dir.exists():
                    size = self._dir_size(cache_dir)
                    shutil.rmtree(cache_dir)
                    return self._ok(
                        output=f"pip 缓存已手动清理 (释放 {self._fmt_size(size)})",
                        freed_size=size,
                    )
                return self._ok(output="未找到 pip 缓存目录。")
        except Exception as e:
            return self._fail(f"清理 pip 缓存失败: {e}")

    # ------------------------------------------------------------------
    # Action: status — show environment status for all repos
    # ------------------------------------------------------------------

    def _status(self) -> ToolResult:
        """Show the environment status of all repos in the workspace."""
        ws = self.workspace_dir
        if not ws.exists():
            return self._ok(output="工作区为空（目录不存在）。")

        repos = self._list_repos()
        if not repos:
            return self._ok(output="工作区中无仓库。")

        total_venv_size = 0
        venv_count = 0
        lines = [
            f"## 工作区环境状态",
            f"",
            f"{'仓库名':<25} {'虚拟环境':<12} {'Python 版本':<15} {'占用空间':<10}",
            f"{'-'*62}",
        ]

        for repo in sorted(repos, key=lambda p: p.name):
            venv_path = repo / VENV_DIR
            if venv_path.exists() and (venv_path / "pyvenv.cfg").exists():
                py_ver = self._get_venv_python(repo)
                size = self._dir_size(venv_path)
                total_venv_size += size
                venv_count += 1
                lines.append(f"{repo.name:<25} {'✅ 存在':<12} {py_ver:<15} {self._fmt_size(size):<10}")
            else:
                lines.append(f"{repo.name:<25} {'❌ 无':<12} {'-':<15} {'-':<10}")

        lines.extend([
            f"",
            f"总计: {len(repos)} 个仓库, {venv_count} 个虚拟环境, "
            f"占用 {self._fmt_size(total_venv_size)}",
            f"",
            f"可用操作:",
            f"  action=remove_venv  repo_name=<仓库名>  — 删除指定仓库的虚拟环境",
            f"  action=clean_all                       — 删除所有虚拟环境",
            f"  action=clean_pip_cache                 — 清理 pip 缓存",
        ])

        return self._ok(
            output="\n".join(lines),
            repo_count=len(repos),
            venv_count=venv_count,
            total_venv_size=total_venv_size,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _list_repos(self) -> list:
        ws = self.workspace_dir
        if not ws.exists():
            return []
        return sorted(
            [p for p in ws.iterdir() if p.is_dir() and (p / ".git").exists()],
            key=lambda p: p.name,
        )

    @staticmethod
    def _get_venv_python(target: Path) -> str:
        """Get the Python version string from an existing venv."""
        if sys.platform == "win32":
            py_path = target / VENV_DIR / "Scripts" / "python.exe"
        else:
            py_path = target / VENV_DIR / "bin" / "python"

        if not py_path.exists():
            return "(未知)"

        try:
            result = subprocess.run(
                [str(py_path), "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return (result.stdout.strip() or result.stderr.strip())[:15]
        except Exception:
            pass
        return "(未知)"

    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        try:
            for p in path.rglob("*"):
                if p.is_file():
                    total += p.stat().st_size
        except Exception:
            pass
        return total

    @staticmethod
    def _fmt_size(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
