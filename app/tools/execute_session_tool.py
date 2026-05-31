"""
ExecuteSessionTool — conversational LLM-driven execution loop.

Replaces the rigid read_repo_tool → plan_run_tool → run_tool pipeline
with a multi-turn LLM conversation. The LLM:

1. Reads the repository context (README, entry files, venv info)
2. Proposes shell commands to run
3. Sees stdout/stderr/exit_code
4. Diagnoses errors and proposes fixes
5. Repeats until it declares "done" (success or failure)

This mirrors how human developers work: read, try, see error, fix, repeat.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from app.core.llm import get_llm
from app.core.logging import get_logger
from app.core.config import get_config
from app.tools import BaseTool, ToolResult


VENV_DIR = ".venv"

ENTRY_SCRIPTS = [
    "quick_test.py",
    "main.py", "run.py", "train.py", "eval.py", "demo.py",
    "predict.py", "test.py", "infer.py", "inference.py",
    "run.sh", "start.sh",
]
ENTRY_NOTEBOOKS = [
    "main.ipynb", "demo.ipynb", "train.ipynb",
]


# ---------------------------------------------------------------------------
# Shared helpers (slim copies to avoid cross-module coupling)
# ---------------------------------------------------------------------------

def _workspace() -> Path:
    return Path(get_config().agent.workspace_dir).resolve()


def _list_repos() -> list[Path]:
    ws = _workspace()
    if not ws.exists():
        return []
    return sorted(
        [p for p in ws.iterdir() if p.is_dir() and (p / ".git").exists()],
        key=lambda p: p.name,
    )


def _resolve_repo(repo_path: str, repo_name: str, log) -> tuple[Optional[Path], str]:
    if repo_path:
        target = Path(repo_path).resolve()
    elif repo_name:
        target = _workspace() / repo_name
    else:
        repos = _list_repos()
        if len(repos) == 0:
            return None, "workspace 中没有找到任何仓库。"
        elif len(repos) == 1:
            target = repos[0]
        else:
            names = "\n".join(f"  - {r.name}" for r in repos)
            return None, f"workspace 中有多个仓库，请指定 repo_name:\n{names}"
    if not target.exists():
        return None, f"仓库路径不存在: {target}"
    return target, ""


def _find_venv_python(target: Path) -> Optional[str]:
    venv_path = target / VENV_DIR
    if not venv_path.exists():
        return None
    if sys.platform == "win32":
        py = venv_path / "Scripts" / "python.exe"
    else:
        py = venv_path / "bin" / "python"
    return str(py) if py.exists() else None


def _read_readme(target: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt", "README"):
        p = target / name
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="ignore")[:8000]
            except Exception:
                return ""
    return ""


def _find_entry_files(target: Path) -> list[str]:
    found = []
    for name in ENTRY_SCRIPTS:
        if (target / name).exists():
            found.append(name)
    for name in ENTRY_NOTEBOOKS:
        if (target / name).exists():
            found.append(name)
    for p in target.glob("*.ipynb"):
        rel = str(p.relative_to(target))
        if rel not in found:
            found.append(rel)
    return found[:10]


def _list_root_files(target: Path) -> list[str]:
    """Return a short listing of the repo root (non-hidden files/dirs)."""
    items = []
    for p in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name)):
        if p.name.startswith("."):
            continue
        suffix = "/" if p.is_dir() else ""
        items.append(f"  {p.name}{suffix}")
    return items[:40]


# ---------------------------------------------------------------------------
# ExecuteSessionTool
# ---------------------------------------------------------------------------

class ExecuteSessionTool(BaseTool):
    name = "execute_session_tool"
    description = (
        "对话式执行工具：LLM 在虚拟环境中自主尝试运行项目，"
        "观察输出、诊断错误、提出修复，直到项目成功运行或确认无法运行。"
        "参数: repo_name(仓库名) 或 repo_path(仓库路径), "
        "max_rounds(最大对话轮次，默认10), timeout(命令超时秒数，默认600)"
    )

    def __init__(self):
        self._log = get_logger("execute_session")

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def execute(self, repo_name: str = "", repo_path: str = "",
                max_rounds: int = 15, timeout: int = 600,
                **kwargs) -> ToolResult:
        on_round = kwargs.pop("on_round", None)

        # 1. Resolve repo
        target, err = _resolve_repo(repo_path, repo_name, self._log)
        if err:
            return self._fail(err)

        # 2. Detect environment state (don't fail — let LLM handle setup)
        venv_python = _find_venv_python(target)
        req_info = self._find_requirement_files(target)
        sys_python = sys.executable

        # 3. Gather context
        readme = _read_readme(target)
        entry_files = _find_entry_files(target)
        root_files = _list_root_files(target)
        framework = self._detect_framework(readme)
        usage_commands = self._extract_usage_commands(readme)

        # 4. Build system prompt
        system_prompt = self._build_system_prompt(
            target, venv_python, readme, entry_files,
            root_files, framework, usage_commands,
            req_info, sys_python, timeout,
        )

        # 5. Conversation loop
        conversation = [{"role": "system", "content": system_prompt}]
        final_summary = ""
        final_success = False
        round_history: list[dict] = []  # for stall detection

        llm = get_llm()

        for round_num in range(1, max_rounds + 1):
            self._log.info(f"Session round {round_num}/{max_rounds}")

            # Get LLM decision
            try:
                decision = self._ask_llm(llm, conversation)
            except Exception as e:
                self._log.error(f"LLM call failed in round {round_num}: {e}")
                if on_round:
                    on_round(round_num, "error", "", str(e), "failed", max_rounds)
                return self._fail(
                    f"LLM 调用失败 (round {round_num}): {e}",
                    repo_name=target.name,
                    local_path=str(target),
                    conversation_history=self._serialize_conversation(conversation),
                )

            action = decision.get("action", "")

            if action == "done":
                final_success = decision.get("success", False)
                final_summary = decision.get("summary", "")
                self._log.info(
                    f"Session finished: success={final_success}, "
                    f"summary={final_summary[:120]}"
                )
                if on_round:
                    on_round(round_num, "done", "", final_summary,
                             "success" if final_success else "failed", max_rounds)
                break

            elif action == "run":
                command = decision.get("command", "")
                if not command:
                    conversation.append({
                        "role": "user",
                        "content": "ERROR: 'run' action requires a 'command' field.",
                    })
                    continue

                reason = decision.get("reason", "")
                self._log.info(
                    f"Round {round_num}: running [{reason[:80] if reason else 'no reason'}] "
                    f"-> {command[:120]}"
                )

                # Notify: round started with command
                if on_round:
                    on_round(round_num, "run", command, reason, "running", max_rounds)

                # Record the LLM's intent
                conversation.append({
                    "role": "assistant",
                    "content": f"[{reason}]$ {command}" if reason else f"$ {command}",
                })

                # Execute
                exec_result = self._run_command(target, venv_python, command, timeout)

                # Build feedback for LLM
                feedback = self._build_feedback(exec_result)
                conversation.append({"role": "user", "content": feedback})

                # Notify: round finished with result
                if on_round:
                    on_round(round_num, "result", command,
                             f"exit={exec_result['exit_code']}",
                             "success" if exec_result["success"] else "failed", max_rounds)

                # Track for stall detection
                cmd_category = self._classify_command(command)
                round_history.append({
                    "round": round_num, "command": command,
                    "category": cmd_category,
                    "status": "success" if exec_result["success"] else "failed",
                    "error": exec_result.get("stderr", "")[:300] or exec_result.get("stdout", "")[:300],
                })

                # Detect stall and inject in-session reflection
                if not exec_result["success"]:
                    is_stalled, recent_failures = self._detect_stall(round_history)
                    if is_stalled:
                        reflection_msg = self._build_reflection_injection(recent_failures)
                        short_analysis = (
                            f"{len(recent_failures)} consecutive '{cmd_category}' failures detected. "
                            f"Injecting reflection prompt to force strategy change."
                        )
                        self._log.warning(short_analysis)
                        if on_round:
                            on_round(round_num, "reflect", command,
                                     short_analysis, "reflecting", max_rounds)
                        conversation.append({
                            "role": "user",
                            "content": reflection_msg,
                        })

                # If command succeeded and looks like a successful run, prompt
                # the LLM to consider declaring done
                if exec_result["success"]:
                    conversation.append({
                        "role": "user",
                        "content": (
                            "Command succeeded (exit code 0). "
                            "Is the project running correctly? "
                            'If yes, respond with {"action": "done", ...}. '
                            "If you need to verify further or run additional "
                            'tests, respond with {"action": "run", ...}.'
                        ),
                    })
            else:
                conversation.append({
                    "role": "user",
                    "content": (
                        f"Unknown action: {action!r}. "
                        'Valid actions: "run" (execute a command) or '
                        '"done" (finish the session).'
                    ),
                })
        else:
            # Max rounds exceeded
            final_summary = (
                f"达到最大对话轮次 ({max_rounds})，"
                f"执行未收敛。已尝试 {round_num} 轮命令。"
            )
            final_success = False
            self._log.warning(f"Max rounds ({max_rounds}) exceeded")

        # 6. Build result
        success_indicator = "[SUCCESS]" if final_success else "[FAILED]"
        detailed_log = self._build_execution_log(
            conversation, target.name, final_success, final_summary, round_num
        )
        output = f"{success_indicator} 执行会话结束\n{detailed_log}"

        if final_success:
            return self._ok(
                output=output,
                repo_name=target.name,
                local_path=str(target),
                rounds=round_num,
                summary=final_summary,
                conversation_history=self._serialize_conversation(conversation),
            )
        else:
            return self._fail(
                error=final_summary,
                repo_name=target.name,
                local_path=str(target),
                rounds=round_num,
                summary=final_summary,
                conversation_history=self._serialize_conversation(conversation),
            )

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _build_system_prompt(self, target: Path, venv_python: Optional[str],
                             readme: str, entry_files: list[str],
                             root_files: list[str], framework: str,
                             usage_commands: list[str],
                             req_info: dict, sys_python: str,
                             timeout: int = 600) -> str:
        readme_excerpt = readme[:3000] if readme else "(无 README)"
        entry_str = ", ".join(entry_files[:8]) if entry_files else "(未检测到标准入口文件)"
        root_str = "\n".join(root_files) if root_files else "(空)"
        usage_str = "\n".join(f"  $ {c}" for c in usage_commands[:5]) or "(未提取到)"

        # --- Environment status ---
        if venv_python:
            env_status = f"虚拟环境: 已存在 ({venv_python})"
        else:
            env_status = f"虚拟环境: 不存在，需要创建（系统 Python: {sys_python}）"

        # --- Requirement files ---
        req_lines = []
        if req_info.get("requirements_txt"):
            req_path = req_info["requirements_txt"]
            pkg_list = req_info.get("packages", [])
            pkg_str = "\n  ".join(pkg_list[:15]) if pkg_list else "(空或无法解析)"
            req_lines.append(f"- requirements.txt 内容:\n  {pkg_str}")
        if req_info.get("setup_py"):
            req_lines.append("- setup.py: 存在")
        if req_info.get("pyproject_toml"):
            req_lines.append("- pyproject.toml: 存在")
        req_str = "\n".join(req_lines) if req_lines else "未检测到标准依赖文件"

        # --- Phase-specific guidance ---
        if venv_python:
            phase_guidance = """## 当前阶段: 执行
