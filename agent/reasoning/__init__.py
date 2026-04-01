# ============================================================
# reasoning/ 模块
# ============================================================
"""
推理机制实现模块。

包含：
- base.py: 推理引擎基类
- react.py: ReAct推理实现
- reflexion.py: Reflexion推理实现
- registry.py: 推理机制注册器

支持的推理模式：
1. ReAct (Reasoning + Acting)
   - Thought → Action → Observation 循环

2. Reflexion (基于自我反思的改进)
   - 执行 → 评估 → 反思 → 调整 循环

3. (可选扩展) Plan-and-Execute
4. (可选扩展) Tree-of-Thought
"""

from agent.reasoning.base import ReasoningEngine, ReasoningResult
from agent.reasoning.registry import ReasoningRegistry

__all__ = [
    "ReasoningEngine",
    "ReasoningResult",
    "ReasoningRegistry",
]
