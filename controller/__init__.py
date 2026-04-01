# ============================================================
# controller/ 模块 - API控制器
# ============================================================
"""
API控制器模块。

提供REST API接口。
使用FastAPI实现。
"""

from controller.agent_controller import router

__all__ = ["router"]
