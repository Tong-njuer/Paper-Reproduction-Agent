"""Documentation generation and report persistence tool."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.tools import BaseTool, ToolResult


class DocTool(BaseTool):
    """文档写入、日志追加、复现报告生成工具。"""

    name = "doc_tool"
    description = (
        "Generate and persist documentation artifacts for reproduction workflow. "
        "Actions: write_document, append_log, write_json_artifact, generate_repro_report."
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        action = str(kwargs.get("action", "write_document")).strip().lower()
        handlers = {
            "write_document": self._write_document,
            "append_log": self._append_log,
            "write_json_artifact": self._write_json_artifact,
            "generate_repro_report": self._generate_repro_report,
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
            return self._error(f"Doc tool failed: {exc}", action=action)

    def _write_document(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_path = self._resolve_output_path(kwargs.get("output_path"))
        title = str(kwargs.get("title", "Untitled Document")).strip()
        sections = kwargs.get("sections")

        if sections is None:
            content = str(kwargs.get("content", "")).strip()
            if not content:
                return self._error("write_document requires sections or content")
            body = content
        else:
            body = self._render_sections(sections)

        markdown = f"# {title}\n\n{body}\n"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")

        return self._success(
            output=f"Document written: {output_path}",
            output_path=str(output_path),
            title=title,
            bytes_written=len(markdown.encode("utf-8")),
        )

    def _append_log(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_path = self._resolve_output_path(kwargs.get("output_path"))
        message = str(kwargs.get("message", "")).strip()
        level = str(kwargs.get("level", "INFO")).strip().upper()

        if not message:
            return self._error("append_log requires argument: message")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        line = f"[{timestamp}] [{level}] {message}\n"

        with output_path.open("a", encoding="utf-8") as fh:
            fh.write(line)

        return self._success(
            output=line.strip(),
            output_path=str(output_path),
            level=level,
        )

    def _write_json_artifact(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_path = self._resolve_output_path(kwargs.get("output_path"))
        payload = kwargs.get("payload")

        if payload is None:
            return self._error("write_json_artifact requires argument: payload")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return self._success(
            output=f"JSON artifact written: {output_path}",
            output_path=str(output_path),
        )

    def _generate_repro_report(self, kwargs: Dict[str, Any]) -> ToolResult:
        output_path = self._resolve_output_path(kwargs.get("output_path"))
        goal = str(kwargs.get("goal", "复现任务")).strip()
        paper = kwargs.get("paper", {})
        source = kwargs.get("source", {})
        environment = kwargs.get("environment", {})
        tests = kwargs.get("tests", {})
        reflections = kwargs.get("reflections", [])
        summary = str(kwargs.get("summary", "")).strip()

        lines: List[str] = []
        lines.append(f"# 复现报告: {goal}")
        lines.append("")
        lines.append(f"- 生成时间: {datetime.now(timezone.utc).isoformat()}")
        lines.append("")

        lines.append("## 1. 论文信息")
        lines.append(self._dict_block(paper))
        lines.append("")

        lines.append("## 2. 源码来源")
        lines.append(self._dict_block(source))
        lines.append("")

        lines.append("## 3. 环境与沙箱")
        lines.append(self._dict_block(environment))
        lines.append("")

        lines.append("## 4. 测试与验证")
        lines.append(self._dict_block(tests))
        lines.append("")

        lines.append("## 5. 失败与修复记录")
        if isinstance(reflections, list) and reflections:
            for idx, item in enumerate(reflections, start=1):
                lines.append(f"### 5.{idx}")
                if isinstance(item, dict):
                    lines.append(self._dict_block(item))
                else:
                    lines.append(str(item))
                lines.append("")
        else:
            lines.append("- 无")
            lines.append("")

        lines.append("## 6. 结论")
        lines.append(summary or "暂无结论")
        lines.append("")

        markdown = "\n".join(lines).strip() + "\n"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")

        return self._success(
            output=f"Reproduction report written: {output_path}",
            output_path=str(output_path),
            bytes_written=len(markdown.encode("utf-8")),
        )

    def _render_sections(self, sections: Any) -> str:
        if not isinstance(sections, list) or not sections:
            return ""

        lines: List[str] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            heading = str(section.get("heading", "Section")).strip() or "Section"
            level = int(section.get("level", 2))
            level = max(2, min(level, 4))
            content = str(section.get("content", "")).strip()

            lines.append(f"{'#' * level} {heading}")
            lines.append(content)
            lines.append("")

        return "\n".join(lines).strip()

    def _dict_block(self, payload: Any) -> str:
        if isinstance(payload, dict) and payload:
            return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
        return "- 无"

    def _resolve_output_path(self, value: Any) -> Path:
        path = Path(str(value or "")).expanduser().resolve()
        if not str(path):
            raise ValueError("Missing output_path")
        return path