- 环境已就绪，直接运行项目即可
- 按之前策略: 优先 quick_test / demo / 简单验证脚本"""
        else:
            phase_guidance = f"""## 当前阶段: 环境配置 + 执行
你需要从零开始配置环境并运行项目。

### 第一步: 创建虚拟环境
```bash
{sys_python} -m venv {target / VENV_DIR}
```
- 如果上述命令失败，尝试 `python3 -m venv ...` 或 `virtualenv ...`
- 如果提示 venv 模块未找到，运行 `pip install virtualenv` 然后用 virtualenv

### 第二步: 安装依赖（重要：批量安装）
- **不要逐轮试错**——每次只装一个包的方式极其低效
- **一次性安装核心依赖群**:
  ```bash
  pip install -r requirements.txt --disable-pip-version-check  # 如果有
  pip install -e . --disable-pip-version-check                 # 如果有 setup.py/pyproject.toml
  ```
- 如果 `pip install -e .` 安装速度很慢或超时，检查是否在没有 requirements.txt 的情况下触发了重量级依赖（如 TensorFlow、PyTorch）的版本解析。此时**先手动安装该框架**，再装其他：
  ```bash
  pip install tensorflow --disable-pip-version-check
  pip install -e . --no-deps --disable-pip-version-check  # 只装项目本身，不再解析依赖
  ```
