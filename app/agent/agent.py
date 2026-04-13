# ============================================================
# 主 Agent 编排模块
# ============================================================
# 将所有 Agent 组件编排成一个内聚系统。
# 实现主执行循环。
#
# 架构:
#   目标 -> 规划器 -> ReAct 循环 -> 观察 -> 反思 -> 记忆
#
# Console Output:
#   - Comprehensive execution trace
#   - State transitions
#   - Module interactions
# ============================================================

from typing import Dict, Any, Optional
from datetime import datetime

# Import agent components
from app.agent.planner import Planner, Plan
from app.agent.react import ReActEngine, ReActStep
from app.agent.reflexion import Reflexion, ReflectionResult
from app.agent.memory import Memory, get_memory
from app.agent.state import StateManager, AgentState

# Import core modules
from app.core.config import Config, get_config
from app.core.context import ExecutionContext, create_context, get_context
from app.core.llm import get_llm


class Agent:
    """
    主 Agent 编排器。

    协调所有模块自主执行任务:
    - Planner: 目标分解
    - ReAct: 行动决策和执行
    - Reflexion: 错误自我反思
    - Memory: 经验存储和检索
    - State: 状态管理和转换

    Attributes:
        config: Agent 配置
        planner: 规划模块
        react: ReAct 引擎
        reflexion: 反思模块
        memory: 记忆系统
        state: 状态管理器
        context: 执行上下文
    """

    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the Agent.

        Args:
            config: Optional configuration object. Loads from env if None.
        """
        # Load configuration
        self.config = config or get_config()

        print("\n" + "=" * 60)
        print("[AGENT] Agent Initialization")
        print("=" * 60)

        # Initialize core LLM first
        self.llm = get_llm()

        # Initialize agent components
        print("\n[PKG] Initializing components...")

        self.planner = Planner()
        self.react = ReActEngine(max_retries=self.config.agent.max_retries)
        self.reflexion = Reflexion(enabled=self.config.agent.enable_reflexion)
        self.memory = get_memory(
            enabled=self.config.agent.enable_memory,
            memory_dir=self.config.memory.memory_dir,
        )
        self.state = StateManager()

        self.context: Optional[ExecutionContext] = None

        print("\n[OK] Agent initialized successfully")
        self._print_startup_banner()

    def _print_startup_banner(self) -> None:
        """Print startup banner with agent info."""
        print("\n" + "=" * 60)
        print("[RUN] Autonomous Agent Core v1.0.0")
        print("=" * 60)
        print("\n[INFO] Capabilities:")
        print("   [+] Goal decomposition and planning")
        print("   [+] ReAct-style reasoning and action")
        print("   [+] Self-reflection on errors")
        print("   [+] Memory (short-term + long-term)")
        print("   [+] Dynamic replanning")

        print("\n[FIX] Configuration:")
        print(f"   Max Steps:     {self.config.agent.max_steps}")
        print(f"   Max Retries:   {self.config.agent.max_retries}")
        print(f"   Replan After:  {self.config.agent.replan_threshold} failures")
        print(f"   LLM Model:     {self.config.llm.model}")
        print(f"   LLM Available:  {'Yes' if self.llm.is_available() else 'No (Demo Mode)'}")

        print("\n" + "=" * 60 + "\n")

    def run(self, goal: str) -> ExecutionContext:
        """
        运行 Agent 完成给定目标。

        Args:
            goal: 要完成的目标

        Returns:
            ExecutionContext: 最终执行上下文（包含历史）
        """
        print("\n" + "=" * 60)
        print(f"[GOAL] AGENT STARTING: {goal[:80]}...")
        print("=" * 60 + "\n")

        # Create execution context
        self.context = create_context(goal)
        self.state.reset()

        # Generate initial plan
        self.state.transition_to(AgentState.PLANNING, "Starting goal decomposition")
        plan = self.planner.create_plan(goal, self.context)
        self.context.plan = [step.model_dump() for step in plan.steps]

        # Main execution loop
        self.state.transition_to(AgentState.EXECUTING, "Starting plan execution")

        while not self.state.should_terminate(self.config.agent.max_steps):
            self.state.increment_step()

            print(f"\n{'='*60}")
            print(f"[STEP] STEP {self.state.step_count}")
            print(f"{'='*60}")

            # Check if plan needs replanning
            if plan.needs_replan:
                print("\n[!]  Plan needs replanning...")
                self.state.transition_to(AgentState.REPLANNING, plan.replan_reason)
                plan = self.planner.replan(plan, plan.replan_reason or "Unknown reason", self.context)
                self.context.plan = [step.model_dump() for step in plan.steps]
                self.state.transition_to(AgentState.EXECUTING, "Replan complete")

            # Check if plan is complete
            if plan.is_complete():
                print("\n[OK] Plan completed successfully")
                self.state.transition_to(AgentState.COMPLETED, "All steps completed")
                break

            # Get current step
            current_step = plan.get_next_step()
            if not current_step:
                break

            # Decide action using ReAct
            react_step = self.react.decide_action(plan, self.context)

            # Store step in context
            step_record = self.context.add_step(
                thought=react_step.thought,
                action=react_step.action,
                action_args=react_step.action_args,
                observation="",
            )

            # Update plan status
            current_step.status = "in_progress"

            # Execute action
            observation = self.react.execute_action(react_step)

            # Update context
            self.context.update_last_step(observation, "success" if not observation.startswith("ERROR") else "failure")

            # Process observation
            analysis = self.react.process_observation(observation, self.context)

            # Update memory
            self.memory.update_short_term(
                action=react_step.action,
                observation=observation,
                error=observation if observation.startswith("ERROR") else None,
            )
            self.memory.add_step_to_history({
                "step": self.state.step_count,
                "action": react_step.action,
                "observation": observation,
                "timestamp": datetime.now().isoformat(),
            })

            # Handle failures
            if not analysis["success"]:
                self.context.increment_failures()
                plan.mark_step_failed(current_step.step_id, observation)

                print(f"\n[X] Step failed (consecutive failures: {self.context.consecutive_failures})")

                # Check if we should replan
                if self.context.consecutive_failures >= self.config.agent.replan_threshold:
                    plan.needs_replan = True
                    plan.replan_reason = f"Exceeded failure threshold ({self.context.consecutive_failures})"

                # Trigger reflection
                if self.config.agent.enable_reflexion:
                    self.state.transition_to(AgentState.REFLECTING, "Handling failure")
                    reflection = self.reflexion.reflect(
                        error=observation,
                        context=self.context,
                        level="L2",
                    )

                    # Learn from reflection
                    if reflection.lesson:
                        fix = reflection.fix_suggestions[0].action if reflection.fix_suggestions else "unknown"
                        self.memory.learn_from_error(
                            error=observation,
                            fix=fix,
                            success=False,
                        )

                    self.state.transition_to(AgentState.EXECUTING, "Reflection complete")
            else:
                # Success
                self.context.reset_failures()
                plan.mark_step_complete(current_step.step_id, observation)
                print(f"\n[OK] Step completed successfully")

            # Check for termination
            if plan.is_complete():
                self.state.transition_to(AgentState.COMPLETED, "Goal achieved")
                break

        # Handle loop termination
        if self.state.current_state not in [AgentState.COMPLETED, AgentState.FAILED]:
            if self.state.step_count >= self.config.agent.max_steps:
                self.state.transition_to(AgentState.TERMINATED, f"Max steps reached ({self.config.agent.max_steps})")
            else:
                self.state.transition_to(AgentState.COMPLETED, "Loop ended")

        # Mark context complete
        self.context.mark_complete(self.state.current_state.value)

        # Print final summary
        self._print_final_summary()

        return self.context

    def _print_final_summary(self) -> None:
        """
        Print final execution summary.
        """
        if not self.context:
            return

        print("\n" + "=" * 60)
        print("[STAT] FINAL EXECUTION SUMMARY")
        print("=" * 60)

        print(f"\n[GOAL] Goal: {self.context.goal}")

        print(f"\n[PROGRESS] Status: {self.state.current_state.value.upper()}")
        print(f"   Total Steps:    {self.state.step_count}")
        print(f"   Duration:       {self.context.get_duration():.2f}s")
        print(f"   Final Failures: {self.context.consecutive_failures}")

        # Step summary
        completed = len([s for s in self.context.steps if s.result == "success"])
        failed = len([s for s in self.context.steps if s.result == "failure"])
        print(f"\n[NOTE] Step Results:")
        print(f"   Completed: {completed}")
        print(f"   Failed:    {failed}")

        # Print recent steps
        if self.context.steps:
            print(f"\n[INFO] Recent Steps:")
            for step in self.context.steps[-5:]:
                icon = "[OK]" if step.result == "success" else "[X]"
                print(f"   {icon} Step {step.step_id}: {step.action}")

        # Memory status
        if self.config.agent.enable_memory:
            print(f"\n[BRAIN] Memory:")
            print(f"   Short-term entries: {len(self.memory.short_term.recent_steps)}")
            print(f"   Long-term entries:  {len(self.memory.long_term)}")

        print("\n" + "=" * 60)
        print("[END] Agent Execution Complete")
        print("=" * 60 + "\n")

    def get_status(self) -> Dict[str, Any]:
        """
        Get current agent status.

        Returns:
            Dict with status information
        """
        return {
            "state": self.state.current_state.value,
            "step_count": self.state.step_count,
            "context": self.context.model_dump() if self.context else None,
            "memory": {
                "short_term_size": len(self.memory.short_term.recent_steps),
                "long_term_size": len(self.memory.long_term),
            },
        }


# ============================================================
# Factory Function
# ============================================================

def create_agent() -> Agent:
    """
    Create a new Agent instance.

    Returns:
        Agent: New agent instance
    """
    return Agent()
