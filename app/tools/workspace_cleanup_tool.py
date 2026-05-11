"""WorkspaceCleanupTool — remove repos from the workspace to free disk space.

Supports:
- Remove a specific repo by name
- List repos with size so user can pick
- Remove all repos (with confirmation)
"""

import shutil
from pathlib import Path

from app.core.config import get_config
from app.core.logging import get_logger
from app.tools import BaseTool, ToolResult
from app.tools.list_workspace_tool import ListWorkspaceTool


class WorkspaceCleanupTool(BaseTool):
    name = "workspace_cleanup_tool"
    description = (
        "清理工作区中的仓库，释放磁盘空间。"
        "参数: repo_name(要删除的仓库名，可选), "
        "action(list/list_sizes/cleanup_all)"
    )

    def __init__(self):
        self._log = get_logger("workspace_cleanup")
        self._lister = ListWorkspaceTool()

    @property
    def workspace_dir(self) -> Path:
        return Path(get_config().agent.workspace_dir).resolve()

    def execute(self, repo_name: str = "", action: str = "",
                **kwargs) -> ToolResult:
        ws = self.workspace_dir
        if not ws.exists():
            return self._ok(output="工作区为空（目录不存在）。")

        repos = self._lister._list_repos()

        # action=list_sizes: show repos sorted by size (biggest first)
        if action == "list_sizes":
            return self._list_sizes(repos)

        # action=cleanup_all: remove everything
        if action == "cleanup_all":
            return self._cleanup_all(repos)

        # Remove a specific repo
        if repo_name:
            return self._remove_one(ws, repo_name)

        # Default: show what's available
        if not repos:
            return self._ok(output="工作区中暂无仓库。")

        total_size = sum(self._lister._dir_size(r) for r in repos)
        lines = [
            f"工作区 ({ws}) 中共有 {len(repos)} 个仓库，"
            f"总占用 {self._lister._fmt_size(total_size)}。",
            "",
            "可执行的操作:",
            "  action=list_sizes   — 按磁盘占用排序查看",
            "  repo_name=<name>    — 删除指定仓库",
            "  action=cleanup_all  — 清空所有仓库",
            "",
            "现有仓库:",
        ]
        for r in repos:
            size = self._lister._dir_size(r)
            lines.append(f"  - {r.name} ({self._lister._fmt_size(size)})")

        return self._ok(output="\n".join(lines), repo_count=len(repos))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _list_sizes(self, repos: list[Path]) -> ToolResult:
        if not repos:
            return self._ok(output="工作区中暂无仓库。")

        sized = [(r, self._lister._dir_size(r)) for r in repos]
        sized.sort(key=lambda x: x[1], reverse=True)

        total = sum(s for _, s in sized)
        lines = [
            f"工作区仓库按磁盘占用排序 (总占用 {self._lister._fmt_size(total)}):\n"
        ]
        for i, (repo, size) in enumerate(sized, 1):
            lines.append(f"  {i}. {repo.name} — {self._lister._fmt_size(size)}")

        return self._ok(
            output="\n".join(lines),
            repos=[{"name": r.name, "size": s} for r, s in sized],
            total_size=total,
        )

    def _cleanup_all(self, repos: list[Path]) -> ToolResult:
        if not repos:
            return self._ok(output="工作区中暂无仓库，无需清理。")

        total_size = sum(self._lister._dir_size(r) for r in repos)
        removed = []
        errors = []

        for repo in repos:
            try:
                shutil.rmtree(repo)
                removed.append(repo.name)
                self._log.info(f"Removed: {repo}")
            except Exception as e:
                errors.append(f"{repo.name}: {e}")

        lines = [
            f"已清空工作区，删除 {len(removed)} 个仓库，"
            f"释放 {self._lister._fmt_size(total_size)}。",
        ]
        if errors:
            lines.append(f"失败 {len(errors)} 个: " + "; ".join(errors))

        return self._ok(
            output="\n".join(lines),
            removed=removed, errors=errors,
            freed_size=total_size,
        )

    def _remove_one(self, ws: Path, repo_name: str) -> ToolResult:
        target = ws / repo_name
        if not target.exists():
            # Fuzzy match
            matches = [p for p in ws.iterdir()
                      if p.is_dir() and repo_name.lower() in p.name.lower()
                      and (p / ".git").exists()]
            if len(matches) == 1:
                target = matches[0]
            elif len(matches) > 1:
                names = ", ".join(m.name for m in matches)
                return self._fail(
                    f"找到多个匹配: {names}。请指定更精确的仓库名。"
                )
            else:
                return self._fail(
                    f"仓库 '{repo_name}' 不存在。"
                    f"请使用 list_workspace_tool 查看可用仓库。"
                )

        if not (target / ".git").exists():
            return self._fail(f"'{target.name}' 不是 git 仓库，拒绝删除。")

        size = self._lister._dir_size(target)
        try:
            shutil.rmtree(target)
            return self._ok(
                output=f"已删除仓库: {target.name}\n释放空间: {self._lister._fmt_size(size)}",
                removed=target.name,
                freed_size=size,
            )
        except Exception as e:
            return self._fail(f"删除失败: {e}")
