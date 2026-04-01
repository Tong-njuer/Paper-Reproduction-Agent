# ============================================================
# AgentController - Agent API控制器
# ============================================================
"""
Agent API控制器。

提供以下端点：
- POST /api/agent/run - 运行Agent任务
- GET /api/trace/{trace_id} - 获取Trace详情
- GET /api/trace/{trace_id}/timeline - 获取Timeline数据
- GET /api/modes - 列出所有模式
- GET /api/traces - 列出历史Trace
"""

from typing import Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse

from dto.request import AgentRequest
from dto.response import AgentResponse
from service.agent_service import AgentService
from service.trace_service import TraceService

# 创建路由
router = APIRouter(prefix="/api", tags=["agent"])

# 全局服务实例（简化实现）
_agent_service: AgentService | None = None
_trace_service: TraceService | None = None


def get_agent_service() -> AgentService:
    """获取Agent服务实例"""
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService()
    return _agent_service


def get_trace_service() -> TraceService:
    """获取Trace服务实例"""
    global _trace_service
    if _trace_service is None:
        _trace_service = TraceService()
    return _trace_service


@router.post("/agent/run", response_model=dict[str, Any])
async def run_agent(request: AgentRequest):
    """
    运行Agent任务

    发起一个新的Agent执行任务。

    Args:
        request: Agent请求

    Returns:
        AgentResponse: Agent响应
    """
    service = get_agent_service()
    response = await service.run_agent(request)
    return response.to_dict()


@router.get("/trace/{trace_id}", response_model=dict[str, Any])
async def get_trace(trace_id: str):
    """
    获取Trace详情

    Args:
        trace_id: Trace ID

    Returns:
        Trace详情
    """
    service = get_trace_service()
    trace = await service.get_trace(trace_id)

    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    return trace.to_dict()


@router.get("/trace/{trace_id}/timeline")
async def get_trace_timeline(trace_id: str):
    """
    获取Timeline数据

    用于前端Timeline组件展示。

    Args:
        trace_id: Trace ID

    Returns:
        Timeline数据
    """
    service = get_trace_service()
    timeline = await service.get_timeline(trace_id)

    if timeline is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    return {
        "trace_id": timeline.trace_id,
        "total_steps": timeline.total_steps,
        "steps_summary": [
            {
                "step_id": s.step_id,
                "thought_preview": s.thought_preview,
                "action_preview": s.action_preview,
                "tool_name": s.tool_name,
                "status": s.status,
                "duration_ms": s.duration_ms,
            }
            for s in timeline.steps_summary
        ],
        "statistics": timeline.statistics,
    }


@router.get("/modes")
async def list_modes():
    """
    列出所有可用的训练模式

    Returns:
        模式列表
    """
    service = get_agent_service()
    modes = service.list_modes()

    mode_infos = []
    for mode_name in modes:
        info = service.get_mode_info(mode_name)
        if info:
            mode_infos.append(info)

    return {"modes": mode_infos}


@router.get("/traces")
async def list_traces(
    user_id: str | None = None,
    mode: str | None = None,
    limit: int = 20,
):
    """
    列出历史Trace

    Args:
        user_id: 用户ID（可选）
        mode: 模式（可选）
        limit: 返回数量

    Returns:
        Trace列表
    """
    service = get_trace_service()
    traces = await service.list_traces(
        user_id=user_id,
        mode=mode,
        limit=limit,
    )

    return {"traces": traces}


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}
