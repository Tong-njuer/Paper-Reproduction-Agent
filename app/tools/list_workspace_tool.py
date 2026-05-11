import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from app.core.config import get_config
from app.core.logging import get_logger
from app.tools import BaseTool, ToolResult


class ListWorkspaceTool(BaseTool):
    name = "list_workspace_tool"
    description = (
        "列出工作区中所有已克隆的仓库及状态。无需参数。"
    )

    VENV_DIR = ".venv"

    def __init__(self):
        self._log = get_logger("list_workspace")

    @property
    def workspace_dir(self) -> Path:
        return Path(get_config().agent.workspace_dir).resolve()

    def execute(self, **kwargs) -> ToolResult:
        ws = self.workspace_dir
        if not ws.exists():
            return self._ok(output="工作区为空（目录不存在）。")

        repos = self._list_repos()
        if not repos:
            return self._ok(output="工作区中暂无已克隆的仓库。")

        lines = [f"工作区 ({ws}) 中共有 {len(repos)} 个仓库:\n"]
        for r in repos:
            lines.append(self._describe_repo(r))

        return self._ok(
            output="\n".join(lines),
            repo_count=len(repos),
            repos=[{"name": r.name, "path": str(r)} for r in repos],
        )

    def _list_repos(self) -> list[Path]:
        ws = self.workspace_dir
        if not ws.exists():
            return []
        return sorted(
            [p for p in ws.iterdir() if p.is_dir() and (p / ".git").exists()],
            key=lambda p: p.name,
        )

    def _describe_repo(self, repo: Path) -> str:
        name = repo.name
        lines = [f"  {name}"]

        # Remote URL
        remote = self._git_remote(repo)
        if remote:
            lines.append(f"    remote: {remote}")

        # venv status
        venv_path = repo / self.VENV_DIR
        if venv_path.exists():
            py = self._venv_python(venv_path)
            if py:
                py_ver = self._python_version(py)
                lines.append(f"    venv: {py_ver or '已存在'}")
            else:
                lines.append(f"    venv: 已存在但Python解释器不可用")
        else:
            lines.append(f"    venv: 未创建")

        # Last modified
        mtime = datetime.fromtimestamp(repo.stat().st_mtime)
        lines.append(f"    last-modified: {mtime.strftime('%Y-%m-%d %H:%M')}")

        # Size
        size = self._dir_size(repo)
        lines.append(f"    size: {self._fmt_size(size)}")

        return "\n".join(lines)

    @staticmethod
    def _git_remote(repo: Path) -> str | None:
        try:
            r = subprocess.run(
                ["git", "-C", str(repo), "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def _venv_python(venv_path: Path) -> str | None:
        if sys.platform == "win32":
            py = venv_path / "Scripts" / "python.exe"
        else:
            py = venv_path / "bin" / "python"
        return str(py) if py.exists() else None

    @staticmethod
    def _python_version(python_exe: str) -> str | None:
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
