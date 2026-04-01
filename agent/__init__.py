# ============================================================
# agent/ 模块
# ============================================================
"""
Agent核心模块，包含：

- base.py: Agent基类，定义通用接口
- planner.py: Planner - 训练计划制定
- executor.py: Executor - 执行任务
- evaluator.py: Evaluator - 评估结果
- reflector.py: Reflector - 反思与调整
- user_model.py: UserModel - 用户画像管理

推理机制：
- reasoning/ 目录包含 ReAct、Reflexion 等推理实现

训练模式：
- modes/ 目录包含算法、设计、项目等不同训练模式
"""

from agent.base import BaseAgent
from agent.planner import Planner
from agent.executor import Executor
from agent.evaluator import Evaluator
from agent.reflector import Reflector
from agent.user_model import UserModel, UserLevel

# 导出公开接口
__all__ = [
    "BaseAgent",
    "Planner",
    "Executor",
    "Evaluator",
    "Reflector",
    "UserModel",
    "UserLevel",
]
