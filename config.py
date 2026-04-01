# ============================================================
# 配置文件
# ============================================================
"""
配置管理。

从环境变量加载配置。
"""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """应用配置"""

    # LLM配置
    openai_api_key: str = ""
    openai_model: str = "gpt-4"
    anthropic_api_key: str = ""

    # 服务配置
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # 执行环境配置
    docker_image: str = "python:3.11-slim"
    docker_timeout: int = 30

    # 日志配置
    log_level: str = "INFO"
    log_trace_dir: str = "./logs/traces"

    # 数据库配置（可选）
    database_url: str = ""


def load_config() -> Config:
    """
    从环境变量加载配置

    Returns:
        Config: 配置对象
    """
    return Config(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("API_PORT", "8000")),
        docker_image=os.getenv("DOCKER_IMAGE", "python:3.11-slim"),
        docker_timeout=int(os.getenv("DOCKER_TIMEOUT", "30")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_trace_dir=os.getenv("LOG_TRACE_DIR", "./logs/traces"),
        database_url=os.getenv("DATABASE_URL", ""),
    )


# 全局配置实例
config = load_config()
