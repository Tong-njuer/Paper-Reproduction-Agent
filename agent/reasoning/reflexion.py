# ============================================================
# Reflexion 推理引擎实现
# ============================================================
"""
Reflexion 推理模式实现。

Reflexion 核心思想：
- 从失败中学习，通过自我反思改进策略
- 维护执行历史和反思记忆
- 基于历史经验调整决策

设计参考：
- "Reflexion: Language Agents with Verbal Reinforcement Learning"
- 适用于需要从错误中学习的复杂任务
"""

from dataclasses import dataclass, field
from typing import Any

from agent.reasoning.base import (
    ReasoningContext,
    ReasoningEngine,
    ReasoningResult,
)


@dataclass
class ReflexionMemory:
    """
    Reflexion 记忆

    存储历史执行信息和反思记录。
    """
    # 执行历史
    executions: list["ExecutionTrace"] = field(default_factory=list)

    # 反思历史
    reflections: list["ReflectionRecord"] = field(default_factory=list)

    # 学习的教训
    learned_lessons: list[str] = field(default_factory=list)

    # 避免的策略
    strategies_to_avoid: list[str] = field(default_factory=list)


@dataclass
class ExecutionTrace:
    """执行追踪记录"""
    task: str                           # 任务描述
    actions: list[str]                 # 执行的动作序列
    result: str                         # 执行结果
    success: bool                      # 是否成功
    timestamp: Any = None              # 时间戳


@dataclass
class ReflectionRecord:
    """反思记录"""
    situation: str                     # 情境描述
    reflection: str                    # 反思内容
    adjustment: str                    # 策略调整
    outcome: str | None               # 调整后的结果


class ReflexionEngine(ReasoningEngine):
    """
    Reflexion 推理引擎

    在 ReAct 基础上增加反思机制：
    1. 执行动作后，如果失败则触发反思
    2. 从反思中学习，调整后续策略
    3. 维护记忆，避免重复错误
    """

    def __init__(self, llm_client: Any = None):
        """
        初始化 Reflexion 引擎

        Args:
            llm_client: LLM 客户端
        """
        self.llm_client = llm_client
        self._memory = ReflexionMemory()
        self._step_count = 0
        self._consecutive_failures = 0

    @property
    def name(self) -> str:
        return "Reflexion"

    @property
    def description(self) -> str:
        return (
            "Reflexion: 基于自我反思的推理模式。"
            "从失败中学习，避免重复错误。"
        )

    async def think(self, context: ReasoningContext) -> ReasoningResult:
        """
        执行 Reflexion 推理

        在 ReAct 基础上，检查失败历史，调整策略。

        Args:
            context: 推理上下文

        Returns:
            ReasoningResult: 推理结果
        """
        self._step_count += 1

        # 1. 检查是否需要反思
        should_reflect = self._consecutive_failures >= 2

        if should_reflect:
            # 触发反思
            await self._perform_reflection(context)

        # 2. 考虑历史教训
        adjusted_context = await self._apply_lessons(context)

        # 3. 执行标准 ReAct 推理
        # 这里复用 ReAct 的逻辑
        react_result = await self._react_think(adjusted_context)

        # 4. 更新失败计数
        if not react_result.is_finish and react_result.action:
            # 如果动作执行后失败，会在下一轮更新
            pass

        return react_result

    async def _perform_reflection(self, context: ReasoningContext) -> None:
        """
        执行反思

        分析最近的失败，总结教训，调整策略。
        """
        # 构建反思情境
        situation = self._build_situation(context)

        # 调用 LLM 生成反思
        reflection_text = await self._generate_reflection(situation)

        # 解析反思内容
        adjustment = await self._extract_adjustment(reflection_text)

        # 更新记忆
        record = ReflectionRecord(
            situation=situation,
            reflection=reflection_text,
            adjustment=adjustment,
        )
        self._memory.reflections.append(record)

        # 如果有策略调整，更新避免列表
        if adjustment:
            self._memory.strategies_to_avoid.append(adjustment)

    def _build_situation(self, context: ReasoningContext) -> str:
        """构建反思情境描述"""
        recent_actions = context.previous_actions[-5:] if context.previous_actions else []
        recent_obs = context.previous_observations[-5:] if context.previous_observations else []

        return f"""
任务: {context.plan.goal if context.plan else '未知'}
最近动作: {recent_actions}
最近观察: {recent_obs}
连续失败次数: {self._consecutive_failures}
历史教训: {self._memory.learned_lessons[-3:]}
"""

    async def _generate_reflection(self, situation: str) -> str:
        """
        生成反思内容

        调用 LLM 分析失败原因，生成反思。

        Args:
            situation: 情境描述

        Returns:
            str: 反思内容
        """
        # TODO: 实现 LLM 调用
        prompt = f"""
## 情境
{situation}

## 反思要求
请分析上述情境中的问题：
1. 失败的根本原因是什么？
2. 下次应该如何避免？
3. 有什么具体的策略调整？

请用简洁的语言回答。
"""
        # 简化实现
        return "反思：需要调整解题思路，避免重复相同的错误方法。"

    async def _extract_adjustment(self, reflection: str) -> str:
        """从反思中提取策略调整"""
        # TODO: 解析反思文本，提取具体调整
        return ""

    async def _apply_lessons(
        self, context: ReasoningContext
    ) -> ReasoningContext:
        """
        应用历史教训

        修改上下文，避开已知的失败策略。

        Args:
            context: 原始上下文

        Returns:
            ReasoningContext: 调整后的上下文
        """
        # 添加教训到上下文
        if self._memory.learned_lessons:
            context.metadata["learned_lessons"] = self._memory.learned_lessons[-3:]

        return context

    async def _react_think(
        self, context: ReasoningContext
    ) -> ReasoningResult:
        """
        核心 ReAct 推理

        这是一个简化的实现，
        实际应该复用或继承 ReActEngine。
        """
        # TODO: 复用 ReActEngine 的逻辑
        return ReasoningResult(
            thought="思考中...",
            action="run_code",
            action_params={"code": "# TODO"},
            is_finish=False,
            reasoning_steps=self._step_count,
        )

    def record_execution(
        self,
        task: str,
        actions: list[str],
        result: str,
        success: bool,
    ) -> None:
        """
        记录执行结果

        在动作执行完成后调用，用于更新记忆。

        Args:
            task: 任务描述
            actions: 动作序列
            result: 执行结果
            success: 是否成功
        """
        trace = ExecutionTrace(
            task=task,
            actions=actions,
            result=result,
            success=success,
        )
        self._memory.executions.append(trace)

        if success:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

    def add_lesson(self, lesson: str) -> None:
        """
        添加学到的教训

        Args:
            lesson: 教训内容
        """
        if lesson not in self._memory.learned_lessons:
            self._memory.learned_lessons.append(lesson)

    async def reset(self) -> None:
        """重置推理引擎"""
        self._step_count = 0
        self._consecutive_failures = 0
        # 注意：记忆通常保留，只重置运行时状态

    @property
    def memory(self) -> ReflexionMemory:
        """获取记忆"""
        return self._memory
