# ============================================================
# AlgorithmAgent - 算法训练Agent
# ============================================================
"""
算法训练Agent实现。

继承BaseAgent，实现算法训练的具体逻辑。
"""

from agent.base import BaseAgent, AgentConfig
from agent.planner import AlgorithmPlanner
from agent.executor import Executor
from agent.evaluator import AlgorithmEvaluator
from agent.reflector import ReflexionReflector
from agent.modes.base import TrainingMode
from tools.registry import ToolRegistry
from service.trace_service import TraceService


class AlgorithmAgent(BaseAgent):
    """
    算法训练Agent

    专门用于算法题目练习的Agent。
    """

    def __init__(
        self,
        config: AgentConfig,
        tool_registry: ToolRegistry,
        mode: TrainingMode,
        trace_service: TraceService | None = None,
    ):
        """
        初始化AlgorithmAgent

        Args:
            config: Agent配置
            tool_registry: 工具注册器
            mode: 训练模式
            trace_service: Trace服务
        """
        self.mode = mode
        super().__init__(
            config=config,
            tool_registry=tool_registry,
            trace_service=trace_service,
        )

    def _create_planner(self) -> AlgorithmPlanner:
        """创建Planner"""
        return AlgorithmPlanner()

    def _create_executor(self) -> Executor:
        """创建Executor"""
        return Executor(self.tool_registry)

    def _create_evaluator(self) -> AlgorithmEvaluator:
        """创建Evaluator"""
        return AlgorithmEvaluator()

    def _create_reflector(self) -> ReflexionReflector:
        """创建Reflector"""
        return ReflexionReflector(enable_deep_reflection=True)
