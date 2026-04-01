# ============================================================
# AgentService - Agent服务
# ============================================================
"""
Agent服务主入口。

协调各组件，提供统一的Agent执行接口。
"""

from typing import Any

from agent.base import BaseAgent, AgentConfig
from agent.modes import ModeRegistry, TrainingMode
from agent.reasoning import ReasoningRegistry
from tools.registry import ToolRegistry, get_global_registry

from dto.request import AgentRequest
from dto.response import AgentResponse
from service.trace_service import TraceService


class AgentService:
    """
    Agent服务

    整合所有Agent组件，提供简单的执行接口。
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        trace_service: TraceService | None = None,
    ):
        """
        初始化Agent服务

        Args:
            tool_registry: 工具注册器
            trace_service: Trace服务
        """
        self.tool_registry = tool_registry or get_global_registry()
        self.trace_service = trace_service or TraceService()

        # 初始化模式注册表
        self._mode_registry = ModeRegistry()
        self._register_modes()

        # 初始化推理注册表
        self._reasoning_registry = ReasoningRegistry()
        self._register_reasoning()

    def _register_modes(self) -> None:
        """注册所有训练模式"""
        from agent.modes.algorithm_mode import AlgorithmMode
        from agent.modes.design_mode import DesignMode
        from agent.modes.project_mode import ProjectMode
        from agent.modes.refactor_mode import RefactorMode
        from agent.modes.learning_path_mode import LearningPathMode

        self._mode_registry.register(AlgorithmMode())
        self._mode_registry.register(DesignMode())
        self._mode_registry.register(ProjectMode())
        self._mode_registry.register(RefactorMode())
        self._mode_registry.register(LearningPathMode())

    def _register_reasoning(self) -> None:
        """注册推理引擎"""
        self._reasoning_registry.create_engine("react")
        self._reasoning_registry.create_engine("reflexion")

    async def run_agent(
        self,
        request: AgentRequest,
    ) -> AgentResponse:
        """
        运行Agent

        主入口方法：
        1. 获取对应的模式
        2. 创建Agent实例
        3. 执行任务
        4. 返回结果

        Args:
            request: Agent请求

        Returns:
            AgentResponse: Agent响应
        """
        # 1. 获取模式
        mode = self._mode_registry.get(request.mode)
        if mode is None:
            return AgentResponse(
                success=False,
                output="",
                error=f"Unknown mode: {request.mode}",
            )

        # 2. 创建Agent配置
        config = AgentConfig(
            name=f"CoachAgent-{mode.config.mode_name}",
            description=mode.config.description,
            max_iterations=mode.config.max_iterations,
            timeout_seconds=mode.config.timeout_seconds,
        )

        # 3. 创建Agent实例（这里需要根据模式创建具体的Agent）
        # 简化实现：使用通用的BaseAgent
        agent = await self._create_agent(config, mode)

        # 4. 执行
        try:
            response = await agent.run(
                task=request.task,
                context=request.to_context(),
            )

            # 5. 记录Trace
            if response.trace:
                await self.trace_service.save_trace(response.trace)

            return response

        except Exception as e:
            return AgentResponse(
                success=False,
                output="",
                error=f"Agent execution error: {str(e)}",
            )

    async def _create_agent(
        self,
        config: AgentConfig,
        mode: TrainingMode,
    ) -> BaseAgent:
        """
        创建Agent实例

        根据模式和配置创建合适的Agent。
        这里使用组合模式，简化实现。

        Args:
            config: Agent配置
            mode: 训练模式

        Returns:
            BaseAgent: Agent实例
        """
        # 导入具体的Agent实现
        from agent.algorithm_agent import AlgorithmAgent

        if mode.config.mode_name == "algorithm":
            return AlgorithmAgent(
                config=config,
                tool_registry=self.tool_registry,
                mode=mode,
                trace_service=self.trace_service,
            )

        # 其他模式暂用通用实现
        # TODO: 实现其他模式的Agent
        return AlgorithmAgent(
            config=config,
            tool_registry=self.tool_registry,
            mode=mode,
            trace_service=self.trace_service,
        )

    def list_modes(self) -> list[str]:
        """列出所有可用模式"""
        return self._mode_registry.list_modes()

    def get_mode_info(self, mode_name: str) -> dict[str, Any] | None:
        """获取模式信息"""
        info = self._mode_registry.get_mode_info(mode_name)
        return info.to_dict() if info else None
