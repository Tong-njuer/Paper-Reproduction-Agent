# ============================================================
# Core Package
# ============================================================
# Contains fundamental infrastructure:
#   - config: Configuration management
#   - llm: LLM interface (Zhipu GLM)
#   - context: Context management for agent
# ============================================================

from app.core.config import Config
from app.core.llm import LLMInterface

__all__ = ["Config", "LLMInterface"]
