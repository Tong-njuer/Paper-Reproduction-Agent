# ============================================================
# 主入口文件
# ============================================================
"""
编程教练 Agent 系统

主入口文件。
"""

import uvicorn
from fastapi import FastAPI

from controller.agent_controller import router
from config import config


def create_app() -> FastAPI:
    """
    创建FastAPI应用

    Returns:
        FastAPI: 应用实例
    """
    app = FastAPI(
        title="编程教练 Agent",
        description="多模式编程学习助手",
        version="1.0.0",
    )

    # 注册路由
    app.include_router(router)

    @app.get("/")
    async def root():
        return {
            "name": "编程教练 Agent",
            "version": "1.0.0",
            "description": "多模式编程学习助手",
        }

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.api_host,
        port=config.api_port,
        reload=True,
    )