- 安装完成后**只运行一次验证命令**（如 `python -c "import 项目名; print('OK')"`），确认核心导入成功

### 第三步: 处理安装失败
常见问题与解法:
- **包名错误** (如 sklearn → 应为 scikit-learn): 修正包名后重试
- **版本号限制过死** (如 tensorflow==1.15.4): 去掉 == 版本号重试
- **需要编译器** (如 cvxopt、progressbar33): 跳过这些包，它们通常只用于少数示例
- **Python 版本不兼容**: 这是硬限制，诚实报告并结束
- **网络超时**: 重试 pip install，可加 `--default-timeout=120`
- **一次性批量处理**：如果发现缺了多个依赖（如 tensorflow、gym、absl），不要一个个装，而是合并为一个 pip install 命令

### 第四步: 执行
环境就绪后，运行项目的入口脚本/quick_test 验证"""

        return f"""你是一个代码执行代理，负责配置 Python 环境并成功运行开源项目。

## 仓库信息
- 名称: {target.name}
- 路径: {target}
- {env_status}
- 框架: {framework or "unknown"}
- 检测到的入口文件: {entry_str}

## README 摘要
{readme_excerpt}

## 根目录文件列表
{root_str}

## 依赖文件
{req_str}

## README 中提取的执行命令
{usage_str}

