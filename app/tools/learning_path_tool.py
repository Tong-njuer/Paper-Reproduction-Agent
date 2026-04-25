"""Learning path planning tool."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.tools import BaseTool, ToolResult


class LearningPathTool(BaseTool):
    """生成结构化学习路径，支持阶段拆解和验收标准。"""

    name = "learning_path_tool"
    description = (
        "Generate a staged learning path. "
        "Args: topic (required), level, weeks, focus, output_format."
    )

    _VALID_LEVELS = {"beginner", "intermediate", "advanced"}

    def execute(self, **kwargs: Any) -> ToolResult:
        topic = str(kwargs.get("topic") or kwargs.get("goal") or "").strip()
        if not topic:
            return self._error("Missing required argument: topic")

        level = str(kwargs.get("level", "beginner")).strip().lower()
        if level not in self._VALID_LEVELS:
            return self._error(
                f"Invalid level: {level}",
                allowed=sorted(self._VALID_LEVELS),
            )

        weeks = self._coerce_weeks(kwargs.get("weeks", 4))
        focus = str(kwargs.get("focus", "practical reproduction")).strip()
        output_format = str(kwargs.get("output_format", "markdown")).strip().lower()

        plan = self._build_plan(topic=topic, level=level, weeks=weeks, focus=focus)

        if output_format == "json":
            output = json.dumps(plan, ensure_ascii=False, indent=2)
        else:
            output = self._to_markdown(plan)

        return self._success(
            output=output,
            topic=topic,
            level=level,
            weeks=weeks,
            focus=focus,
            plan=plan,
        )

    def _build_plan(self, topic: str, level: str, weeks: int, focus: str) -> Dict[str, Any]:
        phase_titles = [
            "Concept Foundation",
            "Environment & Tooling",
            "Guided Practice",
            "Independent Reproduction",
        ]

        if weeks <= 3:
            phase_titles = phase_titles[:3]

        phases: List[Dict[str, Any]] = []
        phase_weeks = max(1, weeks // len(phase_titles))
        extra_weeks = weeks - phase_weeks * len(phase_titles)

        current_week = 1
        for index, title in enumerate(phase_titles):
            duration = phase_weeks + (1 if index < extra_weeks else 0)
            start_week = current_week
            end_week = current_week + duration - 1
            current_week = end_week + 1

            phases.append(
                {
                    "phase": index + 1,
                    "title": title,
                    "week_range": f"W{start_week}-W{end_week}",
                    "objectives": self._phase_objectives(title, topic, level, focus),
                    "deliverables": self._phase_deliverables(title, topic),
                    "exit_criteria": self._phase_exit_criteria(title),
                }
            )

        return {
            "topic": topic,
            "level": level,
            "total_weeks": weeks,
            "focus": focus,
            "phases": phases,
        }

    def _phase_objectives(self, title: str, topic: str, level: str, focus: str) -> List[str]:
        mapping = {
            "Concept Foundation": [
                f"Understand core concepts of {topic} at {level} depth",
                "Map key terminology, assumptions and constraints",
                f"Define learning scope around {focus}",
            ],
            "Environment & Tooling": [
                "Prepare reproducible local environment",
                "Verify dependency installation and sample commands",
                "Create baseline runbook for repeatable execution",
            ],
            "Guided Practice": [
                "Follow one complete reference implementation",
                "Record issues and corresponding fixes",
                "Summarize reproducible checkpoints",
            ],
            "Independent Reproduction": [
                "Reproduce target workflow independently",
                "Compare outputs against expected metrics",
                "Produce final report with risks and next steps",
            ],
        }
        return mapping.get(title, [f"Deepen understanding of {topic}"])

    def _phase_deliverables(self, title: str, topic: str) -> List[str]:
        mapping = {
            "Concept Foundation": [
                f"One-page concept notes for {topic}",
                "Glossary of critical terms",
            ],
            "Environment & Tooling": [
                "Environment setup checklist",
                "Dependency lock snapshot",
            ],
            "Guided Practice": [
                "Executed notebook/script logs",
                "Issue-fix matrix",
            ],
            "Independent Reproduction": [
                "End-to-end reproduction report",
                "Validation summary and gap list",
            ],
        }
        return mapping.get(title, ["Checkpoint notes"])

    def _phase_exit_criteria(self, title: str) -> List[str]:
        mapping = {
            "Concept Foundation": [
                "Can explain pipeline and assumptions without notes",
            ],
            "Environment & Tooling": [
                "Can initialize and run baseline command in one attempt",
            ],
            "Guided Practice": [
                "Can rerun guided workflow with stable output",
            ],
            "Independent Reproduction": [
                "Can reproduce target result and explain deviations",
            ],
        }
        return mapping.get(title, ["Phase goals achieved"])

    def _coerce_weeks(self, value: Any) -> int:
        try:
            weeks = int(value)
        except (TypeError, ValueError):
            return 4
        return max(1, min(weeks, 24))

    def _to_markdown(self, plan: Dict[str, Any]) -> str:
        lines: List[str] = []
        lines.append(f"# Learning Path: {plan['topic']}")
        lines.append("")
        lines.append(f"- Level: {plan['level']}")
        lines.append(f"- Duration: {plan['total_weeks']} weeks")
        lines.append(f"- Focus: {plan['focus']}")
        lines.append("")

        for phase in plan["phases"]:
            lines.append(f"## Phase {phase['phase']} - {phase['title']} ({phase['week_range']})")
            lines.append("Objectives:")
            for item in phase["objectives"]:
                lines.append(f"- {item}")
            lines.append("Deliverables:")
            for item in phase["deliverables"]:
                lines.append(f"- {item}")
            lines.append("Exit Criteria:")
            for item in phase["exit_criteria"]:
                lines.append(f"- {item}")
            lines.append("")

        return "\n".join(lines).strip()
