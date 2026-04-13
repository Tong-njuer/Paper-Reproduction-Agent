# ============================================================
# 记忆模块
# ============================================================
# 管理 Agent 记忆 - 短期和长期。
# 存储执行历史、经验教训和错误模式。
#
# Memory Types:
#   - Short-term: 最近的步骤和当前上下文
#   - Long-term: 持久的经验教训和模式
#
# Console Output:
#   - Memory operations
#   - Retrieved context
#   - Learning updates
# ============================================================

import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field


class ShortTermMemory(BaseModel):
    """
    最近执行上下文的短期记忆。

    Attributes:
        last_action: 最近的操作
        last_observation: 最近的观察
        last_error: 最近的错误（如果有）
        recent_steps: 用于上下文的最近 N 个步骤
    """
    last_action: str = ""
    last_observation: str = ""
    last_error: Optional[str] = None
    recent_steps: List[Dict[str, Any]] = Field(default_factory=list)


class LongTermMemoryEntry(BaseModel):
    """
    长期记忆中的单个条目。

    Attributes:
        id: 唯一标识符
        error_pattern: 此条处理的错误类型
        successful_fix: 成功修复的方法
        times_applied: 使用次数
        success_rate: 成功率
        created_at: 学习时间
        last_used: 最后使用时间
    """
    id: str
    error_pattern: str
    successful_fix: str
    times_applied: int = 0
    success_rate: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    last_used: datetime = Field(default_factory=datetime.now)


