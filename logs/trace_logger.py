# ============================================================
# TraceLogger - Trace日志记录器
# ============================================================
"""
Trace日志记录器。

将Trace记录到文件或数据库，
支持后续分析和评估。
"""

import json
import os
from datetime import datetime
from pathlib import Path

from dto.trace import Trace


class TraceLogger:
    """
    Trace日志记录器

    将Trace记录到文件系统。
    生产环境可替换为数据库存储。
    """

    def __init__(self, log_dir: str = "./logs/traces"):
        """
        初始化日志记录器

        Args:
            log_dir: 日志目录
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    async def save_trace(self, trace: Trace) -> str:
        """
        保存Trace到文件

        Args:
            trace: Trace对象

        Returns:
            str: 保存的文件路径
        """
        # 生成文件名
        timestamp = trace.started_at.strftime("%Y%m%d_%H%M%S")
        filename = f"{trace.trace_id}_{timestamp}.json"
        filepath = self.log_dir / filename

        # 转换为字典并保存
        data = trace.to_dict()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return str(filepath)

    async def load_trace(self, trace_id: str) -> Trace | None:
        """
        从文件加载Trace

        Args:
            trace_id: Trace ID

        Returns:
            Trace: Trace对象，不存在返回None
        """
        # 查找文件
        for filepath in self.log_dir.glob(f"{trace_id}_*.json"):
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
                # TODO: 反序列化为Trace对象
                return data

        return None

    async def list_traces(
        self,
        limit: int = 100,
    ) -> list[dict]:
        """
        列出所有Trace

        Args:
            limit: 返回数量

        Returns:
            list[dict]: Trace概要列表
        """
        traces = []

        for filepath in sorted(
            self.log_dir.glob("*.json"),
            key=os.path.getmtime,
            reverse=True,
        )[:limit]:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
                traces.append({
                    "trace_id": data.get("trace_id"),
                    "session_id": data.get("session_id"),
                    "mode": data.get("mode"),
                    "task_description": data.get("task_description", "")[:50],
                    "success": data.get("success"),
                    "started_at": data.get("started_at"),
                })

        return traces
