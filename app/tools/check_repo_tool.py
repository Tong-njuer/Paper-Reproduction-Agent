"""CheckRepoTool — deep inspection of a specific cloned repository.

Shows: git remote URL, last commit, branch, venv status with Python version,
installed pip packages, entry-point files, disk size, and recent git log.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.config import get_config
from app.core.logging import get_logger
from app.tools import BaseTool, ToolResult


class CheckRepoTool(BaseTool):
    name = "check_repo_tool"
    description = (
        "深度检查某个已克隆仓库的状态: 远程地址、提交、分支、"
        "虚拟环境(含Python版本)、已安装包、入口文件、磁盘占用。"
        "参数: repo_name(仓库名) 或 repo_path(仓库路径)"
    )

    VENV_DIR = ".venv"

    def __init__(self):
        self._log = get_logger("check_repo")

    @property
    def workspace_dir(self) -> Path:
        return Path(get_config().agent.workspace_dir).resolve()

    def execute(self, repo_name: str = "", repo_path: str = "",
                **kwargs) -> ToolResult:
        target = self._resolve(repo_name, repo_path)
        if target is None:
            repos = self._list_repos()
            names = ", ".join(r.name for r in repos) if repos else "(空)"
            return self._fail(
                f"未找到仓库。请指定 repo_name 或 repo_path。"
                f"workspace 中现有: {names}"
            )

        lines = [
            f"仓库检查: {target.name}",
            f"路径: {target}",
            "",
        ]

        # Git info
        lines.append("## Git 信息")
        lines.append(self._git_info(target))
        lines.append("")

        # venv
        lines.append("## 虚拟环境")
        lines.append(self._venv_info(target))
        lines.append("")

        # Installed packages
        lines.append("## 已安装的包")
        lines.append(self._pip_list(target))
        lines.append("")

        # Entry files
        lines.append("## 入口文件")
        lines.append(self._entry_files(target))
        lines.append("")

        # Root files
        lines.append("## 根目录文件 (前40项)")
        lines.append(self._root_listing(target))
        lines.append("")

        # Disk size
        lines.append("## 磁盘占用")
        size = self._dir_size(target)
        lines.append(f"  {self._fmt_size(size)}")

        return self._ok(
            output="\n".join(lines),
            repo_name=target.name,
            repo_path=str(target),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, repo_name: str, repo_path: str) -> Optional[Path]:
        if repo_path:
            target = Path(repo_path).resolve()
            if target.exists() and (target / ".git").exists():
                return target
            return None
        if repo_name:
            target = self.workspace_dir / repo_name
            if target.exists() and (target / ".git").exists():
                return target
            return None
        # No args: pick the only repo if there is exactly one
        repos = self._list_repos()
        if len(repos) == 1:
            return repos[0]
        return None

    def _list_repos(self) -> list[Path]:
        ws = self.workspace_dir
        if not ws.exists():
            return []
        return sorted(
            [p for p in ws.iterdir() if p.is_dir() and (p / ".git").exists()],
            key=lambda p: p.name,
        )

    # ------------------------------------------------------------------
    # Git
    # ------------------------------------------------------------------

    def _git_info(self, target: Path) -> str:
        lines = []
        remote = self._git_remote(target)
        branch = self._git_branch(target)
        last_commit = self._git_last_commit(target)
        lines.append(f"  remote: {remote or '(无)'}")
        lines.append(f"  branch: {branch or '(无)'}")
        if last_commit:
            lines.append(f"  last-commit: {last_commit}")
        return "\n".join(lines)

    @staticmethod
    def _git_remote(repo: Path) -> Optional[str]:
        try:
            r = subprocess.run(
                ["git", "-C", str(repo), "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10,
            )
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None

    @staticmethod
    def _git_branch(repo: Path) -> Optional[str]:
        try:
            r = subprocess.run(
                ["git", "-C", str(repo), "branch", "--show-current"],
                capture_output=True, text=True, timeout=10,
            )
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None

    @staticmethod
    def _git_last_commit(repo: Path) -> Optional[str]:
        try:
            r = subprocess.run(
                ["git", "-C", str(repo), "log", "-1",
                 "--format=%h %s (%an, %ar)"],
                capture_output=True, text=True, timeout=10,
            )
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # venv
    # ------------------------------------------------------------------

    def _venv_info(self, target: Path) -> str:
        venv_path = target / self.VENV_DIR
        if not venv_path.exists():
            return "  未创建"
        py = self._venv_python(venv_path)
        if py:
            ver = self._python_version(py)
            return f"  已创建 ({ver or '版本未知'})\n  Python: {py}"
        return "  已存在但Python解释器不可用"

    @staticmethod
    def _venv_python(venv_path: Path) -> Optional[str]:
        if sys.platform == "win32":
            py = venv_path / "Scripts" / "python.exe"
        else:
            py = venv_path / "bin" / "python"
        return str(py) if py.exists() else None

    @staticmethod
    def _python_version(python_exe: str) -> Optional[str]:
        try:
            r = subprocess.run(
                [python_exe, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                return (r.stdout or r.stderr).strip()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # pip list
    # ------------------------------------------------------------------

    def _pip_list(self, target: Path) -> str:
        venv_path = target / self.VENV_DIR
        py = self._venv_python(venv_path) if venv_path.exists() else None
        if not py:
            return "  虚拟环境未就绪，无法列出包。"
        try:
            r = subprocess.run(
                [py, "-m", "pip", "list", "--format=columns"],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0:
                lines = r.stdout.strip().split("\n")
                pkgs = []
                for line in lines[2:]:  # skip header rows
                    parts = line.split()
                    if parts:
                        pkgs.append(f"  {parts[0]} {parts[1] if len(parts) > 1 else ''}")
                return "\n".join(pkgs[:30]) if pkgs else "  (无已安装包)"
            return f"  pip list 失败: {r.stderr[:200]}"
        except Exception as e:
            return f"  无法列出包: {e}"

    # ------------------------------------------------------------------
    # Entry files
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_files(target: Path) -> str:
        patterns = [
            "main.py", "run.py", "train.py", "eval.py", "demo.py",
            "predict.py", "test.py", "infer.py", "inference.py",
            "setup.py", "run.sh", "start.sh", "quick_test.py",
            "main.ipynb", "demo.ipynb",
        ]
        found = []
        for name in patterns:
            if (target / name).exists():
                found.append(f"  {name}")
        # Also list any .ipynb
        for p in sorted(target.glob("*.ipynb")):
            rel = str(p.relative_to(target))
            if f"  {rel}" not in found:
                found.append(f"  {rel}")
        return "\n".join(found[:15]) if found else "  (未检测到标准入口文件)"

    # ------------------------------------------------------------------
    # Root listing
    # ------------------------------------------------------------------

    @staticmethod
    def _root_listing(target: Path) -> str:
        items = []
        for p in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name)):
            if p.name.startswith("."):
                continue
            suffix = "/" if p.is_dir() else ""
            items.append(f"  {p.name}{suffix}")
        return "\n".join(items[:40]) if items else "  (空)"

    # ------------------------------------------------------------------
    # Disk size
    # ------------------------------------------------------------------

    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        try:
            for dirpath, _dirnames, filenames in os.walk(str(path)):
                for f in filenames:
                    fp = Path(dirpath) / f
                    try:
                        total += fp.stat().st_size
                    except OSError:
                        pass
        except Exception:
            pass
        return total

    @staticmethod
    def _fmt_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
