"""Schedule management tool for execution planning."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.tools import BaseTool, ToolResult


@dataclass
class _ScheduleStorage:
    path: Path

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"plans": {}}
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {"plans": {}}

    def save(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)


class ScheduleTool(BaseTool):
    """维护任务计划、进度和时间预算。"""

    name = "schedule_tool"
    description = (
        "Manage execution schedules. "
        "Actions: create_plan, get_plan, update_progress, list_plans, increase_timeout."
    )

    def __init__(self) -> None:
        self._storage = _ScheduleStorage(
            path=Path("workspace") / "tool_data" / "schedule_store.json"
        )

    def execute(self, **kwargs: Any) -> ToolResult:
        action = str(kwargs.get("action", "create_plan")).strip().lower()

        handlers = {
            "create_plan": self._create_plan,
            "get_plan": self._get_plan,
            "update_progress": self._update_progress,
            "list_plans": self._list_plans,
            "increase_timeout": self._increase_timeout,
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
            return self._error(f"Schedule tool error: {exc}", action=action)

    def _create_plan(self, kwargs: Dict[str, Any]) -> ToolResult:
        goal = str(kwargs.get("goal", "")).strip()
        if not goal:
            return self._error("create_plan requires argument: goal")

        raw_tasks = kwargs.get("tasks")
        tasks = self._normalize_tasks(raw_tasks)
        if not tasks:
            tasks = [
                "Collect requirements",
                "Prepare environment",
                "Execute validation steps",
                "Document findings",
            ]

        plan_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        plan = {
            "plan_id": plan_id,
            "goal": goal,
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "tasks": [
                {
                    "task_id": idx + 1,
                    "title": task,
                    "status": "pending",
                    "updated_at": now,
                }
                for idx, task in enumerate(tasks)
            ],
        }

        store = self._storage.load()
        store.setdefault("plans", {})[plan_id] = plan
        self._storage.save(store)

        return self._success(
            output=f"Plan created: {plan_id}",
            plan_id=plan_id,
            goal=goal,
            task_count=len(tasks),
        )

    def _get_plan(self, kwargs: Dict[str, Any]) -> ToolResult:
        plan_id = str(kwargs.get("plan_id", "")).strip()
        if not plan_id:
            return self._error("get_plan requires argument: plan_id")

        store = self._storage.load()
        plan = store.get("plans", {}).get(plan_id)
        if not plan:
            return self._error(f"Plan not found: {plan_id}", plan_id=plan_id)

        return self._success(
            output=json.dumps(plan, ensure_ascii=False, indent=2),
            plan_id=plan_id,
            plan=plan,
        )

    def _update_progress(self, kwargs: Dict[str, Any]) -> ToolResult:
        plan_id = str(kwargs.get("plan_id", "")).strip()
        task_id_raw = kwargs.get("task_id")
        status = str(kwargs.get("status", "")).strip().lower()

        if not plan_id:
            return self._error("update_progress requires argument: plan_id")
        if task_id_raw is None:
            return self._error("update_progress requires argument: task_id")
        if status not in {"pending", "in_progress", "completed", "failed", "skipped"}:
            return self._error(
                f"Invalid task status: {status}",
                allowed=["pending", "in_progress", "completed", "failed", "skipped"],
            )

        try:
            task_id = int(task_id_raw)
        except (TypeError, ValueError):
            return self._error("task_id must be an integer")

        store = self._storage.load()
        plan = store.get("plans", {}).get(plan_id)
        if not plan:
            return self._error(f"Plan not found: {plan_id}", plan_id=plan_id)

        tasks: List[Dict[str, Any]] = plan.get("tasks", [])
        matched = None
        for task in tasks:
            if int(task.get("task_id", -1)) == task_id:
                matched = task
                break

        if matched is None:
            return self._error(f"Task not found: {task_id}", plan_id=plan_id, task_id=task_id)

        now = datetime.now(timezone.utc).isoformat()
        matched["status"] = status
        matched["updated_at"] = now
        plan["updated_at"] = now

        if all(task.get("status") in {"completed", "skipped"} for task in tasks):
            plan["status"] = "completed"
        elif any(task.get("status") == "failed" for task in tasks):
            plan["status"] = "at_risk"
        else:
            plan["status"] = "active"

        store["plans"][plan_id] = plan
        self._storage.save(store)

        return self._success(
            output=f"Updated task {task_id} to {status}.",
            plan_id=plan_id,
            task_id=task_id,
            status=status,
            plan_status=plan["status"],
        )

    def _list_plans(self, _: Dict[str, Any]) -> ToolResult:
        store = self._storage.load()
        plans = list(store.get("plans", {}).values())

        lightweight = [
            {
                "plan_id": p.get("plan_id"),
                "goal": p.get("goal"),
                "status": p.get("status"),
                "task_count": len(p.get("tasks", [])),
                "updated_at": p.get("updated_at"),
            }
            for p in plans
        ]

        return self._success(
            output=json.dumps(lightweight, ensure_ascii=False, indent=2),
            count=len(lightweight),
            plans=lightweight,
        )

    def _increase_timeout(self, kwargs: Dict[str, Any]) -> ToolResult:
        current_timeout = kwargs.get("current_timeout", 30)
        factor = kwargs.get("factor", 1.5)
        max_timeout = kwargs.get("max_timeout", 3600)

        try:
            current = max(1, int(current_timeout))
            factor_value = max(1.0, float(factor))
            max_value = max(1, int(max_timeout))
        except (TypeError, ValueError):
            return self._error("Invalid numeric arguments for increase_timeout")

        new_timeout = min(max_value, int(current * factor_value))
        output = f"Recommended timeout increase: {current}s -> {new_timeout}s"

        return self._success(
            output=output,
            current_timeout=current,
            factor=factor_value,
            max_timeout=max_value,
            recommended_timeout=new_timeout,
        )

    def _normalize_tasks(self, raw_tasks: Any) -> List[str]:
        if raw_tasks is None:
            return []

        if isinstance(raw_tasks, list):
            return [str(item).strip() for item in raw_tasks if str(item).strip()]

        if isinstance(raw_tasks, str):
            chunks = [item.strip() for item in raw_tasks.split(";")]
            return [chunk for chunk in chunks if chunk]

        return []
