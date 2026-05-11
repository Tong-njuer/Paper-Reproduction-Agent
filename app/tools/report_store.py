"""
Report persistence — save, list, and view past execution reports.

Reports are stored as JSON files in data/reports/.  Each report gets a
unique ID and records the goal, success status, summary, steps, source
URL, paper info, errors, and timestamp.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger
from app.tools import BaseTool, ToolResult

# Module-level singleton so the orchestrator and tools share the same store.
_store: Optional["ReportStore"] = None


def get_report_store() -> "ReportStore":
    global _store
    if _store is None:
        _store = ReportStore()
    return _store


# ---------------------------------------------------------------------------
# Storage backend
# ---------------------------------------------------------------------------

class ReportStore:
    """JSON-file-backed report storage."""

    def __init__(self, store_dir: str = "./data/reports"):
        self._dir = Path(store_dir)
        self._log = get_logger("report_store")

    @property
    def dir(self) -> Path:
        return self._dir

    def save(self, report: dict) -> str:
        """Persist a report dict. Returns the report ID."""
        self._dir.mkdir(parents=True, exist_ok=True)
        report_id = report.get("id") or self._make_id()
        report["id"] = report_id
        path = self._dir / f"{report_id}.json"
        try:
            path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            self._log.info(f"Report saved: {report_id} → {path}")
        except Exception as e:
            self._log.error(f"Failed to save report {report_id}: {e}")
        return report_id

    def list(self) -> list[dict]:
        """Return all reports sorted by timestamp (newest first)."""
        if not self._dir.exists():
            return []
        reports = []
        for p in sorted(self._dir.glob("*.json"),
                        key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                reports.append({
                    "id": data.get("id", p.stem),
                    "goal": data.get("goal", "")[:120],
                    "success": data.get("success", False),
                    "timestamp": data.get("timestamp", ""),
                    "source_url": data.get("source_url", "")[:80],
                    "step_count": len(data.get("steps", [])),
                    "error_count": len(data.get("errors", [])),
                })
            except Exception:
                pass
        return reports

    def get(self, report_id: str) -> Optional[dict]:
        """Retrieve a single report by ID."""
        path = self._dir / f"{report_id}.json"
        if not path.exists():
            # Try fuzzy match
            matches = list(self._dir.glob(f"{report_id}*.json"))
            if matches:
                path = matches[0]
            else:
                # Try matching by goal substring
                for p in sorted(self._dir.glob("*.json"),
                                key=lambda x: x.stat().st_mtime, reverse=True):
                    try:
                        data = json.loads(p.read_text(encoding="utf-8"))
                        if report_id.lower() in data.get("goal", "").lower():
                            path = p
                            break
                    except Exception:
                        pass
                else:
                    return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _make_id() -> str:
        return f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class ListReportsTool(BaseTool):
    name = "list_reports_tool"
    description = (
        "列出所有已保存的历史复现报告。无需参数。"
    )

    def __init__(self, store: ReportStore = None):
        self._store = store or ReportStore()

    def execute(self, **kwargs) -> ToolResult:
        reports = self._store.list()
        if not reports:
            return self._ok(output="暂无已保存的报告。", reports=[])

        lines = [f"共 {len(reports)} 份报告:\n"]
        for i, r in enumerate(reports, 1):
            status = "[OK]" if r["success"] else "[FAIL]"
            ts = r.get("timestamp", "")[:16]
            lines.append(
                f"  {i}. {status} {r['goal'][:80]}\n"
                f"     ID: {r['id']}  时间: {ts}  步骤: {r['step_count']}  错误: {r['error_count']}"
            )

        return self._ok(
            output="\n".join(lines),
            reports=reports,
            total=len(reports),
        )


class ViewReportTool(BaseTool):
    name = "view_report_tool"
    description = (
        "查看某一份历史复现报告的完整内容。"
        "参数: report_id(报告ID, 可用 list_reports_tool 获取)"
    )

    def __init__(self, store: ReportStore = None):
        self._store = store or ReportStore()

    def execute(self, report_id: str = "", **kwargs) -> ToolResult:
        if not report_id:
            return self._fail("缺少 report_id 参数。请先使用 list_reports_tool 获取报告ID。")

        report = self._store.get(report_id)
        if not report:
            return self._fail(f"未找到报告 '{report_id}'。请使用 list_reports_tool 查看可用报告。")

        return self._ok(
            output=self._format_report(report),
            report=report,
        )

    def _format_report(self, report: dict) -> str:
        lines = [
            f"## 复现报告: {report.get('goal', '')}",
            f"ID: {report.get('id', '')}",
            f"时间: {report.get('timestamp', '')}",
            f"状态: {'成功' if report.get('success') else '失败'}",
            "",
        ]

        if report.get("source_url"):
            lines.append(f"源码: {report['source_url']}")

        paper_info = report.get("paper_info", {})
        if paper_info:
            if paper_info.get("title"):
                lines.append(f"论文: {paper_info['title']}")
            if paper_info.get("urls"):
                lines.append(f"链接: {', '.join(paper_info['urls'][:3])}")

        lines.append("")

        steps = report.get("steps", [])
        if steps:
            lines.append("### 执行步骤")
            for s in steps:
                icon = {("success", True): "[OK]", ("done", True): "[OK]",
                        ("failed", True): "[FAIL]", ("skipped", True): "[SKIP]"}.get(
                    (s.get("status"), True), "[?]")
                lines.append(f"- {icon} Step {s.get('step_id', '?')}: {s.get('description', '')[:80]}")

        errors = report.get("errors", [])
        if errors:
            lines.append("\n### 错误")
            for e in errors:
                lines.append(f"- {str(e)[:200]}")

        if report.get("summary"):
            lines.append(f"\n### 总结\n{report['summary']}")

        return "\n".join(lines)


class SearchReportsTool(BaseTool):
    name = "search_reports_tool"
    description = (
        "在所有历史报告中按关键词搜索，查找相关复现记录。"
        "参数: query(搜索词)"
    )

    def __init__(self, store: ReportStore = None):
        self._store = store or ReportStore()

    def execute(self, query: str = "", **kwargs) -> ToolResult:
        if not query:
            return self._fail("缺少搜索关键词 (query)")

        reports = self._store.list()
        if not reports:
            return self._ok(output="暂无已保存的报告。", matches=[])

        q = query.lower()
        matches = []
        for r in reports:
            score = 0
            if q in r.get("goal", "").lower():
                score += 3
            if q in r.get("source_url", "").lower():
                score += 2
            if q in r.get("id", "").lower():
                score += 1
            if score > 0:
                r["_score"] = score
                matches.append(r)

        matches.sort(key=lambda x: x["_score"], reverse=True)

        if not matches:
            # Deep search: load full reports and check steps/errors/summary
            all_reports = []
            for p in sorted(self._store.dir.glob("*.json"),
                           key=lambda x: x.stat().st_mtime, reverse=True):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    summary = data.get("summary", "")
                    steps_text = " ".join(
                        s.get("description", "") + " " + s.get("observation", "")
                        for s in data.get("steps", [])
                    )
                    errors_text = " ".join(str(e) for e in data.get("errors", []))
                    full_text = f"{summary} {steps_text} {errors_text}".lower()
                    if q in full_text:
                        matches.append({
                            "id": data.get("id", p.stem),
                            "goal": data.get("goal", "")[:120],
                            "success": data.get("success", False),
                            "timestamp": data.get("timestamp", ""),
                            "source_url": data.get("source_url", "")[:80],
                            "step_count": len(data.get("steps", [])),
                            "error_count": len(data.get("errors", [])),
                            "_score": 1,
                        })
                except Exception:
                    pass

        if not matches:
            return self._ok(
                output=f"未找到包含 '{query}' 的报告。",
                matches=[], query=query,
            )

        lines = [f"搜索 '{query}' 找到 {len(matches)} 份相关报告:\n"]
        for i, r in enumerate(matches[:20], 1):
            status = "[OK]" if r["success"] else "[FAIL]"
            ts = r.get("timestamp", "")[:16]
            lines.append(
                f"  {i}. {status} {r['goal'][:80]}\n"
                f"     ID: {r['id']}  时间: {ts}  相关度: {'★' * min(r['_score'], 3)}"
            )

        return self._ok(
            output="\n".join(lines),
            matches=matches, query=query, total=len(matches),
        )


class DeleteReportTool(BaseTool):
    name = "delete_report_tool"
    description = (
        "删除某一份历史复现报告。参数: report_id(报告ID)"
    )

    def __init__(self, store: ReportStore = None):
        self._store = store or ReportStore()

    def execute(self, report_id: str = "", **kwargs) -> ToolResult:
        if not report_id:
            return self._fail("缺少 report_id 参数。请先使用 list_reports_tool 获取报告ID。")

        path = self._store.dir / f"{report_id}.json"
        if not path.exists():
            # Try fuzzy match
            matches = list(self._store.dir.glob(f"{report_id}*.json"))
            if matches:
                path = matches[0]
            else:
                return self._fail(
                    f"未找到报告 '{report_id}'。"
                    f"请使用 list_reports_tool 查看可用报告。"
                )

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            goal = data.get("goal", report_id)[:80]
            path.unlink()
            return self._ok(
                output=f"已删除报告: {goal}\nID: {path.stem}",
                deleted_id=path.stem,
            )
        except Exception as e:
            return self._fail(f"删除失败: {e}")
