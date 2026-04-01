# ============================================================
# ReAct 推理引擎实现
# ============================================================
"""
ReAct (Reasoning + Acting) 推理模式实现。

ReAct 核心流程：
1. Thought: 分析当前情况，形成思考
2. Action: 选择并执行一个动作
3. Observation: 观察动作结果
4. 循环直到任务完成

设计参考：
- "ReAct: Synergizing Reasoning and Acting in Language Models"
- 适用于需要工具调用的复杂任务
"""

from dataclasses import dataclass
from typing import Any

from agent.reasoning.base import (
    ReasoningContext,
    ReasoningEngine,
    ReasoningResult,
)
from tools.registry import ToolRegistry


class ReActEngine(ReasoningEngine):
    """
    ReAct 推理引擎

    实现经典的 ReAct 推理循环。

    工作流程：
    1. 分析当前状态，理解目标
    2. 决定要执行的工具/动作
    3. 返回动作指令
    4. 等待执行结果后进行下一次推理
    """

    def __init__(self, llm_client: Any = None):
        """
        初始化 ReAct 引擎

        Args:
            llm_client: LLM 客户端（可选，默认使用配置）
        """
        self.llm_client = llm_client
        self._step_count = 0

    @property
    def name(self) -> str:
        return "ReAct"

    @property
    def description(self) -> str:
        return (
            "ReAct: Reasoning + Acting 推理模式。"
            "通过 Thought → Action → Observation 循环进行推理。"
        )

    async def think(self, context: ReasoningContext) -> ReasoningResult:
        """
        执行 ReAct 推理

        根据当前上下文，生成下一个动作的决策。

        Args:
            context: 推理上下文

        Returns:
            ReasoningResult: 推理结果
        """
        self._step_count += 1

        # 1. 分析当前状态
        current_goal = self._get_current_goal(context)
        previous_actions_str = self._summarize_previous(context)

        # 2. 构建推理提示
        prompt = self._build_reasoning_prompt(
            goal=current_goal,
            previous_actions=previous_actions_str,
            available_tools=self._get_available_tools(context),
        )

        # 3. 调用 LLM 进行推理
        # 注意：这里需要接入实际的 LLM
        # 简化实现：使用规则判断
        reasoning_output = await self._invoke_llm(prompt, context)

        # 4. 解析推理结果
        return self._parse_reasoning_output(reasoning_output, context)

    async def reset(self) -> None:
        """重置推理引擎"""
        self._step_count = 0

    # ============================================================
    # 内部方法（可被子类重写）
    # ============================================================

    def _get_current_goal(self, context: ReasoningContext) -> str:
        """获取当前目标"""
        if context.plan and context.plan.steps:
            if context.current_step_index < len(context.plan.steps):
                return context.plan.steps[context.current_step_index]
            return context.plan.goal
        return "完成当前任务"

    def _summarize_previous(self, context: ReasoningContext) -> str:
        """总结之前的动作"""
        if not context.previous_actions:
            return "尚无之前的动作"

        summary = []
        for i, (action, obs) in enumerate(
            zip(context.previous_actions, context.previous_observations)
        ):
            summary.append(f"步骤{i+1}: 动作={action}, 观察={obs}")

        return "\n".join(summary[-3:])  # 只保留最近3步

    def _get_available_tools(self, context: ReasoningContext) -> str:
        """获取可用工具列表"""
        if context.tool_registry is None:
            return "无可用工具"

        tools = context.tool_registry.list_tools()
        tool_descs = [f"- {t}" for t in tools]
        return "\n".join(tool_descs) if tool_descs else "无可用工具"

    def _build_reasoning_prompt(
        self,
        goal: str,
        previous_actions: str,
        available_tools: str,
    ) -> str:
        """
        构建推理提示词

        将当前状态格式化为 LLM 可理解的提示。

        Args:
            goal: 当前目标
            previous_actions: 之前的动作历史
            available_tools: 可用工具

        Returns:
            str: 格式化的提示词
        """
        return f"""
## 当前目标
{goal}

## 之前的动作与观察
{previous_actions}

## 可用工具
{available_tools}

## 推理要求
请分析当前情况，决定下一步动作。
你应该：
1. 思考当前状态和目标
2. 如果可以完成任务，设置 is_finish=true
3. 如果需要继续，选择一个工具并提供参数

输出格式：
- Thought: [你的思考]
- Action: [工具名，如果完成任务则为 None]
- Action Parameters: [参数字典，JSON格式]
- Is Finish: [true/false]
"""

    async def _invoke_llm(
        self,
        prompt: str,
        context: ReasoningContext,
    ) -> str:
        """
        调用 LLM

        这是与 LLM 提供者交互的抽象方法。
        子类或外部应注入具体的 LLM 客户端。

        Args:
            prompt: 提示词
            context: 推理上下文

        Returns:
            str: LLM 输出
        """
        # TODO: 实现 LLM 调用
        # 简化实现：返回空，后续通过规则判断

        # 模拟 LLM 输出
        return f"""
Thought: 分析当前情况...
Action: run_code
Action Parameters: {{"code": "# TODO: 生成的代码"}}
Is Finish: false
"""

    def _parse_reasoning_output(
        self,
        output: str,
        context: ReasoningContext,
    ) -> ReasoningResult:
        """
        解析 LLM 输出

        从 LLM 的文本输出中提取结构化的推理结果。

        Args:
            output: LLM 输出文本
            context: 推理上下文

        Returns:
            ReasoningResult: 解析后的结果
        """
        # TODO: 实现解析逻辑
        # 简化实现：基于规则判断

        # 检查是否应该结束
        is_finish = "is finish: true" in output.lower()

        # 提取动作
        action = None
        action_params = {}

        if "action:" in output.lower():
            for line in output.split("\n"):
                line_lower = line.lower()
                if line_lower.startswith("action:"):
                    action = line.split(":", 1)[1].strip()
                elif "action parameters:" in line_lower:
                    # 简化：跳过参数解析
                    pass

        return ReasoningResult(
            thought=output,
            action=action,
            action_params=action_params,
            is_finish=is_finish,
            reasoning_steps=self._step_count,
        )
