"""Core Package — 核心基础设施。

包含：
  - config: 配置管理
  - llm: LLM 接口（智谱 GLM / DeepSeek）
  - logging: 日志工具
"""

from app.core.config import Config
from app.core.llm import LLMInterface


__all__ = [
    "Config",
    "LLMInterface",
]

__all__ = ["Config", "LLMInterface"]
