import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from app.core.logging import get_logger


class StepRecord:
    def __init__(self, step_id: str, description: str, thought: str = "",
                 action: str = "", action_args: dict = None, observation: str = "",
                 status: str = "pending", error: str = ""):
        self.step_id = step_id
        self.description = description
        self.thought = thought
        self.action = action
        self.action_args = action_args or {}
        self.observation = observation
        self.status = status
        self.error = error
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id, "description": self.description,
            "thought": self.thought, "action": self.action,
            "action_args": self.action_args, "observation": self.observation,
            "status": self.status, "error": self.error,
            "timestamp": self.timestamp,
        }


class LongTermEntry:
    def __init__(self, error_pattern: str, fix_strategy: str,
                 success_count: int = 0, total_count: int = 0):
        self.error_pattern = error_pattern
        self.fix_strategy = fix_strategy
        self.success_count = success_count
        self.total_count = total_count
        self.created_at = datetime.now().isoformat()

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.total_count, 1)

    def to_dict(self) -> dict:
        return {
            "error_pattern": self.error_pattern, "fix_strategy": self.fix_strategy,
            "success_count": self.success_count, "total_count": self.total_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LongTermEntry":
        return cls(
            error_pattern=d["error_pattern"], fix_strategy=d["fix_strategy"],
            success_count=d.get("success_count", 0), total_count=d.get("total_count", 0),
        )


class Memory:
    def __init__(self, enabled: bool = True, memory_dir: str = "./data/memory",
                 short_term_max: int = 10):
        self.enabled = enabled
        self._log = get_logger("memory")
        self.short_term: List[StepRecord] = []
        self.max_short = short_term_max
        self.long_term: List[LongTermEntry] = []
        self.memory_dir = Path(memory_dir)
        # Multi-turn conversation history: past agent run results
        self.conversation_history: List[dict] = []
        self.max_history: int = 10
        if self.enabled:
            self._load_long_term()
            self._load_conversation_history()

    def remember_run(self, result: dict):
        """Store a completed agent run for multi-turn context."""
        if not self.enabled:
            return
        self.conversation_history.append({
            "goal": result.get("goal", "")[:100],
            "success": result.get("success", False),
            "summary": result.get("summary", "")[:500],
            "source_url": result.get("source_url", ""),
            "error_count": len(result.get("errors", [])),
            "timestamp": datetime.now().isoformat(),
        })
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]
        self._save_conversation_history()

    def _save_conversation_history(self):
        path = self.memory_dir / "conversation_history.json"
        try:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self.conversation_history, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            self._log.warning(f"Failed to save conversation history: {e}")

    def _load_conversation_history(self):
        path = self.memory_dir / "conversation_history.json"
        if path.exists():
            try:
                self.conversation_history = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                self._log.warning(f"Failed to load conversation history: {e}")

    def add_step(self, record: StepRecord):
        if not self.enabled:
            return
        self.short_term.append(record)
        if len(self.short_term) > self.max_short:
            self.short_term = self.short_term[-self.max_short:]

    def update_last(self, status: str = "", observation: str = "", error: str = ""):
        if not self.short_term:
            return
        rec = self.short_term[-1]
        if status:
            rec.status = status
        if observation:
            rec.observation = observation
        if error:
            rec.error = error

    def learn_from_error(self, error_pattern: str, fix_strategy: str):
        if not self.enabled:
            return
        for entry in self.long_term:
            if entry.error_pattern == error_pattern:
                entry.total_count += 1
                entry.fix_strategy = fix_strategy
                self._save_long_term()
                return
        self.long_term.append(LongTermEntry(
            error_pattern=error_pattern, fix_strategy=fix_strategy, total_count=1))
        self._save_long_term()
        self._log.info(f"Learned pattern: {error_pattern}")

    def recall(self, error_keywords: str, top_k: int = 3) -> List[LongTermEntry]:
        keywords = error_keywords.lower().split()
        scored = []
        for entry in self.long_term:
            score = sum(1 for kw in keywords if kw in entry.error_pattern.lower())
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]

    def context_for_prompt(self) -> str:
        parts = []
        # Recent execution steps
        if self.short_term:
            recent = self.short_term[-5:]
            parts.append("## 近期执行记录")
            for r in recent:
                parts.append(
                    f"- [{r.step_id}] {r.description}: {r.status}"
                    + (f" | 错误: {r.error}" if r.error else "")
                )
        # Conversation history (previous runs)
        if self.conversation_history:
            parts.append("\n## 对话历史（之前的复现任务）")
            for i, run in enumerate(reversed(self.conversation_history[-3:]), 1):
                parts.append(
                    f"- 第{i}次: {run['goal']} "
                    f"({'✅成功' if run['success'] else '❌失败'})"
                    f" | {run.get('source_url', '')}"
                )
        # Long-term learned patterns
        if self.long_term:
            parts.append("\n## 历史经验")
            for e in self.long_term[-5:]:
                parts.append(f"- 问题: {e.error_pattern} → 方案: {e.fix_strategy}")
        return "\n".join(parts)

    def summary(self) -> dict:
        return {
            "short_term_count": len(self.short_term),
            "long_term_count": len(self.long_term),
            "conversation_count": len(self.conversation_history),
        }

    def _load_long_term(self):
        path = self.memory_dir / "long_term_memory.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.long_term = [LongTermEntry.from_dict(d) for d in data]
            except Exception as e:
                self._log.warning(f"Failed to load long-term memory: {e}")

    def _save_long_term(self):
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        (self.memory_dir / "long_term_memory.json").write_text(
            json.dumps([e.to_dict() for e in self.long_term], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
