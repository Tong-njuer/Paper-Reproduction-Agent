import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.core.config import get_config
from app.core.llm import get_llm
from app.core.logging import get_logger
from app.agent.state import AgentState, StateManager
from app.agent.memory import Memory, StepRecord
from app.agent.planner import Planner, Plan, PlanStep
from app.agent.react import ReActEngine, ReActStep
from app.agent.reflection import Reflection, ReflectionResult
from app.tools import list_available_tools, get_tool
from app.tools.report_store import get_report_store
from datetime import datetime


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
        self._step_context: Dict[str, str] = {}  # deterministic inter-step data
        self._failed_urls: set = set()  # URLs that have been tried for clone and failed

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

        # Phase 2: Execute loop with in-place retry
        while not self._state.should_terminate():
            current = plan.get_next_step(allow_retry=True)
            if current is None:
                self._log.info("All steps complete")
                break

            is_retry = current.retry_count > 0
            self._state.transition_to(AgentState.EXECUTING, f"Step {current.step_id}")
            self._state.step()
            current.status = "active"

            retry_tag = f" [重试 #{current.retry_count}]" if is_retry else ""
            self._emit_step({
                "type": "step_start", "step_id": current.step_id,
                "description": current.description,
                "retry": is_retry, "retry_count": current.retry_count,
            })
            self._emit_log("info",
                           f"步骤{current.step_id}{retry_tag}: {current.description}")

            # --- Summary/report step: skip ReAct, call ReportTool directly ---
            if self._is_summary_step(current):
                self._handle_summary_step(current, result, plan)
                break

            # ReAct: decide -> execute
            history = self._memory.context_for_prompt()
            tools_desc = "\n".join(
                f"- {n}: {d}" for n, d in list_available_tools().items()
            )
            # Always force the planned tool — LLM only determines args
            react_step = self._react.decide(
                goal, current, history, tools_desc,
                force_tool=current.tool_hint,
            )

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
            # Enrich args with deterministic inter-step data
            self._enrich_args(react_step)

            self._emit_log("info",
                           f"步骤{current.step_id}{retry_tag} | 行动: {react_step.action}({react_step.action_args})")

            # Execute action
            observation = self._react.execute(react_step)

            self._emit_step({
                "type": "observation", "step_id": current.step_id,
                "observation": observation,
                "status": react_step.status,
            })

            if react_step.status == "success":
                # VERIFY step completion before marking done
                verified, verify_msg = self._verify_step_completion(
                    current, observation
                )
                if verified:
                    consecutive_failures = 0
                    self._state.reset_retry()
                    plan.mark_done(current.step_id, observation)
                    self._memory.update_last(status="done", observation=observation)
                    result.steps.append({
                        "step_id": current.step_id,
                        "description": current.description,
                        "thought": react_step.thought,
                        "action": react_step.action,
                        "observation": observation[:8000],
                        "status": "success",
                        "retry_count": current.retry_count,
                    })
                    self._emit_log("success",
                                   f"步骤{current.step_id} 完成: {observation[:100]}")
                    self._extract_result_info(result, current, observation)
                    continue  # Move to next step

                # Tool succeeded but goal not achieved
                react_step.status = "failed"
                observation = f"ERROR: 步骤验证失败 - {verify_msg}"
                self._emit_log("warning",
                               f"步骤{current.step_id} 验证失败: {verify_msg}")

            # --- Step failed ---
            consecutive_failures += 1
            self._state.increment_retry()
            plan.mark_failed(current.step_id, observation)  # increments retry_count

            error_msg = observation.replace("ERROR: ", "")
            self._memory.update_last(status="failed", error=error_msg)
            result.errors.append(
                f"Step {current.step_id} (尝试 {current.retry_count}/{current.max_retries}): {error_msg[:200]}"
            )
            self._emit_log("error",
                           f"步骤{current.step_id} 失败 ({current.retry_count}/{current.max_retries}): {error_msg[:150]}")

            # Track failed clone URLs so _enrich_args won't force them on retry
            if current.tool_hint == "clone_tool":
                failed_url = react_step.action_args.get("repo_url", "")
                if failed_url:
                    self._failed_urls.add(failed_url)
                    # Clear the stored context URL so retry uses a fresh one
                    if self._step_context.get("repo_url") == failed_url:
                        self._step_context.pop("repo_url", None)
                        self._emit_log("info",
                                       f"Cleared failed repo_url from context: {failed_url}")

            # Phase 3a: Try ErrorHandlerTool BEFORE reflection (fast fix)
            error_handled = self._try_error_handler(current, error_msg)

            if error_handled:
                # Error was fixed — skip reflection, retry step immediately
                self._emit_log("info",
                               f"步骤{current.step_id} 错误已被ErrorHandler修复，立即重试")
                plan.retry_step(current.step_id)
                continue  # Back to loop, same step picked up as "pending"

            # Phase 3b: Reflect (only if error handler didn't fix it)
            self._state.transition_to(AgentState.REFLECTING,
                                      f"Error in step {current.step_id}")
            reflection_level = "L1" if current.retry_count == 1 else ("L2" if current.retry_count < current.max_retries else "L3")
            reflection = self._reflection.reflect(
                error=error_msg,
                step_desc=current.description,
                history=self._memory.context_for_prompt(),
                level=reflection_level,
            )

            self._emit_step({
                "type": "reflection", "step_id": current.step_id,
                "analysis": reflection.analysis.to_dict(),
                "fix_suggestions": [f.to_dict() for f in reflection.fix_suggestions],
                "should_replan": reflection.should_replan,
                "retry_count": current.retry_count,
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

            # Decide: in-place retry, replan, or skip
            if current.retry_count < current.max_retries:
                # In-place retry: apply fix suggestion and loop back
                if reflection.fix_suggestions:
                    fix = reflection.fix_suggestions[0]
                    self._emit_log("info",
                                   f"步骤{current.step_id} 应用修复 ({current.retry_count}/{current.max_retries}): {fix.description}")
                    # Allow tool changes only for well-defined error→fix mappings
                    if fix.action and fix.action in list_available_tools():
                        if fix.action == current.tool_hint:
                            current.tool_hint = fix.action
                        elif self._allow_cross_tool_fix(
                            reflection.analysis.error_type, current.tool_hint, fix.action
                        ):
                            self._emit_log("info",
                                           f"允许跨工具修复: {current.tool_hint} → {fix.action} ({reflection.analysis.error_type})")
                            current.tool_hint = fix.action
                        else:
                            self._emit_log("warning",
                                           f"忽略跨工具修复建议: {fix.action} (当前工具: {current.tool_hint})")
                    if fix.args:
                        current.expected_artifact = fix.description
                plan.retry_step(current.step_id)
                # Loop continues — same step picked up as "pending" again
            elif reflection.should_replan or consecutive_failures >= self._replan_threshold:
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
                # Max retries exhausted, non-critical step → skip
                plan.skip_step(current.step_id,
                               f"已达最大重试次数 ({current.max_retries})")
                self._emit_log("warning",
                               f"步骤{current.step_id} 跳过（已达最大重试次数）")
                result.steps.append({
                    "step_id": current.step_id,
                    "description": current.description,
                    "status": "skipped",
                    "reason": f"Max retries ({current.max_retries}) exhausted",
                })

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

        # Auto-save report when there is meaningful output
        if result.steps or result.summary:
            self._save_report(result)

        return result

    def _save_report(self, result: AgentResult):
        """Persist the final report to ReportStore."""
        try:
            store = get_report_store()
            report = {
                "goal": result.goal,
                "success": result.success,
                "timestamp": datetime.now().isoformat(),
                "summary": result.summary,
                "source_url": result.source_url,
                "paper_info": result.paper_info,
                "steps": result.steps,
                "errors": result.errors,
            }
            store.save(report)
        except Exception as e:
            self._log.warning(f"Failed to auto-save report: {e}")

    def _extract_result_info(self, result: AgentResult, step, observation: str):
        desc = step.description.lower()

        # Source code — only extract repo URLs from source_tool (which is
        # specifically designed to find official repos from paper references).
        # search_tool returns arXiv results that may mention unrelated repos.
        if step.tool_hint == "source_tool":
            urls = self._extract_urls(observation)
            for url in urls:
                if self._is_repo_url(url) and not result.source_url:
                    result.source_url = url
                    self._step_context["repo_url"] = url
                    self._emit_log("success", f"找到源码地址: {url}")

        # Setup / environment configuration — capture local path
        if any(kw in desc for kw in ["配置环境", "setup", "环境", "venv", "虚拟环境",
                                       "安装依赖", "配置依赖"]):
            path_match = re.search(r'(?:路径|本地路径|local_path)[：:]\s*([^\s\n]+)', observation)
            if path_match:
                local_path = path_match.group(1)
                if not result.source_url:
                    result.source_url = local_path
                result.paper_info.setdefault("local_paths", []).append(local_path)
                self._step_context["planned_repo_path"] = local_path
                self._emit_log("success", f"环境配置路径: {local_path}")

        # Paper content — match by description keywords
        if any(kw in desc for kw in ["搜索", "论文", "获取", "阅读", "fetch",
                                       "search", "paper", "arxiv", "访问"]):
            result.paper_content = (result.paper_content + "\n" + observation)[:15000]
            urls = self._extract_urls(observation)
            for url in urls:
                if "arxiv" in url or "paper" in url.lower():
                    result.paper_info.setdefault("urls", []).append(url)
                    # Forward to fetch_tool so it doesn't hallucinate URLs
                    if not self._step_context.get("paper_url"):
                        self._step_context["paper_url"] = url

        # plan_run_tool — capture the determined command & path for run_tool
        if step.tool_hint == "plan_run_tool":
            cmd_match = re.search(r'命令[：:]\s*(.+?)(?:\n|$)', observation)
            if cmd_match:
                cmd = cmd_match.group(1).strip()
                self._step_context["planned_command"] = cmd
                self._emit_log("success", f"已捕获执行命令: {cmd[:120]}")
            path_match = re.search(r'路径[：:]\s*([^\s\n]+)', observation)
            if path_match:
                self._step_context["planned_repo_path"] = path_match.group(1)
                self._emit_log("success", f"已捕获仓库路径: {path_match.group(1)}")

        # Execution — capture repo analysis and results for post-execution Q&A
        if any(kw in desc for kw in ["执行", "运行", "execute", "run",
                                       "复现脚本", "复现执行",
                                       "read_repo", "plan_run",
                                       "规划.*命令", "确定.*命令"]):
            result.paper_content = (result.paper_content + "\n" + observation)[:15000]
            result.paper_info.setdefault("execution_results", []).append(
                observation[:8000]
            )
            # Extract repo path from execution
            path_match = re.search(r'路径[：:]\s*([^\s\n]+)', observation)
            if path_match and not result.source_url:
                result.source_url = path_match.group(1)

    # ------------------------------------------------------------------
    # Step completion verification
    # ------------------------------------------------------------------

    def _verify_step_completion(self, step: PlanStep, observation: str) -> tuple[bool, str]:
        """Verify that a step actually achieved its goal, not just that the tool ran OK."""
        tool = step.tool_hint

        if tool == "clone_tool":
            return self._verify_clone(step, observation)
        elif tool == "setup_tool":
            return self._verify_setup(step, observation)
        elif tool == "search_tool":
            return self._verify_search(step, observation)
        elif tool == "fetch_tool":
            return self._verify_fetch(step, observation)
        elif tool == "source_tool":
            return self._verify_source(step, observation)
        elif tool == "execute_tool":
            return self._verify_execute(step, observation)
        elif tool == "read_repo_tool":
            return self._verify_read_repo(step, observation)
        elif tool == "plan_run_tool":
            return self._verify_plan_run(step, observation)
        elif tool == "run_tool":
            return self._verify_run(step, observation)
        elif tool == "execute_session_tool":
            return self._verify_execute_session(step, observation)
        else:
            # Unknown tool — check observation is non-empty and not an error
            if not observation or observation.strip() == "":
                return False, "工具输出为空"
            if observation.startswith("ERROR:"):
                return False, observation
            return True, ""

    def _verify_clone(self, step: PlanStep, observation: str) -> tuple[bool, str]:
        """Verify clone: the specific target repo directory must exist in workspace."""
        if observation.startswith("ERROR:"):
            return False, observation

        # Extract local path from observation
        path_match = re.search(r'本地路径[：:]\s*([^\s\n]+)', observation)
        if path_match:
            local_path = Path(path_match.group(1))
            if local_path.exists() and (local_path / ".git").exists():
                return True, ""
            return False, f"克隆目录不存在或无.git: {local_path}"

        # _pull existing-repo format: "仓库已存在于本地: /app/workspace/xxx"
        existing_match = re.search(
            r'仓库已存在于本地[：:]\s*([^\s\n]+)', observation
        )
        if existing_match:
            local_path = Path(existing_match.group(1))
            if local_path.exists() and (local_path / ".git").exists():
                return True, ""
            return False, f"本地仓库目录不存在: {local_path}"

        # Extract repo URL from observation to derive expected directory name
        url_match = re.search(r'仓库[：:]\s*(https?://[^\s\n]+)', observation)
        if url_match:
            repo_url = url_match.group(1)
            repo_name = repo_url.rstrip("/").split("/")[-1]
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            expected_path = Path(get_config().agent.workspace_dir).resolve() / repo_name
            if expected_path.exists() and (expected_path / ".git").exists():
                return True, ""
            return False, f"克隆后仓库目录未找到: {expected_path}"

        # Last resort: observation says "克隆成功" — check workspace for the repo
        # derived from step description or tool context
        if "克隆成功" in observation or "拉取最新代码" in observation:
            ws = Path(get_config().agent.workspace_dir).resolve()
            # Try to find the repo from step description or any recent git dir
            repo_name_match = re.search(
                r'(?:仓库|repo|克隆)[^\n]*?[/\s]([a-zA-Z0-9_.-]+)(?:\s|$|\.git)',
                observation
            )
            if repo_name_match:
                expected = ws / repo_name_match.group(1).rstrip(".git")
                if expected.exists() and (expected / ".git").exists():
                    return True, ""
            # Broad fallback: check any git repo modified in the last minute
            import time
            now = time.time()
            for d in sorted(ws.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if d.is_dir() and (d / ".git").exists():
                    mtime = d.stat().st_mtime
                    if now - mtime < 120:  # modified within 2 minutes
                        return True, ""
            return False, "输出显示克隆成功但无法在workspace中确认仓库"

        return False, "无法从输出中确定克隆结果，缺少本地路径或仓库URL"

    def _verify_setup(self, step: PlanStep, observation: str) -> tuple[bool, str]:
        """Verify setup: venv must exist AND no critical pip install failures."""
        if observation.startswith("ERROR:"):
            return False, observation

        # Check for pip install failures in the output
        # setup_tool prints [WARN] for each failed package install
        warn_matches = re.findall(r'\[WARN\]\s*(.+)', observation)
        pip_errors = [m for m in warn_matches if any(
            kw in m.lower() for kw in [
                "no matching distribution", "could not find",
                "could not install", "error:",
            ]
        )]
        if pip_errors:
            first_err = pip_errors[0][:150]
            return False, f"依赖安装失败，{len(pip_errors)} 个包未能安装: {first_err}"

        # Check for venv path in output
        path_match = re.search(r'(?:venv|虚拟环境).*?[：:]\s*([^\s\n]+)', observation)
        if path_match:
            venv_path = Path(path_match.group(1))
        else:
            # Try local_path from observation
            path_match = re.search(r'路径[：:]\s*([^\s\n]+)', observation)
            if path_match:
                repo_path = Path(path_match.group(1))
                venv_path = repo_path / ".venv"
            else:
                return False, "无法确定虚拟环境路径"

        if venv_path.exists():
            import sys
            if sys.platform == "win32":
                py = venv_path / "Scripts" / "python.exe"
            else:
                py = venv_path / "bin" / "python"
            if py.exists():
                return True, ""
            return False, f"虚拟环境存在但Python解释器未找到: {py}"
        return False, f"虚拟环境目录不存在: {venv_path}"

    def _verify_search(self, step: PlanStep, observation: str) -> tuple[bool, str]:
        """Verify search: output should contain paper info."""
        if not observation or observation.strip() == "":
            return False, "搜索返回空结果"
        if observation.startswith("ERROR:"):
            return False, observation
        # Negative indicators — the search ran but found nothing
        no_result_markers = [
            "未找到", "not found", "no results", "0 results",
            "无结果", "找不到", "no paper", "no match",
            "could not find", "couldn't find",
        ]
        obs_lower = observation.lower()
        for marker in no_result_markers:
            if marker in obs_lower:
                return False, f"搜索未找到相关论文 (检测到: {marker})"
        # Should contain some paper-like content
        if any(kw in observation for kw in ["标题", "Title", "作者", "Author", "摘要", "Abstract", "年份", "Year"]):
            return True, ""
        # Non-empty but without clear paper metadata — flag as uncertain
        return False, "搜索结果中未检测到论文元数据（标题/作者/摘要等）"

    def _verify_fetch(self, step: PlanStep, observation: str) -> tuple[bool, str]:
        """Verify fetch: output should be non-empty content."""
        if not observation or observation.strip() == "":
            return False, "获取内容为空"
        if observation.startswith("ERROR:"):
            return False, observation
        return True, ""

    def _verify_source(self, step: PlanStep, observation: str) -> tuple[bool, str]:
        """Verify source: output should contain a repo URL."""
        if not observation or observation.strip() == "":
            return False, "源码搜索返回空结果"
        if observation.startswith("ERROR:"):
            return False, observation
        urls = self._extract_urls(observation)
        if any(self._is_repo_url(u) for u in urls):
            return True, ""
        if "github.com" in observation or "gitlab.com" in observation:
            return True, ""
        return False, "未在结果中找到有效的源码仓库链接"

    def _verify_execute(self, step: PlanStep, observation: str) -> tuple[bool, str]:
        """Verify execution: exit code should be 0, no fatal errors."""
        if not observation or observation.strip() == "":
            return False, "执行输出为空"
        if observation.startswith("ERROR:"):
            return False, observation
        # Check exit code from output
        if "退出码: 0" in observation or "exit_code" in observation.lower():
            if "执行成功" in observation or "success" in observation.lower():
                return True, ""
        # Check for fatal error indicators
        fatal_markers = ["Traceback (most recent call last)", "Error:", "FATAL"]
        if any(m in observation for m in fatal_markers):
            return False, "执行输出中包含错误"
        # Non-empty output without fatal errors is acceptable
        return True, ""

    def _verify_read_repo(self, step: PlanStep, observation: str) -> tuple[bool, str]:
        """Verify read_repo: output should contain repo analysis info."""
        if not observation or observation.strip() == "":
            return False, "仓库分析输出为空"
        if observation.startswith("ERROR:"):
            return False, observation
        if any(kw in observation for kw in ["仓库分析完成", "README摘要", "框架:", "入口文件"]):
            return True, ""
        return True, ""  # Non-empty output is acceptable

    def _verify_plan_run(self, step: PlanStep, observation: str) -> tuple[bool, str]:
        """Verify plan_run: output should contain the determined command."""
        if not observation or observation.strip() == "":
            return False, "执行计划输出为空"
        if observation.startswith("ERROR:"):
            return False, observation
        if any(kw in observation for kw in ["执行计划确定", "命令:", "命令来源"]):
            return True, ""
        return True, ""

    def _verify_run(self, step: PlanStep, observation: str) -> tuple[bool, str]:
        """Verify run: output should contain execution results."""
        if not observation or observation.strip() == "":
            return False, "执行输出为空"
        if observation.startswith("ERROR:"):
            return False, observation
        fatal_markers = ["Traceback (most recent call last)", "Error:", "FATAL"]
        if any(m in observation for m in fatal_markers):
            return False, "执行输出中包含错误"
        return True, ""

    def _verify_execute_session(self, step: PlanStep, observation: str) -> tuple[bool, str]:
        """Verify execute_session_tool: check for success indicator or explicit failure."""
        if not observation or observation.strip() == "":
            return False, "执行会话输出为空"
        if observation.startswith("ERROR:"):
            return False, observation
        # The tool prefixes output with [SUCCESS] or [FAILED]
        if "[SUCCESS]" in observation:
            return True, ""
        if "[FAILED]" in observation:
            # Still mark as "verified" (tool ran correctly) — the failure
            # will be picked up by the normal error/reflection flow
            return True, ""
        # Non-empty output without clear indicators is acceptable
        return True, ""

    # ------------------------------------------------------------------
    # Summary step handling (bypasses ReAct)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_summary_step(step: PlanStep) -> bool:
        """A step is a summary step only if it has no concrete tool assigned."""
        if not step.tool_hint or step.tool_hint in ("", "report", "report_tool"):
            return True
        # If a real registered tool is assigned, it is NOT a summary step —
        # even if the description contains words like "报告" or "汇总".
        return False

    def _handle_summary_step(self, step: PlanStep, result: AgentResult, plan: Plan):
        """Generate final report using ReportTool, bypassing ReAct."""
        self._emit_log("info", f"步骤{step.step_id}: 生成汇总报告")

        report_tool = get_tool("report_tool")
        if report_tool:
            tool_result = report_tool.execute(
                goal=result.goal,
                steps=result.steps,
                paper_info=result.paper_info,
                source_url=result.source_url,
                errors=result.errors,
                paper_content=result.paper_content,
            )
            summary = tool_result.output if tool_result.success else self._build_summary(result, plan)
        else:
            summary = self._build_summary(result, plan)

        plan.mark_done(step.step_id, summary)
        result.summary = summary
        result.steps.append({
            "step_id": step.step_id,
            "description": step.description,
            "status": "success",
            "observation": summary[:500],
        })
        self._emit_step({
            "type": "summary", "step_id": step.step_id,
            "summary": summary,
        })
        self._emit_log("success", f"报告生成完成")

    # ------------------------------------------------------------------
    # Error handler integration (before reflection)
    # ------------------------------------------------------------------

    def _try_error_handler(self, step: PlanStep, error_msg: str) -> bool:
        """Try the ErrorHandlerTool to fix the error without replanning.
        Returns True if the error was fixed and the step should be retried.
        """
        handler = get_tool("error_handler_tool")
        if not handler:
            return False

        # Determine error type from reflection pattern analysis (lightweight)
        error_type = self._reflection._analyze_pattern(error_msg).error_type

        self._emit_log("info",
                       f"步骤{step.step_id} 尝试ErrorHandler修复 [{error_type}]")

        try:
            result = handler.execute(
                error=error_msg,
                error_type=error_type,
                step_description=step.description,
            )
            if result.success and result.metadata.get("fixed"):
                self._emit_log("success",
                               f"ErrorHandler修复成功: {result.output[:150]}")
                # If error handler found a corrected command, apply it
                corrected_cmd = result.metadata.get("corrected_command")
                if corrected_cmd:
                    self._emit_log("info",
                                   f"ErrorHandler纠正命令: {corrected_cmd}")
                return True
            else:
                self._emit_log("warning",
                               f"ErrorHandler未能修复: {result.error[:150] if result.error else result.output[:150]}")
                return False
        except Exception as e:
            self._log.warning(f"ErrorHandler failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Args enrichment — deterministic inter-step data passing
    # ------------------------------------------------------------------

    def _enrich_args(self, react_step: ReActStep):
        """Inject deterministic args from previous step outputs.
        This prevents the LLM from guessing or inventing parameters
        that were already determined by a prior step.
        """
        tool = react_step.action

        if tool == "run_tool":
            planned_cmd = self._step_context.get("planned_command", "")
            current_cmd = react_step.action_args.get("command", "")
            planned_path = self._step_context.get("planned_repo_path", "")

            # Always trust plan_run_tool's result over LLM hallucination.
            # The LLM should NOT invent commands when a plan already exists.
            if planned_cmd and current_cmd != planned_cmd:
                self._log.info(
                    f"Overriding hallucinated run_tool command: "
                    f"{current_cmd!r} → {planned_cmd!r}"
                )
                react_step.action_args["command"] = planned_cmd

            # Inject repo_path from plan_run_tool to prevent repo name
            # hallucination (e.g. "simclr" → "simclr_repo")
            if planned_path:
                llm_repo = react_step.action_args.get("repo_name", "")
                if llm_repo and planned_path:
                    planned_name = Path(planned_path).name
                    if llm_repo != planned_name:
                        self._log.info(
                            f"Overriding hallucinated repo_name: "
                            f"{llm_repo!r} → {planned_name!r}"
                        )
                        react_step.action_args.pop("repo_name", None)
                        react_step.action_args["repo_path"] = planned_path
                if not react_step.action_args.get("repo_path") and not react_step.action_args.get("repo_name"):
                    react_step.action_args["repo_path"] = planned_path

        elif tool == "execute_session_tool":
            # Inject repo_path/name from previous setup/clone step context
            planned_path = self._step_context.get("planned_repo_path", "")
            if planned_path:
                if not react_step.action_args.get("repo_path") and not react_step.action_args.get("repo_name"):
                    react_step.action_args["repo_path"] = planned_path
            # Inject sub-step callback so the frontend can show per-round progress
            react_step.action_args["on_round"] = self._make_round_callback()

        elif tool == "clone_tool":
            stored_url = self._step_context.get("repo_url", "")
            llm_url = react_step.action_args.get("repo_url", "")
            # Trust the stored URL from source_tool over the LLM's guess,
            # BUT only if the stored URL hasn't already been tried and failed.
            if stored_url and stored_url != llm_url:
                if stored_url in self._failed_urls:
                    self._log.info(
                        f"Stored URL {stored_url!r} previously failed, "
                        f"allowing LLM URL: {llm_url!r}"
                    )
                else:
                    self._log.info(
                        f"Overriding hallucinated repo_url: {llm_url!r} → {stored_url!r}"
                    )
                    react_step.action_args["repo_url"] = stored_url

        elif tool == "fetch_tool":
            stored_url = self._step_context.get("paper_url", "")
            llm_url = react_step.action_args.get("url", "")
            # fetch_tool always needs a URL; LLM often passes empty string.
            # Use the paper URL stored from a previous search_tool/fetch_tool step.
            if stored_url and (not llm_url or llm_url != stored_url):
                self._log.info(
                    f"Enriching fetch_tool url: {llm_url!r} → {stored_url!r}"
                )
                react_step.action_args["url"] = stored_url

    def _make_round_callback(self):
        """Build a callback for execute_session_tool that emits sub-step events.

        Called for each round in the session tool's internal loop, enabling
        the frontend to show per-round progress within a parent step.
        """
        def on_round(round_num: int, phase: str, command: str,
                     detail: str, status: str, max_rounds: int):
            self._emit_step({
                "type": "sub_step",
                "phase": phase,
                "round_num": round_num,
                "max_rounds": max_rounds,
                "command": command,
                "detail": detail,
                "status": status,
            })
        return on_round

    @staticmethod
    def _is_generic_command(cmd: str) -> bool:
        """Check if a command looks like a generic/default guess rather than a real one."""
        # Commands that look like placeholders
        generic_patterns = [
            r'^python\s+main\.py\s*$',
            r'^python\s+run\.py\s*$',
            r'^python\s+train\.py\s*$',
            r'^python\s+test\.py\s*$',
            r'^python\s*$',
            r'^python3\s+main\.py\s*$',
            r'^python3\s+run\.py\s*$',
        ]
        import re as _re
        cmd_stripped = cmd.strip()
        for pat in generic_patterns:
            if _re.match(pat, cmd_stripped):
                return True
        return False

    # ------------------------------------------------------------------
    # Cross-tool fix allowlist
    # ------------------------------------------------------------------

    @staticmethod
    def _allow_cross_tool_fix(error_type: str, current_tool: str, fix_tool: str) -> bool:
        """Allow retry to switch tools only for well-defined error→fix mappings."""
        allowed = {
            # execute_tool / run_tool / execute_session_tool fails with missing deps → setup_tool
            ("import_error", "execute_tool", "setup_tool"): True,
            ("import_error", "run_tool", "setup_tool"): True,
            ("import_error", "execute_session_tool", "setup_tool"): True,
            ("pip_failed", "execute_tool", "setup_tool"): True,
            ("pip_failed", "run_tool", "setup_tool"): True,
            ("pip_failed", "execute_session_tool", "setup_tool"): True,
            ("missing_requirements", "execute_tool", "setup_tool"): True,
            ("missing_requirements", "run_tool", "setup_tool"): True,
            ("missing_requirements", "execute_session_tool", "setup_tool"): True,
            # setup_tool fails on venv → execute may still work
            ("venv_failed", "setup_tool", "execute_tool"): True,
            ("venv_failed", "setup_tool", "run_tool"): True,
            ("venv_failed", "setup_tool", "execute_session_tool"): True,
            # plan_run_tool can't find entry → read_repo_tool re-analyze
            ("no_entry_point", "plan_run_tool", "read_repo_tool"): True,
            ("cmd_not_found", "plan_run_tool", "read_repo_tool"): True,
        }
        return allowed.get((error_type, current_tool, fix_tool), False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_urls(text: str) -> List[str]:
        return re.findall(r'https?://[^\s<>",{}|\\^`\[\]]+', text)

    @staticmethod
    def _is_repo_url(url: str) -> bool:
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
