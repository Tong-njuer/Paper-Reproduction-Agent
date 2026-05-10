"""StatsTool — aggregate statistics from report history and workspace.

Provides: total reports, success rate, common error patterns,
average steps per run, workspace disk usage, most-searched papers, etc.
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.core.config import get_config
from app.core.logging import get_logger
from app.tools import BaseTool, ToolResult
from app.tools.report_store import ReportStore
from app.tools.list_workspace_tool import ListWorkspaceTool


class StatsTool(BaseTool):
    name = "stats_tool"
    description = (
        "查看 Agent 系统统计数据: 总报告数、成功率、常见错误、"
        "工作区状态等。无需参数。"
    )

    def __init__(self):
        self._log = get_logger("stats")
        self._store = ReportStore()

    def execute(self, **kwargs) -> ToolResult:
        lines = ["## Agent 系统统计", ""]

        # Report stats
        report_stats = self._report_stats()
        lines.extend(report_stats)
        lines.append("")

        # Workspace stats
        workspace_stats = self._workspace_stats()
        lines.extend(workspace_stats)
        lines.append("")

        # Error patterns
        error_stats = self._error_patterns()
        lines.extend(error_stats)

        return self._ok(output="\n".join(lines))

    # ------------------------------------------------------------------
    # Report stats
    # ------------------------------------------------------------------

    def _report_stats(self) -> list[str]:
        reports = self._store.list()
        lines = ["### 报告统计", ""]

        if not reports:
            lines.append("  暂无报告。")
            return lines

        total = len(reports)
        success_count = sum(1 for r in reports if r["success"])
        fail_count = total - success_count
        rate = (success_count / total * 100) if total > 0 else 0

        lines.append(f"  总报告数:    {total}")
        lines.append(f"  成功:        {success_count} ({rate:.1f}%)")
        lines.append(f"  失败:        {fail_count} ({100 - rate:.1f}%)")

        # Average steps
        avg_steps = sum(r["step_count"] for r in reports) / total if total > 0 else 0
        lines.append(f"  平均步骤数:  {avg_steps:.1f}")

        # Average errors
        avg_errors = sum(r["error_count"] for r in reports) / total if total > 0 else 0
        lines.append(f"  平均错误数:  {avg_errors:.1f}")

        # Recent activity
        if reports:
            lines.append(f"  最近报告:    {reports[0].get('timestamp', '')[:16]}")

        # Most common goals (top 5)
        goals = [r.get("goal", "") for r in reports]
        # Extract key terms
        goal_words = []
        for g in goals:
            words = g.lower().replace("复现", "").replace("reproduce", "").strip()
            if words:
                goal_words.append(words[:60])
        if goal_words:
            common = Counter(goal_words).most_common(5)
            lines.append("  常见目标:")
            for g, c in common:
                lines.append(f"    [{c}次] {g}")

        return lines

    # ------------------------------------------------------------------
    # Workspace stats
    # ------------------------------------------------------------------

    def _workspace_stats(self) -> list[str]:
        lines = ["### 工作区统计", ""]

        lister = ListWorkspaceTool()
        repos = lister._list_repos()
        ws = Path(get_config().agent.workspace_dir).resolve()

        if not repos:
            lines.append(f"  路径: {ws}")
            lines.append("  仓库: 无")
            return lines

        total_size = sum(lister._dir_size(r) for r in repos)
        lines.append(f"  路径:      {ws}")
        lines.append(f"  仓库数:    {len(repos)}")
        lines.append(f"  总占用:    {lister._fmt_size(total_size)}")

        # List repos with size
        sized = [(r, lister._dir_size(r)) for r in repos]
        sized.sort(key=lambda x: x[1], reverse=True)
        lines.append("  仓库:")
        for r, s in sized[:10]:
            lines.append(f"    {r.name} — {lister._fmt_size(s)}")

        return lines

    # ------------------------------------------------------------------
    # Error patterns
    # ------------------------------------------------------------------

    def _error_patterns(self) -> list[str]:
        lines = ["### 常见错误模式", ""]

        if not self._store.dir.exists():
            lines.append("  暂无数据。")
            return lines

        error_types = Counter()
        total_errors = 0

        for p in self._store.dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                for e in data.get("errors", []):
                    total_errors += 1
                    err_str = str(e).lower()
                    if "import" in err_str or "modulenotfound" in err_str:
                        error_types["import_error"] += 1
                    elif "pip" in err_str or "install" in err_str:
                        error_types["pip_install"] += 1
                    elif "clone" in err_str or "clone" in err_str:
                        error_types["clone_failed"] += 1
                    elif "timeout" in err_str:
                        error_types["timeout"] += 1
                    elif "venv" in err_str or "virtualenv" in err_str:
                        error_types["venv_error"] += 1
                    elif "not found" in err_str or "找不到" in err_str:
                        error_types["not_found"] += 1
                    elif "permission" in err_str:
                        error_types["permission"] += 1
                    else:
                        error_types["other"] += 1
            except Exception:
                pass

        if not error_types:
            lines.append("  暂无错误记录。")
            return lines

        lines.append(f"  总错误数: {total_errors}")
        for etype, count in error_types.most_common(8):
            label = {
                "import_error": "模块导入错误",
                "pip_install": "pip安装失败",
                "clone_failed": "克隆失败",
                "timeout": "超时",
                "venv_error": "虚拟环境错误",
                "not_found": "文件/资源未找到",
                "permission": "权限错误",
                "other": "其他",
            }.get(etype, etype)
            pct = (count / total_errors * 100) if total_errors > 0 else 0
            lines.append(f"  {label}: {count} ({pct:.1f}%)")

        return lines