{phase_guidance}

## 命令执行规则
- 命令在仓库根目录 ({target}) 下执行
- 如果虚拟环境已存在，PATH 会自动指向 .venv/bin 或 .venv/Scripts，可直接用 `python`
- 如果虚拟环境不存在，需先用系统 Python ({sys_python}) 创建，然后再安装依赖
- 可以运行任何命令: pip install, ls, cat, python script.py 等
- 每个命令有 {timeout}s 超时限制（安装大量依赖时可能需要的更久，但 pip 通常很快）
- **pip install 时始终加 `--disable-pip-version-check` 减少噪音**

## 输出格式
每轮用 JSON 回复:
{{"action": "run", "command": "完整命令", "reason": "简短说明为什么执行这个命令"}}
{{"action": "done", "success": true, "summary": "项目成功运行的总结"}}
{{"action": "done", "success": false, "summary": "无法运行的原因（如 Python 版本不兼容等硬限制）"}}"""

    # ------------------------------------------------------------------
    # Requirement file detection
    # ------------------------------------------------------------------

    def _find_requirement_files(self, target: Path) -> dict:
        info = {}
        req_txt = target / "requirements.txt"
        if req_txt.exists():
            info["requirements_txt"] = str(req_txt)
            try:
                content = req_txt.read_text(encoding="utf-8", errors="ignore")
                pkgs = [line.strip() for line in content.split("\n")
                        if line.strip() and not line.strip().startswith("#")]
                info["packages"] = pkgs
            except Exception:
                info["packages"] = []
        if (target / "setup.py").exists():
            info["setup_py"] = True
        if (target / "pyproject.toml").exists():
            info["pyproject_toml"] = True
        return info

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    def _ask_llm(self, llm, conversation: list[dict]) -> dict:
        """Send conversation to LLM, return parsed decision."""
        messages = list(conversation)

        # Add a final reminder
        messages.append({
            "role": "user",
            "content": (
                "请决定下一步: 运行命令还是结束会话?\n"
                "请用 JSON 格式回复（不要用其他格式）:\n"
                '运行命令: {"action": "run", "command": "要执行的命令", "reason": "说明"}\n'
                '结束会话: {"action": "done", "success": true|false, "summary": "总结"}'
            ),
        })

        # Build a combined prompt for the generate_structured method
        system_msg = ""
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                role_label = {"assistant": "ASSISTANT", "user": "USER"}
                label = role_label.get(m["role"], m["role"].upper())
                user_messages.append(f"[{label}]\n{m['content']}")

        prompt = "\n\n".join(user_messages)
        system = system_msg if system_msg else None

        try:
            return llm.generate_structured(prompt, system_prompt=system)
        except RuntimeError:
            # DeepSeek sometimes returns "[reason]$ command" format instead of JSON.
            # Try to extract the command from the raw response.
            raw = llm.generate(prompt, system_prompt=system).content
            decision = self._parse_freeform_decision(raw)
            if decision:
                self._log.warning(
                    f"LLM returned non-JSON format, parsed manually: "
                    f"{decision.get('action', '?')}"
                )
                return decision
            raise

    # ------------------------------------------------------------------
    # Freeform decision parser (fallback when LLM doesn't return JSON)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_freeform_decision(text: str) -> dict | None:
        """Try to extract a run/done decision from non-JSON LLM output.

        Handles formats like:
          [reason]$ command
          action: run
          {"action": "done" ...
        """
        import re
        text = text.strip()

        # Strategy 1: Check if there's JSON buried in the text (brace matching)
        brace_start = text.find("{")
        if brace_start >= 0:
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        import json
                        try:
                            return json.loads(text[brace_start:i + 1])
                        except json.JSONDecodeError:
                            break

        # Strategy 2: "[reason]$ command" format → action=run
        m = re.match(r'^\[([^\]]*)\]\s*\$\s*(.+)$', text, re.DOTALL)
        if m:
            return {
                "action": "run",
                "reason": m.group(1).strip()[:200],
                "command": m.group(2).strip(),
            }

        # Strategy 3: "$ command" format (no reason) → action=run
        m = re.match(r'^\$\s*(.+)$', text.strip())
        if m:
            return {
                "action": "run",
                "reason": "executing command",
                "command": m.group(1).strip(),
            }

        # Strategy 4: Lines starting with a shell command pattern
        for line in text.split("\n"):
            line = line.strip()
            # Skip conversational lines
            if not line or line.startswith("[") or line.startswith("#"):
                continue
            # Looks like a shell command (contains common patterns)
            if re.match(
                r'^(python|pip|cd\s|ls\s|cat\s|grep\s|find\s|'
                r'\.venv/bin/|\.venv/Scripts/|'
                r'\$|apt|brew|conda|git\s|make|cmake|'
                r'wget|curl|./|bash\s|sh\s)',
                line
            ):
                return {
                    "action": "run",
                    "reason": "extracted from freeform response",
                    "command": line,
                }

        # Strategy 5: Check for done/success keywords
        done_keywords = ["done", "成功", "success", "完成", "finished",
                         "conclusion", "总结", "结论"]
        if any(kw in text.lower() for kw in done_keywords):
            # Try to extract success/failure
            success = not any(kw in text.lower() for kw in
                             ["fail", "失败", "error", "错误", "unable", "无法"])
            return {
                "action": "done",
                "success": success,
                "summary": text[:500],
            }

        return None

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def _run_command(self, target: Path, venv_python: str,
                     command: str, timeout: int) -> dict:
        """Execute a shell command in the repo directory with venv context."""
        result = {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "command": command,
        }

        try:
            # Build venv-enriched environment
            venv_bin = str(target / VENV_DIR / ("Scripts" if sys.platform == "win32" else "bin"))
            # Use a pip mirror for faster downloads (Tsinghua mirror for China)
            pip_index = os.environ.get(
                "PIP_INDEX_URL",
                "https://pypi.tuna.tsinghua.edu.cn/simple",
            )
            env = {
                **os.environ,
                "VIRTUAL_ENV": str(target / VENV_DIR),
                "PATH": f"{venv_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                "PYTHONUNBUFFERED": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_INDEX_URL": pip_index,
            }

            proc = subprocess.run(
                command, shell=True,
                capture_output=True, text=True, timeout=timeout,
                cwd=str(target),
                env=env,
            )

            result["exit_code"] = proc.returncode
            result["stdout"] = proc.stdout
            result["stderr"] = proc.stderr
            result["success"] = proc.returncode == 0

        except subprocess.TimeoutExpired:
            result["stderr"] = f"命令超时 ({timeout}s)"
        except FileNotFoundError as e:
            result["stderr"] = f"命令未找到: {e}"
        except Exception as e:
            result["stderr"] = f"执行异常: {e}"

        return result

    def _build_feedback(self, exec_result: dict) -> str:
        """Build a concise feedback message from command execution result."""
        status = "SUCCESS (exit 0)" if exec_result["success"] else f"FAILED (exit {exec_result['exit_code']})"
        cmd = exec_result["command"]

        stdout = exec_result.get("stdout", "")
        stderr = exec_result.get("stderr", "")

        # Truncate for context window
        if len(stdout) > 2000:
            stdout = stdout[:2000] + f"\n... (truncated, total {len(stdout)} chars)"
        if len(stderr) > 1500:
            stderr = stderr[:1500] + f"\n... (truncated, total {len(stderr)} chars)"

        lines = [
            f"COMMAND: {cmd}",
            f"STATUS: {status}",
        ]
        if stdout:
            lines.append(f"STDOUT:\n{stdout}")
        if stderr:
            lines.append(f"STDERR:\n{stderr}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Stall detection & in-session reflection
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_command(command: str) -> str:
        """Categorize a shell command for stall detection."""
        cmd = command.strip().lower()
        if any(kw in cmd for kw in ["pip install", "pip3 install", "python -m pip install"]):
            return "pip_install"
        if any(kw in cmd for kw in ["python ", "python3 "]) and ".py" in cmd:
            return "python_script"
        if any(kw in cmd for kw in ["python ", "python3 ", "-m venv", "virtualenv"]):
            if ".py" not in cmd:
                return "venv"
        if any(kw in cmd for kw in ["git clone", "git pull", "git checkout"]):
            return "git"
        if any(kw in cmd for kw in ["apt ", "apt-get ", "brew ", "yum ", "conda install"]):
            return "system_pkg"
        if any(kw in cmd for kw in ["jupyter", "nbconvert", "ipynb"]):
            return "notebook"
        if any(kw in cmd for kw in ["ls ", "cat ", "head ", "tail ", "find ", "grep ",
                                      "echo ", "pwd", "which ", "cd "]):
            return "inspect"
        if any(kw in cmd for kw in ["wget ", "curl ", "mkdir", "cp ", "mv ", "rm ",
                                      "tar ", "unzip", "chmod"]):
            return "file_ops"
        return "other"

    @staticmethod
    def _build_reflection_injection(recent_failures: list[dict]) -> str:
        """Build a reflection prompt injected when the LLM appears stuck."""
        failure_summary = "\n".join(
            f"  Round {f['round']}: `{f['command'][:120]}` → {f['error'][:200]}"
            for f in recent_failures[-4:]
        )
        return f"""## 反思提示 (Reflection)

你最近 {len(recent_failures)} 次尝试都失败了（相同的策略但都未解决问题）：

{failure_summary}

请退一步思考:
1. 根本原因是什么？（不是表面错误，而是更深层的问题）
2. 当前策略为什么不起作用？
3. 有没有完全不同的替代方案？

具体建议:
- 如果 pip 反复失败: 检查是否是 Python 版本不兼容、网络问题、或包名/版本错误
- 如果同一命令反复失败: 尝试完全不同的入口脚本，或查看 README 中是否有特殊说明
- 如果依赖安装一直失败: 考虑项目可能根本不需要安装即可运行（纯脚本项目）
- 如果感觉项目无法在当前环境运行: 诚实报告原因并结束

请根据反思结果，选择一个新的、不同的行动，或承认无法继续并结束会话。"""

    def _detect_stall(self, round_history: list[dict],
                      stall_threshold: int = 3) -> tuple[bool, list[dict]]:
        """Check if the LLM is stuck retrying the same failing approach.

        Returns (is_stalled, recent_failures_list).
        """
        if len(round_history) < stall_threshold:
            return False, []

        # Look at the last N entries, find consecutive same-category failures
        recent = round_history[-stall_threshold:]
        categories = [r["category"] for r in recent]
        statuses = [r["status"] for r in recent]

        # All same category AND all failed → stalled
        if len(set(categories)) == 1 and all(s == "failed" for s in statuses):
            return True, recent

        # Extend to more rounds if at least 3 of last 4 same category failed
        if len(round_history) >= 4:
            recent4 = round_history[-4:]
            cats4 = [r["category"] for r in recent4]
            stats4 = [r["status"] for r in recent4]
            dominant = max(set(cats4), key=cats4.count)
            dominant_failures = [
                r for r in recent4
                if r["category"] == dominant and r["status"] == "failed"
            ]
            if len(dominant_failures) >= 3:
                return True, recent4

        return False, []

    # ------------------------------------------------------------------
    # Context gathering
    # ------------------------------------------------------------------

    def _detect_framework(self, readme: str) -> str:
        for fw in ["PyTorch", "TensorFlow", "JAX", "Keras", "transformers",
                    "diffusers", "scikit-learn", "sklearn"]:
            if fw.lower() in readme.lower():
                return fw
        return "unknown"

    def _extract_usage_commands(self, readme: str) -> list[str]:
        commands = []
        code_blocks = re.findall(
            r'```(?:bash|sh|shell|python)?\s*\n(.+?)\n```',
            readme, re.DOTALL,
        )
        for block in code_blocks:
            for line in block.strip().split("\n"):
                line = line.strip()
                if line.startswith("#") or line.startswith("//"):
                    continue
                if any(skip in line.lower() for skip in [
                    "pip ", "apt ", "brew ", "conda ", "git ", "cd ",
                    "docker", "wget", "curl", "echo", "export ", "mkdir",
                ]):
                    continue
                if re.search(r'python3?\s+\S+\.py', line):
                    commands.append(line)

        inline = re.findall(r'`([^`]*python[^`]*\.py[^`]*)`', readme)
        for line in inline:
            line = line.strip()
            if "\n" in line:
                continue
            if re.search(r'python3?\s+\S+\.py', line):
                commands.append(line)

        seen = set()
        unique = []
        for c in commands:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique[:10]

    @staticmethod
    def _serialize_conversation(conversation: list[dict]) -> str:
        """Compact serialization for metadata storage."""
        lines = []
        for m in conversation:
            role = m.get("role", "?")[:1].upper()
            content = m.get("content", "")[:200]
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)

    @staticmethod
    def _build_execution_log(conversation: list[dict], repo_name: str,
                             success: bool, final_summary: str,
                             total_rounds: int) -> str:
        """Build a detailed, human-readable execution log from the conversation.

        Parses the multi-turn LLM conversation to extract: initial state,
        each command attempted, its result, errors encountered, how they
        were resolved, and the final verification.
        """
        lines = [
            f"仓库: {repo_name}",
            f"对话轮次: {total_rounds}",
            f"最终结果: {'成功' if success else '失败'}",
            "",
            "## 执行过程",
        ]

        # Parse assistant messages to extract commands and reasoning
        round_num = 0
        for m in conversation:
            role = m.get("role", "")
            content = m.get("content", "")

            if role == "system":
                # Extract initial state from system prompt
                for hint in ["虚拟环境: 已存在", "虚拟环境: 不存在",
                            "框架:", "检测到的入口文件:"]:
                    for line in content.split("\n"):
                        if hint in line:
                            lines.append(f"  初始状态: {line.strip()}")
                            break

            elif role == "assistant":
                content = content.strip()
                # Format: "[reason]$ command" or just "$ command" or JSON
                if content.startswith("[") and "]$ " in content:
                    bracket_end = content.index("]$ ")
                    reason = content[1:bracket_end]
                    cmd = content[bracket_end + 3:]
                    round_num += 1
                    lines.append(f"\n  Round {round_num}:")
                    lines.append(f"    意图: {reason}")
                    lines.append(f"    命令: {cmd}")
                elif content.startswith("$ "):
                    cmd = content[2:]
                    round_num += 1
                    lines.append(f"\n  Round {round_num}:")
                    lines.append(f"    命令: {cmd}")
                # JSON response (done action) — handled below

            elif role == "user":
                content = content.strip()
                # Skip reflection prompts and prompt reminders in the log
                if content.startswith("## 反思提示"):
                    lines.append(f"\n  ⚠️ 系统检测到连续失败，注入反思提示 (Reflection)")
                    continue
                if "请决定下一步" in content:
                    continue
                if "Command succeeded (exit code 0)" in content:
                    continue

                # Extract command result from feedback
                if content.startswith("COMMAND:"):
                    # Format: COMMAND: xxx\nSTATUS: xxx\nSTDOUT:\n...\nSTDERR:\n...
                    status = ""
                    stdout = ""
                    stderr = ""
                    for line in content.split("\n"):
                        if line.startswith("STATUS:"):
                            status = line.replace("STATUS:", "").strip()
                        elif line.startswith("STDOUT:"):
                            stdout = line.replace("STDOUT:", "").strip()[:500]
                        elif line.startswith("STDERR:"):
                            stderr = line.replace("STDERR:", "").strip()[:500]
                    status_tag = "[OK]" if "SUCCESS" in status else "[FAIL]"
                    lines.append(f"    结果: {status_tag} {status}")
                    if stdout:
                        lines.append(f"    标准输出: {stdout[:300]}")
                    if stderr:
                        lines.append(f"    错误输出: {stderr[:300]}")

        lines.append("")
        lines.append(f"## 最终结论")
        lines.append(final_summary)

        return "\n".join(lines)
