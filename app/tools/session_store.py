"""
SessionStore — 会话状态持久化

保存对话上下文到磁盘，支持页面刷新后恢复。
每次用户发消息、每次收到响应时自动保存。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger


class SessionStore:
    """文件-backed 会话存储器，按 thread_id 隔离。"""

    def __init__(self, store_dir: str = "./data/sessions"):
        self._dir = Path(store_dir)
        self._log = get_logger("session_store")

    def save(self, thread_id: str, data: dict):
        """保存会话快照。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{self._safe_name(thread_id)}.json"
        try:
            # Keep only essential keys, trim large fields
            snapshot = {
                "thread_id": thread_id,
                "timestamp": datetime.now().isoformat(),
                "paper_content": (data.get("paper_content") or "")[:5000],
                "last_result": self._trim_result(data.get("last_result")),
                "messages": data.get("_messages", [])[-100:],
                "user_messages": data.get("_user_messages", [])[-20:],
                "agent_running": data.get("agent_running", False),
            }
            path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            self._log.warning(f"Session save failed: {e}")

    def load(self, thread_id: str) -> Optional[dict]:
        """加载上一次的会话快照。"""
        path = self._dir / f"{self._safe_name(thread_id)}.json"
        if not path.exists():
            # Also try the legacy thread ID (before refresh)
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            self._log.warning(f"Session load failed: {e}")
            return None

    def load_latest(self) -> Optional[dict]:
        """加载最近一次非空白会话快照（跨线程恢复用）。
        跳过 blank 会话（无 last_result、无 paper_content、无 user_messages）。
        """
        if not self._dir.exists():
            return None
        files = sorted(self._dir.glob("*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                # 只要有任一有意义的数据就接受
                if data.get("last_result") or data.get("paper_content") or data.get("messages"):
                    return data
            except Exception:
                continue
        return None

    def delete(self, thread_id: str):
        """删除指定线程的会话快照。"""
        path = self._dir / f"{self._safe_name(thread_id)}.json"
        if path.exists():
            path.unlink()

    @staticmethod
    def _safe_name(thread_id: str) -> str:
        """将 thread_id 转为安全的文件名。"""
        import re
        return re.sub(r'[^a-zA-Z0-9_-]', '_', thread_id)[:80]

    @staticmethod
    def _trim_result(result: Optional[dict]) -> Optional[dict]:
        """精简 last_result，去掉过大的字段。"""
        if not result:
            return None
        return {
            "goal": result.get("goal", "")[:100],
            "success": result.get("success", False),
            "summary": result.get("summary", "")[:500],
            "source_url": result.get("source_url", ""),
            "error_count": len(result.get("errors", [])),
        }


# Module singleton
_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
