# ============================================================
# TraceService - Trace记录服务
# ============================================================
"""
Trace记录服务。

负责：
- 保存Trace记录
- 查询Trace
- 生成Timeline数据
"""

from datetime import datetime
from typing import Any

from dto.trace import Trace, TraceTimeline, StepSummary


class TraceService:
    """
    Trace服务

    管理Trace记录的存储和查询。
    目前使用内存存储，生产环境应使用数据库。
    """

    def __init__(self):
        """初始化Trace服务"""
        self._traces: dict[str, Trace] = {}

    async def save_trace(self, trace: Trace) -> None:
        """
        保存Trace记录

        Args:
            trace: Trace对象
        """
        self._traces[trace.trace_id] = trace

    async def get_trace(self, trace_id: str) -> Trace | None:
        """
        获取Trace

        Args:
            trace_id: Trace ID

        Returns:
            Trace: Trace对象，不存在返回None
        """
        return self._traces.get(trace_id)

    async def get_session_traces(
        self, session_id: str, limit: int = 10
    ) -> list[Trace]:
        """
        获取会话的所有Trace

        Args:
            session_id: 会话ID
            limit: 返回数量限制

        Returns:
            list[Trace]: Trace列表
        """
        traces = [
            t for t in self._traces.values()
            if t.session_id == session_id
        ]
        # 按时间倒序
        traces.sort(key=lambda t: t.started_at, reverse=True)
        return traces[:limit]

    async def get_timeline(self, trace_id: str) -> TraceTimeline | None:
        """
        生成Timeline展示数据

        Args:
            trace_id: Trace ID

        Returns:
            TraceTimeline: Timeline数据
        """
        trace = self._traces.get(trace_id)
        if trace is None:
            return None

        # 生成步骤概要
        steps_summary = []
        for i, step in enumerate(trace.steps):
            summary = StepSummary(
                step_id=i + 1,
                thought_preview=step.thought[:100] if step.thought else "",
                action_preview=step.action or "",
                tool_name=step.tool_name,
                status=step.status.value,
                duration_ms=step.duration_ms,
            )
            steps_summary.append(summary)

        # 统计信息
        statistics = {
            "total_steps": len(trace.steps),
            "total_duration_seconds": trace.total_duration_seconds,
            "tool_usage": trace.tool_usage,
            "error_count": trace.error_count,
            "success": trace.success,
        }

        return TraceTimeline(
            trace_id=trace_id,
            total_steps=len(trace.steps),
            steps_summary=steps_summary,
            statistics=statistics,
        )

    async def list_traces(
        self,
        user_id: str | None = None,
        mode: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        列出Trace记录

        Args:
            user_id: 用户ID（可选）
            mode: 模式（可选）
            limit: 返回数量限制

        Returns:
            list[dict]: Trace概要列表
        """
        traces = list(self._traces.values())

        # 过滤
        if user_id:
            traces = [t for t in traces if t.user_id == user_id]
        if mode:
            traces = [t for t in traces if t.mode == mode]

        # 排序
        traces.sort(key=lambda t: t.started_at, reverse=True)

        # 转换为概要
        return [
            {
                "trace_id": t.trace_id,
                "session_id": t.session_id,
                "user_id": t.user_id,
                "mode": t.mode,
                "task_description": t.task_description[:50] + "..." if len(t.task_description) > 50 else t.task_description,
                "success": t.success,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "total_duration_seconds": t.total_duration_seconds,
                "steps_count": len(t.steps),
            }
            for t in traces[:limit]
        ]

    async def delete_trace(self, trace_id: str) -> bool:
        """
        删除Trace

        Args:
            trace_id: Trace ID

        Returns:
            bool: 是否成功删除
        """
        if trace_id in self._traces:
            del self._traces[trace_id]
            return True
        return False

    def clear(self) -> None:
        """清空所有Trace（仅用于测试）"""
        self._traces.clear()
