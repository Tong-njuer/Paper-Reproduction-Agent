# ============================================================
# Agent 基类 - BaseAgent
# ============================================================
"""
定义所有Agent的基类接口。

设计思路：
- 所有具体的Agent（AlgorithmAgent、DesignAgent等）都应继承此基类
- 基类定义核心方法：plan, execute, evaluate, reflect
- 具体的推理逻辑通过组合 ReasoningEngine 实现
- 支持插件式的工具系统和模式切换

职责：
- 定义Agent的通用接口
- 规范Agent与外部组件的交互方式
- 提供默认实现（可被子类覆盖）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

from dto.trace import Trace, Step
from dto.response import AgentResponse
from tools.registry import ToolRegistry


class AgentStatus(Enum):
    """Agent运行状态枚举"""
    IDLE = "idle"              # 空闲状态
    PLANNING = "planning"      # 制定计划中
    EXECUTING = "executing"   # 执行任务中
    EVALUATING = "evaluating" # 评估结果中
    REFLECTING = "reflecting" # 反思中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"          # 失败


@dataclass
class AgentConfig:
    """
    Agent配置类

    包含Agent运行所需的各种配置参数。
    设计为dataclass便于序列化存储和修改。
    """
    # Agent名称
    name: str = "ProgrammingCoach"
    # Agent描述
    description: str = "多模式编程教练Agent"

    # 推理相关配置
    max_iterations: int = 10           # 最大迭代次数，防止无限循环
    max_steps_per_iteration: int = 5  # 每次迭代的最大步数
    timeout_seconds: int = 300        # 超时时间

    # 反思配置
    enable_reflection: bool = True    # 是否启用反思机制
    reflection_threshold: int = 3     # 连续失败N次后触发深度反思

    # 工具配置
    tool_timeout: int = 60             # 工具执行超时（秒）

    def __post_init__(self):
        """配置验证"""
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


# 类型变量，用于泛型约束
T = TypeVar("T")


class BaseAgent(ABC, Generic[T]):
    """
    Agent基类

    定义所有编程教练Agent的通用接口和基本功能。
    子类需要实现特定的方法来定制行为。

    设计原则：
    1. 组合优于继承：具体的推理逻辑通过注入的 ReasoningEngine 实现
    2. 模板方法模式：run() 方法定义了通用的执行模板
    3. 钩子方法：提供扩展点供子类定制

    使用示例：
    ```python
    class AlgorithmAgent(BaseAgent):
        def _create_planner(self) -> Planner:
            return AlgorithmPlanner()

        def _create_mode_strategy(self) -> ModeStrategy:
            return AlgorithmModeStrategy()
    ```
    """

    def __init__(
        self,
        config: AgentConfig,
        tool_registry: ToolRegistry,
        # 下面是可以注入的组件，支持自定义
        reasoning_engine=None,
        trace_service=None,
    ):
        """
        初始化Agent

        Args:
            config: Agent配置
            tool_registry: 工具注册器
            reasoning_engine: 推理引擎（可选，默认ReAct）
            trace_service: Trace服务（可选）
        """
        self.config = config
        self.tool_registry = tool_registry
        self.reasoning_engine = reasoning_engine
        self.trace_service = trace_service

        # 运行时状态
        self._status: AgentStatus = AgentStatus.IDLE
        self._current_trace: Trace | None = None
        self._iteration_count: int = 0

        # 初始化组件（由子类定制）
        self._planner = self._create_planner()
        self._executor = self._create_executor()
        self._evaluator = self._create_evaluator()
        self._reflector = self._create_reflector()

    # ============================================================
    # 抽象方法 - 子类必须实现
    # ============================================================

    @abstractmethod
    def _create_planner(self) -> "Planner":
        """创建Planner组件 - 子类实现"""
        pass

    @abstractmethod
    def _create_executor(self) -> "Executor":
        """创建Executor组件 - 子类实现"""
        pass

    @abstractmethod
    def _create_evaluator(self) -> "Evaluator":
        """创建Evaluator组件 - 子类实现"""
        pass

    @abstractmethod
    def _create_reflector(self) -> "Reflector":
        """创建Reflector组件 - 子类实现"""
        pass

    # ============================================================
    # 模板方法 - 核心执行流程
    # ============================================================

    async def run(self, task: str, context: dict[str, Any] | None = None) -> AgentResponse:
        """
        Agent运行的主入口方法（模板方法）

        定义了Agent执行的标准流程：
        1. 初始化 - 设置状态，创建Trace
        2. 计划 - 制定执行计划
        3. 执行循环 - 反复执行直到完成或超时
           3.1 执行一步
           3.2 评估结果
           3.3 反思（如果需要）
        4. 返回结果

        这个方法是线程安全的，支持并发调用。

        Args:
            task: 任务描述
            context: 额外的上下文信息（如用户ID、会话ID等）

        Returns:
            AgentResponse: 包含执行结果和Trace
        """
        context = context or {}
        self._status = AgentStatus.PLANNING
        self._iteration_count = 0

        # Step 1: 初始化Trace记录
        self._current_trace = self._init_trace(task, context)

        try:
            # Step 2: 制定计划
            plan = await self._planner.create_plan(task, context)

            # Step 3: 执行循环
            while self._iteration_count < self.config.max_iterations:
                self._iteration_count += 1
                self._status = AgentStatus.EXECUTING

                # 3.1 执行当前步骤
                step_result = await self._execute_step(plan, context)

                if step_result.is_complete:
                    # 成功完成
                    break

                # 3.2 评估结果
                self._status = AgentStatus.EVALUATING
                evaluation = await self._evaluator.evaluate(
                    step_result, plan, context
                )

                if evaluation.is_satisfactory:
                    # 评估通过，可选反思后结束
                    if self.config.enable_reflection:
                        await self._reflect()
                    break

                # 3.3 检查是否需要重新计划
                if evaluation.need_replan:
                    # 重新制定计划
                    plan = await self._planner.adjust_plan(
                        plan, evaluation.feedback, context
                    )

                # 3.4 反思（如果启用且遇到失败）
                if step_result.is_failed and self.config.enable_reflection:
                    await self._reflect()

            # 最终评估
            self._status = AgentStatus.EVALUATING
            final_result = await self._evaluator.final_evaluate(
                plan, context
            )

            # 标记完成
            self._status = (
                AgentStatus.COMPLETED
                if final_result.is_satisfactory
                else AgentStatus.FAILED
            )

            return AgentResponse(
                success=final_result.is_satisfactory,
                output=final_result.output,
                trace=self._current_trace,
                metadata={
                    "iterations": self._iteration_count,
                    "final_status": self._status.value,
                },
            )

        except Exception as e:
            self._status = AgentStatus.FAILED
            return AgentResponse(
                success=False,
                output="",
                trace=self._current_trace,
                error=str(e),
            )

    async def _execute_step(
        self, plan: "Plan", context: dict[str, Any]
    ) -> "StepResult":
        """
        执行单个步骤

        由Executor实际执行具体的代码/工具调用。
        这个方法将推理引擎和执行器结合起来。

        Args:
            plan: 当前计划
            context: 执行上下文

        Returns:
            StepResult: 步骤执行结果
        """
        # 使用推理引擎进行思考和决策
        reasoning_result = await self.reasoning_engine.think(
            plan=plan,
            context=context,
            tool_registry=self.tool_registry,
        )

        # 记录推理步骤到Trace
        step = self._create_step(reasoning_result)
        self._current_trace.add_step(step)

        # 执行工具（如果有）
        if reasoning_result.action:
            result = await self._executor.execute(
                action=reasoning_result.action,
                params=reasoning_result.action_params,
            )
        else:
            result = None

        # 更新步骤结果
        step.complete(result)
        return StepResult(
            is_complete=reasoning_result.is_finish,
            is_failed=result is not None and not result.success,
            step=step,
            result=result,
        )

    async def _reflect(self) -> None:
        """
        触发反思机制

        由Reflector分析最近的执行历史，
        总结经验教训，可能调整后续策略。
        """
        self._status = AgentStatus.REFLECTING

        if self._current_trace and len(self._current_trace.steps) > 0:
            reflection = await self._reflector.reflect(
                self._current_trace.recent_steps(5)
            )
            # 将反思结果添加到最后一个步骤
            last_step = self._current_trace.steps[-1]
            last_step.add_reflection(reflection)

    # ============================================================
    # 辅助方法
    # ============================================================

    def _init_trace(self, task: str, context: dict[str, Any]) -> Trace:
        """
        初始化Trace记录

        用于记录整个Agent执行过程，便于：
        - 可视化展示
        - 评估分析
        - 问题排查

        Args:
            task: 任务描述
            context: 上下文信息

        Returns:
            初始化的Trace对象
        """
        return Trace(
            trace_id=self._generate_id(),
            session_id=context.get("session_id", "default"),
            user_id=context.get("user_id", "anonymous"),
            mode=context.get("mode", "algorithm"),
            task_description=task,
            user_level=context.get("user_level", UserLevel.BEGINNER),
            steps=[],
            started_at=self._get_current_time(),
        )

    def _create_step(self, reasoning: "ReasoningResult") -> Step:
        """创建Step对象"""
        return Step(
            step_id=self._generate_id(),
            trace_id=self._current_trace.trace_id if self._current_trace else "",
            thought=reasoning.thought,
            action=reasoning.action,
            action_input=reasoning.action_params or {},
            created_at=self._get_current_time(),
        )

    @staticmethod
    def _generate_id() -> str:
        """生成唯一ID（简化实现）"""
        import uuid
        return str(uuid.uuid4())[:8]

    @staticmethod
    def _get_current_time():
        """获取当前时间"""
        from datetime import datetime
        return datetime.now()

    # ============================================================
    # 属性
    # ============================================================

    @property
    def status(self) -> AgentStatus:
        """获取Agent当前状态"""
        return self._status

    @property
    def current_trace(self) -> Trace | None:
        """获取当前Trace"""
        return self._current_trace


# ============================================================
# 辅助数据类型
# ============================================================

@dataclass
class Plan:
    """
    执行计划

    包含一个任务的分解步骤和元信息。
    由Planner生成，Executor执行。
    """
    task: str                           # 原始任务
    goal: str                           # 最终目标
    steps: list[str]                    # 分解的步骤列表
    current_step_index: int = 0         # 当前步骤索引
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_complete(self) -> bool:
        """检查计划是否完成"""
        return self.current_step_index >= len(self.steps)

    def next_step(self) -> str | None:
        """获取下一步"""
        if self.is_complete():
            return None
        step = self.steps[self.current_step_index]
        self.current_step_index += 1
        return step


@dataclass
class StepResult:
    """
    步骤执行结果

    包含单个步骤的执行结果信息。
    """
    is_complete: bool                  # 是否完成整个任务
    is_failed: bool                     # 当前步骤是否失败
    step: Step                          # 关联的Step对象
    result: Any                        # 工具执行结果（ToolResult或None）


@dataclass
class ReasoningResult:
    """
    推理结果

    包含推理引擎的思考和决策结果。
    """
    thought: str                       # 思考内容
    action: str | None                  # 要执行的动作（工具名）
    action_params: dict[str, Any] | None # 动作参数
    is_finish: bool = False            # 是否应该结束


@dataclass
class EvaluationResult:
    """
    评估结果

    包含评估的结论和建议。
    """
    is_satisfactory: bool              # 是否满足要求
    need_replan: bool                  # 是否需要重新计划
    feedback: str                       # 评估反馈
    score: float | None = None         # 评分（可选）
    output: str | None = None           # 最终输出（如果评估通过）
