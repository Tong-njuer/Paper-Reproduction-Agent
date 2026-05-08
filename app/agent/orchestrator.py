import re
from typing import Callable, Dict, List, Optional

from app.core.config import get_config
from app.core.llm import get_llm
from app.core.logging import get_logger
from app.agent.state import AgentState, StateManager
from app.agent.memory import Memory, StepRecord
from app.agent.planner import Planner, Plan
from app.agent.react import ReActEngine, ReActStep
from app.agent.reflection import Reflection, ReflectionResult
from app.tools import list_available_tools


class AgentResult:
    def __init__(self):
        self.success: bool = False
        self.goal: str = ""
        self.summary: str = ""
        self.source_url: str = ""
        self.paper_content: str = ""
        self.paper_info: Dict = {}
        self.steps: List[Dict] = []
        self.errors: List[str] = []

    def to_dict(self) -> dict:
        return {
            "success": self.success, "goal": self.goal,
            "summary": self.summary, "source_url": self.source_url,
            "paper_content": self.paper_content,
            "paper_info": self.paper_info, "steps": self.steps,
            "errors": self.errors,
        }


class Orchestrator:
    def __init__(self, on_step: Optional[Callable] = None,
                 on_log: Optional[Callable] = None):
        config = get_config()
        agent_cfg = config.agent
        self._log = get_logger("orchestrator")
        self._state = StateManager(max_steps=agent_cfg.max_steps)
        self._memory = Memory(
            enabled=agent_cfg.enable_memory,
            memory_dir="./data/memory",
        )
        self._planner = Planner()
        self._react = ReActEngine(max_retries=agent_cfg.max_retries)
        self._reflection = Reflection(enabled=agent_cfg.enable_reflection)
        self._max_retries = agent_cfg.max_retries
        self._replan_threshold = agent_cfg.replan_threshold
        self._on_step = on_step
        self._on_log = on_log

    def _emit_step(self, step_data: dict):
        if self._on_step:
            try:
                self._on_step(step_data)
            except Exception:
                pass

    def _emit_log(self, level: str, message: str):
        if self._on_log:
            try:
                self._on_log(level, message)
            except Exception:
                pass

    def run(self, goal: str) -> AgentResult:
        result = AgentResult()
        result.goal = goal

        self._log.info(f"Starting agent for goal: {goal}")
        self._emit_log("info", f"开始执行目标: {goal}")

        # Phase 1: Plan
        self._state.transition_to(AgentState.PLANNING, "Starting planning")
        plan = self._planner.create_plan(goal, self._memory.context_for_prompt())
        self._emit_step({
            "type": "plan", "status": "done",
            "steps": [s.to_dict() for s in plan.steps],
        })
        self._emit_log("info", f"规划完成: {len(plan.steps)} 个步骤")
        for s in plan.steps:
            self._emit_log("info", f"  步骤{s.step_id}: {s.description}")

        consecutive_failures = 0

        # Phase 2: Execute loop
        while not self._state.should_terminate():
            current = plan.get_next_step()
            if current is None:
                self._log.info("All steps complete")
                break

            self._state.transition_to(AgentState.EXECUTING, f"Step {current.step_id}")
            self._state.step()
            current.status = "active"

            self._emit_step({
                "type": "step_start", "step_id": current.step_id,
                "description": current.description,
            })

            # ReAct: decide -> execute
            history = self._memory.context_for_prompt()
            tools_desc = "\n".join(
                f"- {n}: {d}" for n, d in list_available_tools().items()
            )
            react_step = self._react.decide(goal, current, history, tools_desc)

            # Record step
            record = StepRecord(
                step_id=f"step_{current.step_id}",
                description=current.description,
                thought=react_step.thought,
                action=react_step.action,
                action_args=react_step.action_args,
                status="active",
            )
            self._memory.add_step(record)

            self._emit_step({
                "type": "react", "step_id": current.step_id,
                "thought": react_step.thought,
                "action": react_step.action,
                "action_args": react_step.action_args,
            })
            self._emit_log("info",
                           f"步骤{current.step_id} | 思考: {react_step.thought[:80]}")
            self._emit_log("info",
                           f"步骤{current.step_id} | 行动: {react_step.action}({react_step.action_args})")

            # Execute action
            observation = self._react.execute(react_step)

            self._emit_step({
                "type": "observation", "step_id": current.step_id,
                "observation": observation,
                "status": react_step.status,
            })

            if react_step.status == "success":
                consecutive_failures = 0
                self._state.reset_retry()
                plan.mark_done(current.step_id, observation)
                self._memory.update_last(status="done", observation=observation)
                result.steps.append({
                    "step_id": current.step_id,
                    "description": current.description,
                    "thought": react_step.thought,
                    "action": react_step.action,
                    "observation": observation[:500],
                    "status": "success",
                })
                self._emit_log("success",
                               f"步骤{current.step_id} 完成: {observation[:100]}")
                self._extract_result_info(result, current, observation)

            else:
                consecutive_failures += 1
                self._state.increment_retry()
                error_msg = observation.replace("ERROR: ", "")
                self._memory.update_last(status="failed", error=error_msg)
                result.errors.append(f"Step {current.step_id}: {error_msg}")
                self._emit_log("error",
                               f"步骤{current.step_id} 失败: {error_msg[:150]}")

                # Phase 3: Reflect
                self._state.transition_to(AgentState.REFLECTING,
                                          f"Error in step {current.step_id}")
                reflection = self._reflection.reflect(
                    error=error_msg,
                    step_desc=current.description,
                    history=self._memory.context_for_prompt(),
                    level="L2" if consecutive_failures < 2 else "L3",
                )

                self._emit_step({
                    "type": "reflection", "step_id": current.step_id,
                    "analysis": reflection.analysis.to_dict(),
                    "fix_suggestions": [f.to_dict() for f in reflection.fix_suggestions],
                    "should_replan": reflection.should_replan,
                })
                self._emit_log("warning",
                               f"反思 [{reflection.level}]: {reflection.analysis.explanation}")

                # Record learning
                self._memory.learn_from_error(
                    error_pattern=reflection.analysis.error_type,
                    fix_strategy="; ".join(
                        f.description for f in reflection.fix_suggestions[:2]
                    ),
                )

                # Decide: retry or replan
                if reflection.should_replan or consecutive_failures >= self._replan_threshold:
                    self._state.transition_to(AgentState.REPLANNING,
                                              f"Replan after {consecutive_failures} failures")
                    self._emit_log("warning", "触发重新规划...")
                    plan = self._planner.replan(plan, current, error_msg)
                    consecutive_failures = 0
                    self._emit_step({
                        "type": "replan",
                        "steps": [s.to_dict() for s in plan.steps],
                    })
                else:
                    # Retry: apply first fix suggestion
                    if reflection.fix_suggestions:
                        fix = reflection.fix_suggestions[0]
                        self._emit_log("info",
                                       f"重试步骤{current.step_id}: {fix.description}")
                        plan.mark_failed(current.step_id, error_msg)
                        new_step = type(current)(
                            step_id=len(plan.steps) + 1,
                            description=f"[重试] {current.description}",
                            tool_hint=fix.action,
                        )
                        plan.steps.append(new_step)
                    else:
                        plan.mark_failed(current.step_id, error_msg)

        # Phase 4: Finalize
        if self._state.step_count >= self._state._max_steps:
            self._state.transition_to(AgentState.FAILED, "Max steps reached")
            result.success = False
            result.summary = f"达到最大步数限制 ({self._state._max_steps})，部分任务未完成"
        elif plan.is_complete() or plan.completed_count() > 0:
            self._state.transition_to(AgentState.COMPLETED, "All steps done")
            result.success = True
            result.summary = self._build_summary(result, plan)
        else:
            self._state.transition_to(AgentState.FAILED, "Plan incomplete")
            result.success = False
            result.summary = "未能完成任务"

        self._emit_step({"type": "done", "result": result.to_dict()})
        self._emit_log("info" if result.success else "error",
                       f"执行结束: {result.summary}")
        return result

    def _extract_result_info(self, result: AgentResult, step, observation: str):
        desc = step.description.lower()

        # Source code — match by description keywords
        if any(kw in desc for kw in ["源码", "source", "仓库", "repo", "github", "gitlab"]):
            urls = self._extract_urls(observation)
            for url in urls:
                if self._is_repo_url(url) and not result.source_url:
                    result.source_url = url
                    self._emit_log("success", f"找到源码地址: {url}")

        # Setup / environment configuration — capture local path
        if any(kw in desc for kw in ["配置环境", "setup", "环境", "venv", "虚拟环境",
                                       "安装依赖", "配置依赖"]):
            # Extract local path from setup result
            path_match = re.search(r'(?:路径|本地路径|local_path)[：:]\s*([^\s\n]+)', observation)
            if path_match:
                local_path = path_match.group(1)
                if not result.source_url:
                    result.source_url = local_path
                result.paper_info.setdefault("local_paths", []).append(local_path)
                self._emit_log("success", f"环境配置路径: {local_path}")

        # Paper content — match by description keywords
        if any(kw in desc for kw in ["搜索", "论文", "获取", "阅读", "fetch",
                                       "search", "paper", "arxiv", "访问"]):
            result.paper_content = (result.paper_content + "\n" + observation)[:15000]
            urls = self._extract_urls(observation)
            for url in urls:
                if "arxiv" in url or "paper" in url.lower():
                    result.paper_info.setdefault("urls", []).append(url)

    @staticmethod
    def _extract_urls(text: str) -> List[str]:
        import re
        return re.findall(r'https?://[^\s<>",{}|\\^`\[\]]+', text)

    @staticmethod
    def _is_repo_url(url: str) -> bool:
        import re
        return bool(re.search(r'(github|gitlab|bitbucket|gitee|huggingface)\.com/', url, re.I))

    def _build_summary(self, result: AgentResult, plan: Plan) -> str:
        parts = [f"目标「{result.goal}」执行完成。"]
        if result.source_url:
            parts.append(f"源码地址: {result.source_url}")
        if result.paper_info.get("urls"):
            parts.append(f"论文链接: {', '.join(result.paper_info['urls'][:3])}")
        parts.append(f"共执行 {plan.completed_count()}/{len(plan.steps)} 步")
        if result.errors:
            parts.append(f"遇到 {len(result.errors)} 个错误")
        return "\n".join(parts)

    def get_state(self) -> dict:
        return self._state.summary()
