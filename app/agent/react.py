# ============================================================
# ReAct 引擎模块
# ============================================================
# 实现 Thought -> Action -> Observation 循环。
# 基于当前计划和上下文进行步级决策。
#
# 核心循环: Thought -> Action -> Observation -> Thought -> ...
#
# Console Output:
#   - Current thought process
#   - Action decisions
#   - Observation results
# ============================================================

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from app.core.llm import get_llm
from app.core.context import ExecutionContext, StepContext
from app.agent.planner import Plan, PlanStep
from app.tools import get_tool, TOOL_REGISTRY


class ReActStep(BaseModel):
    """
    ReAct 循环中的单步。

    Attributes:
        thought: 此步骤的 Agent 推理
        action: 要执行的操作（工具名称）
        action_args: 操作参数
        observation: 操作结果
        reasoning: 额外的推理链
    """
    thought: str
    action: str
    action_args: Dict[str, Any] = Field(default_factory=dict)
    observation: str = ""
    reasoning: str = ""


class ReActEngine:
    """
    ReAct（推理+行动）引擎。

    实现核心决策循环:
    1. 思考当前情况
    2. 决定行动
    3. 执行并观察
    4. 从观察中学习

    Attributes:
        llm: 用于推理的 LLM 接口
        max_retries: 失败行动的最大重试次数
    """

    def __init__(self, max_retries: int = 3):
        """
        Initialize the ReAct Engine.

        Args:
            max_retries: Maximum retry attempts for failed actions
        """
        self.llm = get_llm()
        self.max_retries = max_retries
        print("[RETRY] ReAct Engine initialized")

    def decide_action(
        self,
        plan: Plan,
        context: ExecutionContext,
    ) -> ReActStep:
        """
        决定下一步要采取的行动。

        Args:
            plan: Current plan
            context: Execution context

        Returns:
            ReActStep: The decided action with thought process
        """
        # Get current step from plan
        current_step = plan.get_next_step()

        if not current_step:
            # No more steps - idle
            return ReActStep(
                thought="No more steps in plan",
                action="idle",
                action_args={},
            )

        print(f"\n[BRAIN] ReAct: Deciding action for step {current_step.step_id}")
        print(f"   Description: {current_step.description}")

        # Build decision prompt
        prompt = self._build_decision_prompt(current_step, plan, context)

        if self.llm.is_available():
            try:
                response = self.llm.generate_structured(prompt)
                react_step = self._parse_decision(response, current_step)
            except Exception as e:
                print(f"[!]  LLM decision failed: {e}")
                react_step = self._create_fallback_decision(current_step)
        else:
            react_step = self._create_demo_decision(current_step)

        # Print decision
        print(f"\n[THINK] Thought: {react_step.thought}")
        print(f"   Action: {react_step.action}")
        if react_step.action_args:
            print(f"   Args: {react_step.action_args}")

        return react_step

    def execute_action(self, react_step: ReActStep) -> str:
        """
        执行决定的行动。

        Args:
            react_step: The action to execute

        Returns:
            str: Observation (result) from execution
        """
        action_name = react_step.action

        # Handle special actions
        if action_name == "idle":
            return "No action needed - plan complete"
        elif action_name == "finish":
            return "Task completed successfully"

        # Get tool from registry
        tool = get_tool(action_name)

        if tool is None:
            error_msg = f"Unknown action/tool: {action_name}"
            print(f"[X] {error_msg}")
            print(f"   Available tools: {list(TOOL_REGISTRY.keys())}")
            return f"ERROR: {error_msg}"

        # Execute tool
        print(f"\n[EXEC]  Executing: {action_name}")
        print(f"   Args: {react_step.action_args}")

        try:
            result = tool.execute(**react_step.action_args)

            if result.success:
                print(f"[OK] Action completed")
                print(f"   Output: {result.output[:200] if result.output else 'None'}...")
                return result.output or "Action completed successfully"
            else:
                print(f"[X] Action failed")
                print(f"   Error: {result.error}")
                return f"ERROR: {result.error}"

        except Exception as e:
            error_msg = f"Action execution exception: {str(e)}"
            print(f"[X] {error_msg}")
            return f"ERROR: {error_msg}"

    def process_observation(
        self,
        observation: str,
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """
        处理行动的观察结果。

        Args:
            observation: The observation string
            context: Current execution context

        Returns:
            Dict with analysis results:
                - success: bool
                - needs_reflexion: bool
                - needs_replan: bool
                - analysis: str
        """
        is_error = observation.startswith("ERROR")
        is_success = "completed successfully" in observation.lower() or not is_error

        print(f"\n[STAT] Observation Analysis:")
        print(f"   Success: {is_success}")
        print(f"   Error: {is_error}")

        result = {
            "success": is_success and not is_error,
            "needs_reflexion": is_error,
            "needs_replan": is_error,
            "analysis": observation[:100],
        }

        return result

    def _build_decision_prompt(
        self,
        current_step: PlanStep,
        plan: Plan,
        context: ExecutionContext,
    ) -> str:
        """
        Build the prompt for action decision.

        Args:
            current_step: The step to decide action for
            plan: Current plan
            context: Execution context

        Returns:
            str: Formatted prompt
        """
        # Get recent history
        recent_steps = context.steps[-3:] if context.steps else []
        history_text = "\n".join(
            f"- Step {s.step_id}: {s.action} -> {s.observation[:50]}"
            for s in recent_steps
        ) if recent_steps else "No previous steps"

        # Available tools
        available_tools = ", ".join(TOOL_REGISTRY.keys())
        tool_guide = self._build_tool_usage_guide()

        prompt = f"""You are a reasoning agent in a ReAct loop. Given the current situation, decide the next action.

Current Plan Step:
- Step ID: {current_step.step_id}
- Description: {current_step.description}
- Status: {current_step.status}

Recent History:
{history_text if history_text else "No history yet"}

Available Tools:
{available_tools}

Tool Usage Guide (action-specific argument templates):
{tool_guide}

Your task is to decide WHAT action to take (not how to implement it).
Choose the most appropriate tool and arguments to advance the plan.

Hard constraints:
1. "action" MUST be one of the available tools above.
2. "action_args" MUST be a JSON object.
3. If a tool needs an "action" field (e.g., paper_tool/source_tool/repo_index_tool/sandbox_tool/test_tool/doc_tool/schedule_tool), include it explicitly.
4. Prefer minimal required args first, avoid fabricated paths.

Output format (JSON):
{{
    "thought": "Explain your reasoning",
    "action": "tool_name",
    "action_args": {{"arg1": "value1", ...}}
}}

Choose action that will help complete the current step description."""
        return prompt

    def _build_tool_usage_guide(self) -> str:
        """构建工具参数模板，帮助 LLM 输出稳定可执行的 action_args。"""
        return """- paper_tool: {\"action\": \"extract\", \"text\": \"...\"} | {\"action\": \"extract_from_pdf\", \"pdf_path\": \"...\"}
- source_tool: {\"action\": \"discover_candidates\", \"text\": \"...\"} | {\"action\": \"analyze_source\", \"source_path\": \"...\"}
- repo_index_tool: {\"action\": \"summarize_repo\", \"root_path\": \"...\"} | {\"action\": \"search_text\", \"root_path\": \"...\", \"query\": \"...\"}
- sandbox_tool: {\"action\": \"create_workspace\", \"user_id\": \"user_1\"} | {\"action\": \"detect_environment\", \"project_path\": \"...\"}
- test_tool: {\"action\": \"run_unit_tests\", \"project_path\": \"...\"} | {\"action\": \"compare_metrics\", \"expected\": {...}, \"actual\": {...}}
- doc_tool: {\"action\": \"generate_repro_report\", \"output_path\": \"...\", \"goal\": \"...\"}
- schedule_tool: {\"action\": \"create_plan\", \"goal\": \"...\", \"tasks\": [\"...\"]}
- code_tool: {\"command\": \"python --version\", \"timeout\": 30}
- wiki_tool: {\"query\": \"transformer\", \"lang\": \"en\"}
- learning_path_tool: {\"topic\": \"paper reproduction\", \"level\": \"beginner\", \"weeks\": 4}"""

    def _parse_decision(
        self,
        response: Dict[str, Any],
        current_step: PlanStep,
    ) -> ReActStep:
        """
        Parse LLM decision response.

        Args:
            response: LLM JSON response
            current_step: The current plan step

        Returns:
            ReActStep: Parsed decision
        """
        action = str(response.get("action", "idle"))
        action_args = response.get("action_args", {})

        if action not in TOOL_REGISTRY and action != "idle":
            action = "idle"

        if not isinstance(action_args, dict):
            action_args = {}

        return ReActStep(
            thought=str(response.get("thought", "No thought provided")),
            action=action,
            action_args=action_args,
        )

    def _create_fallback_decision(self, current_step: PlanStep) -> ReActStep:
        """
        Create fallback decision when LLM unavailable.

        Args:
            current_step: Current plan step

        Returns:
            ReActStep: Simple fallback decision
        """
        return ReActStep(
            thought=f"Executing step: {current_step.description}",
            action="code_tool",
            action_args={"command": f"echo 'Executing: {current_step.description}'"},
        )

    def _create_demo_decision(self, current_step: PlanStep) -> ReActStep:
        """
        Create demo decision for demonstration mode.

        Args:
            current_step: Current plan step

        Returns:
            ReActStep: Demo decision
        """
        return ReActStep(
            thought=f"[DEMO] Would execute: {current_step.description}",
            action="idle",
            action_args={},
        )