class Memory(BaseModel):
    """
    Agent 的完整记忆系统。

    管理短期（临时）和长期（持久）记忆。

    Attributes:
        enabled: 是否启用记忆
        memory_dir: 持久化存储目录
        short_term: 短期记忆
        long_term: 长期记忆条目
    """
    enabled: bool = True
    memory_dir: str = "./data/memory"
    short_term: ShortTermMemory = Field(default_factory=ShortTermMemory)
    long_term: List[LongTermMemoryEntry] = Field(default_factory=list)

    def __init__(self, **data):
        """Initialize Memory and ensure storage directory exists."""
        super().__init__(**data)
        if self.enabled:
            self._ensure_storage_dir()
            self._load_long_term()

    def _ensure_storage_dir(self) -> None:
        """Ensure the memory storage directory exists."""
        Path(self.memory_dir).mkdir(parents=True, exist_ok=True)

    def _load_long_term(self) -> None:
        """Load long-term memory from disk."""
        memory_file = Path(self.memory_dir) / "long_term_memory.json"
        if memory_file.exists():
            try:
                with open(memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.long_term = [
                        LongTermMemoryEntry(**entry) for entry in data
                    ]
                print(f"[OK] Loaded {len(self.long_term)} long-term memory entries")
            except Exception as e:
                print(f"[!]  Failed to load long-term memory: {e}")

    def _save_long_term(self) -> None:
        """Save long-term memory to disk."""
        if not self.enabled:
            return

        memory_file = Path(self.memory_dir) / "long_term_memory.json"
        try:
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(
                    [entry.model_dump() for entry in self.long_term],
                    f,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            print(f"[SAVE] Saved {len(self.long_term)} long-term memory entries")
        except Exception as e:
            print(f"[X] Failed to save long-term memory: {e}")

    def update_short_term(
        self,
        action: str,
        observation: str,
        error: Optional[str] = None,
    ) -> None:
        """
        用最新执行信息更新短期记忆。

        Args:
            action: 执行的操作
            observation: 观察结果
            error: 可选的错误消息
        """
        self.short_term.last_action = action
        self.short_term.last_observation = observation
        self.short_term.last_error = error

        print(f"\n[BRAIN] Short-term Memory Updated:")
        print(f"   Last Action: {action}")
        print(f"   Observation: {observation[:50]}..." if observation else "   Observation: None")
        if error:
            print(f"   Last Error: {error[:50]}...")

    def add_step_to_history(self, step_data: Dict[str, Any]) -> None:
        """
        Add a step to recent history.

        Args:
            step_data: Step information to store
        """
        self.short_term.recent_steps.append(step_data)
        # Keep only last 10 steps
        if len(self.short_term.recent_steps) > 10:
            self.short_term.recent_steps = self.short_term.recent_steps[-10:]

    def learn_from_error(
        self,
        error: str,
        fix: str,
        success: bool,
    ) -> None:
        """
        从错误和修复中学习。

        Args:
            error: 遇到的错误
            fix: 应用的修复
            success: 修复是否成功
        """
        if not self.enabled:
            return

        print(f"\n[LEARN] Learning from experience:")
        print(f"   Error: {error[:50]}...")
        print(f"   Fix: {fix[:50]}...")
        print(f"   Success: {success}")

        # Check if we already have this error pattern
        for entry in self.long_term:
            if error.lower() in entry.error_pattern.lower():
                # Update existing entry
                entry.times_applied += 1
                if success:
                    entry.success_rate = (
                        entry.success_rate * (entry.times_applied - 1) + 1.0
                    ) / entry.times_applied
                else:
                    entry.success_rate = (
                        entry.success_rate * (entry.times_applied - 1)
                    ) / entry.times_applied
                entry.last_used = datetime.now()
                print(f"   Updated existing memory entry (applied {entry.times_applied} times)")
                self._save_long_term()
                return

        # Create new entry
        new_entry = LongTermMemoryEntry(
            id=f"mem_{len(self.long_term) + 1}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            error_pattern=error,
            successful_fix=fix,
            times_applied=1,
            success_rate=1.0 if success else 0.0,
        )
        self.long_term.append(new_entry)
        print(f"   Created new memory entry: {new_entry.id}")
        self._save_long_term()

    def recall_similar_errors(self, error: str, limit: int = 3) -> List[LongTermMemoryEntry]:
        """
        从长期记忆中检索相似的错误模式。

        Args:
            error: 当前错误用于匹配
            limit: 最大结果数

        Returns:
            匹配的长期记忆条目列表
        """
        if not self.enabled or not self.long_term:
            return []

        # Simple keyword matching
        error_words = set(error.lower().split())
        matches = []

        for entry in self.long_term:
            entry_words = set(entry.error_pattern.lower().split())
            # Calculate similarity based on shared words
            shared = error_words & entry_words
            if shared:
                matches.append((entry, len(shared)))

        # Sort by similarity and return top N
        matches.sort(key=lambda x: x[1], reverse=True)
        results = [m[0] for m in matches[:limit]]

        if results:
            print(f"\n[SEARCH] Recalled {len(results)} similar errors from memory:")
            for entry in results:
                print(f"   - [{entry.id}] Applied {entry.times_applied}x, success: {entry.success_rate:.0%}")

        return results

    def get_context_for_prompt(self) -> str:
        """
        Get formatted context string for LLM prompts.

        Returns:
            str: Formatted memory context
        """
        parts = []

        # Add recent history
        if self.short_term.recent_steps:
            parts.append("Recent steps:")
            for step in self.short_term.recent_steps[-3:]:
                parts.append(f"- {step.get('action', 'unknown')}: {step.get('observation', '')[:50]}")

        # Add last error if any
        if self.short_term.last_error:
            parts.append(f"Last error: {self.short_term.last_error}")

        # Add top long-term memories
        if self.long_term:
            top_memories = sorted(
                self.long_term,
                key=lambda x: (x.times_applied, x.success_rate),
                reverse=True,
            )[:3]
            parts.append("\nLearned patterns:")
            for mem in top_memories:
                parts.append(f"- {mem.error_pattern[:40]}... -> {mem.successful_fix[:40]}...")

        return "\n".join(parts) if parts else "No memory context available"

    def print_memory_status(self) -> None:
        """
        Print current memory status to console.
        """
        print("\n" + "=" * 50)
        print("[BRAIN] Memory Status")
        print("=" * 50)
        print(f"   Enabled: {self.enabled}")
        print(f"   Storage: {self.memory_dir}")
        print(f"   Short-term entries: {len(self.short_term.recent_steps)}")
        print(f"   Long-term entries: {len(self.long_term)}")

        if self.short_term.last_action:
            print(f"\n[STEP] Last Action: {self.short_term.last_action}")
        if self.short_term.last_error:
            print(f"[!]  Last Error: {self.short_term.last_error[:50]}...")

        print("=" * 50 + "\n")


# ============================================================
# Global Memory Instance
# ============================================================
_memory: Optional[Memory] = None


def get_memory(enabled: bool = True, memory_dir: str = "./data/memory") -> Memory:
    """
    Get the global memory instance.

    Args:
        enabled: Whether to enable memory
        memory_dir: Directory for storage

    Returns:
        Memory: Global memory instance
    """
    global _memory
    if _memory is None:
        _memory = Memory(enabled=enabled, memory_dir=memory_dir)
    return _memory


def clear_memory() -> None:
    """Clear the global memory instance."""
    global _memory
    _memory = None
