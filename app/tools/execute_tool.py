import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger
from app.core.config import get_config
from app.tools import BaseTool, ToolResult


class ExecuteTool(BaseTool):
    name = "execute_tool"
    description = (
        "在虚拟环境中执行复现脚本。分析README和入口文件，确定执行命令，"
        "在venv中运行并捕获输出。"
        "参数: repo_name(仓库名) 或 repo_path(仓库路径), "
        "command(指定命令，可选), script(指定脚本名，可选), "
        "timeout(超时秒数，默认600)"
    )

    VENV_DIR = ".venv"

    # Entry-point scripts to look for (in priority order)
    ENTRY_SCRIPTS = [
        "quick_test.py",  # preferred: lightweight test that needs no data/weights
        "main.py", "run.py", "train.py", "eval.py", "demo.py",
        "predict.py", "test.py", "infer.py", "inference.py",
        "run.sh", "start.sh",
    ]
    # Notebook files
    ENTRY_NOTEBOOKS = [
        "main.ipynb", "demo.ipynb", "train.ipynb",
        "denoising.ipynb", "inpainting.ipynb",
        "super_resolution.ipynb", "restoration.ipynb",
    ]

    # README sections that contain usage instructions
    USAGE_SECTION_PATTERNS = [
        r'#{1,3}\s*(?:Usage|用法|运行|执行|Run|Execute|Quick\s*Start|Getting\s*Started)',
        r'#{1,3}\s*(?:Example|示例|Demo|演示)',
        r'```(?:bash|sh|shell|python)\s*\n(.+?)\n```',
    ]

    def __init__(self):
        self._log = get_logger("execute_tool")

    @property
    def workspace_dir(self) -> Path:
        cfg = get_config()
        return Path(cfg.agent.workspace_dir).resolve()

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def execute(self, repo_name: str = "", repo_path: str = "",
                command: str = "", script: str = "",
                timeout: int = 600, **kwargs) -> ToolResult:
        # 1. Resolve repo path (same pattern as setup_tool)
        target, err = self._resolve_repo(repo_path, repo_name)
        if err:
            return self._fail(err)

        # 2. Verify venv exists and get Python path
        venv_python = self._find_venv_python(target)
        if not venv_python:
            return self._fail(
                f"虚拟环境未找到: {target / self.VENV_DIR}。请先运行 setup_tool 配置环境。",
                repo_name=target.name,
                local_path=str(target),
            )

        # 3. Analyze repo to determine what to execute
        analysis = self._analyze_repo(target, venv_python)

        if command:
            final_cmd = command
            cmd_source = "用户指定"
        elif script:
            final_cmd = f"{venv_python} {script}"
            cmd_source = f"用户指定脚本: {script}"
        elif analysis["default_command"]:
            final_cmd = analysis["default_command"]
            cmd_source = "README/入口文件自动检测"
        else:
            # Build helpful error
            if analysis["entry_files"]:
                hint = f"发现的入口文件: {', '.join(analysis['entry_files'][:5])}。"
            else:
                hint = "未发现 .py 入口脚本或 .ipynb 笔记本。"
            return self._fail(
                f"未能从仓库中自动检测到可执行命令。{hint}"
                f"请使用 command 或 script 参数指定，"
                f"例如 command='python main.py' 或 script='denoising.ipynb'。",
                repo_name=target.name,
                local_path=str(target),
                analysis=analysis,
            )

        self._log.info(f"Execute [{cmd_source}]: {final_cmd} (cwd={target})")

        # 4. Ensure required tooling is installed (e.g. jupyter for notebooks)
        deps_ok, deps_msg = self._ensure_dependencies(target, venv_python, final_cmd)
        if deps_msg:
            self._log.info(f"Dependency check: {deps_msg}")

        # 5. Execute in venv
        exec_result = self._run_in_venv(target, venv_python, final_cmd, timeout)

        # 5. Build output
        output = self._build_output(
            target, analysis, final_cmd, cmd_source, exec_result, venv_python
        )

        if exec_result["success"]:
            return self._ok(
                output=output,
                repo_name=target.name,
                local_path=str(target),
                venv_python=venv_python,
                command=final_cmd,
                exit_code=exec_result["exit_code"],
                stdout=exec_result["stdout"][:5000],
                analysis=analysis,
            )
        else:
            # Pass full diagnostic output as error so orchestrator can reflect
            error_summary = (
                f"执行失败 (退出码 {exec_result['exit_code']})\n"
                f"命令: {final_cmd}\n"
                f"stderr: {exec_result['stderr'][:1000]}"
            )
            return self._fail(
                error=error_summary,
                repo_name=target.name,
                local_path=str(target),
                venv_python=venv_python,
                command=final_cmd,
                exit_code=exec_result["exit_code"],
                stderr=exec_result["stderr"][:2000],
                stdout=exec_result["stdout"][:2000],
                analysis=analysis,
            )

    # ------------------------------------------------------------------
    # Repo resolution
    # ------------------------------------------------------------------

    def _resolve_repo(self, repo_path: str, repo_name: str) -> tuple[Optional[Path], str]:
        if repo_path:
            target = Path(repo_path).resolve()
        elif repo_name:
            target = self.workspace_dir / repo_name
        else:
            repos = self._list_workspace_repos()
            if len(repos) == 0:
                return None, "workspace 中没有找到任何仓库。请先克隆或指定 repo_name/repo_path。"
            elif len(repos) == 1:
                target = repos[0]
                self._log.info(f"Auto-detected single repo: {target.name}")
            else:
                names = "\n".join(f"  - {r.name}" for r in repos)
                return None, f"workspace 中有多个仓库，请指定 repo_name:\n{names}"

        if not target.exists():
            return None, f"仓库路径不存在: {target}"
        return target, ""

    def _find_venv_python(self, target: Path) -> Optional[str]:
        venv_path = target / self.VENV_DIR
        if not venv_path.exists():
            return None

        if sys.platform == "win32":
            py = venv_path / "Scripts" / "python.exe"
        else:
            py = venv_path / "bin" / "python"
        return str(py) if py.exists() else None

    # ------------------------------------------------------------------
    # Repo analysis
    # ------------------------------------------------------------------

    def _analyze_repo(self, target: Path, venv_python: str) -> dict:
        """Analyze repo to determine what to execute and how."""
        readme = self._read_readme(target)
        entry_files = self._find_entry_files(target)
        usage_commands = self._extract_usage_commands(readme)

        analysis = {
            "readme_summary": self._summarize_readme(readme),
            "entry_files": entry_files,
            "usage_commands": usage_commands,
            "default_command": "",
            "expected_output": "",
            "success_indicators": [],
            "framework": self._detect_framework(readme),
        }

        # Determine default command
        if usage_commands:
            # Use first extracted usage command
            analysis["default_command"] = self._resolve_command(
                usage_commands[0], target, venv_python
            )
        elif entry_files:
            # Pick best entry file
            best = entry_files[0]
            if best.endswith(".ipynb"):
                analysis["default_command"] = self._notebook_command(best, venv_python, target)
            else:
                analysis["default_command"] = f"{venv_python} {best}"
        else:
            # Last resort: check setup.py
            if (target / "setup.py").exists():
                analysis["default_command"] = f"{venv_python} setup.py --help"

        # Determine expected success indicators
        analysis["success_indicators"] = self._extract_success_indicators(readme)

        return analysis

    def _read_readme(self, target: Path) -> str:
        for name in ("README.md", "README.rst", "README.txt", "README"):
            p = target / name
            if p.exists():
                try:
                    return p.read_text(encoding="utf-8", errors="ignore")[:10000]
                except Exception:
                    return ""
        return ""

    def _find_entry_files(self, target: Path) -> list[str]:
        """Find entry-point scripts and notebooks in the repo."""
        found = []
        # Check root-level entries
        for name in self.ENTRY_SCRIPTS:
            p = target / name
            if p.exists():
                found.append(name)
        # Check root-level notebooks
        for name in self.ENTRY_NOTEBOOKS:
            p = target / name
            if p.exists():
                found.append(name)
        # Also find any .ipynb in root (not covered by the fixed list)
        for p in target.glob("*.ipynb"):
            rel = str(p.relative_to(target))
            if rel not in found:
                found.append(rel)
        # Also search one level deep
        for d in target.iterdir():
            if d.is_dir() and not d.name.startswith(".") and d.name != self.VENV_DIR:
                for name in self.ENTRY_SCRIPTS:
                    p = d / name
                    if p.exists():
                        found.append(str(p.relative_to(target)))
        return found[:10]

    def _extract_usage_commands(self, readme: str) -> list[str]:
        """Extract runnable commands from README."""
        commands = []

        # Pattern 1: code blocks with shell/bash/python
        code_blocks = re.findall(
            r'```(?:bash|sh|shell|python)?\s*\n(.+?)\n```',
            readme, re.DOTALL
        )
        for block in code_blocks:
            for line in block.strip().split("\n"):
                line = line.strip()
                # Skip comments, pip install, apt-get etc.
                if line.startswith("#") or line.startswith("//"):
                    continue
                if any(skip in line.lower() for skip in [
                    "pip ", "apt ", "brew ", "conda ", "git ", "cd ",
                    "docker", "wget", "curl", "echo", "export ", "mkdir",
                ]):
                    continue
                # Match: python xxx.py [args]
                if re.search(r'python3?\s+\S+\.py', line):
                    commands.append(line)
                # Match: ./run.sh, bash run.sh
                elif re.search(r'(?:\./|bash\s+)\S+\.sh', line):
                    commands.append(line)
                # Match: direct script invocation with key args
                elif re.search(r'python3?\s+-m\s+\S+', line):
                    commands.append(line)

        # Pattern 2: inline code `python main.py --epochs 10`
        inline = re.findall(r'`([^`]*python[^`]*\.py[^`]*)`', readme)
        for line in inline:
            line = line.strip()
            # Skip multi-line false positives (code blocks caught by pattern 1)
            if "\n" in line:
                continue
            if re.search(r'python3?\s+\S+\.py', line):
                commands.append(line)

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for c in commands:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique[:10]

    def _resolve_command(self, cmd: str, target: Path, venv_python: str) -> str:
        """Resolve a command to use venv Python."""
        # Replace bare 'python'/'python3' with venv python
        # Escape backslashes in replacement for Windows paths
        escaped_py = venv_python.replace("\\", "\\\\")
        cmd = re.sub(r'\bpython3?\b', escaped_py, cmd, count=1)
        # Replace ./script.sh with bash script.sh
        if cmd.startswith("./") and cmd.endswith(".sh"):
            cmd = f"bash {cmd[2:]}"
        return cmd

    def _notebook_command(self, notebook: str, venv_python: str, target: Path) -> str:
        """Build a command to execute a Jupyter notebook."""
        notebook_path = target / notebook
        # Use jupyter nbconvert --execute to run the notebook headlessly
        output_name = Path(notebook).stem + "_output.ipynb"
        return (
            f"{venv_python} -m jupyter nbconvert "
            f"--execute --to notebook "
            f"--ExecutePreprocessor.timeout=600 "
            f"--output {output_name} "
            f"{notebook}"
        )

    def _detect_framework(self, readme: str) -> str:
        for fw in ["PyTorch", "TensorFlow", "JAX", "Keras", "transformers",
                    "diffusers", "scikit-learn", "sklearn"]:
            if fw.lower() in readme.lower():
                return fw
        return "unknown"

    def _extract_success_indicators(self, readme: str) -> list[str]:
        """Try to find expected output / success criteria from README."""
        indicators = []
        # Look for expected output in code blocks near "output" or "result"
        output_section = re.search(
            r'(?:output|result|预期|输出|结果).{0,200}```[^\n]*\n(.+?)\n```',
            readme, re.DOTALL | re.I
        )
        if output_section:
            indicators.append(output_section.group(1).strip()[:500])
        # Look for accuracy/performance numbers
        numbers = re.findall(
            r'(?:accuracy|PSNR|SSIM|BLEU|F1|mAP|AUC)[^0-9]*(\d+\.?\d*)',
            readme, re.I
        )
        for n in numbers[:3]:
            indicators.append(f"Expected metric value: {n}")
        return indicators[:5]

    def _summarize_readme(self, readme: str) -> str:
        """Extract key info from README."""
        lines = []
        # Title
        title = re.search(r'^#\s+(.+)$', readme, re.MULTILINE)
        if title:
            lines.append(f"项目: {title.group(1).strip()[:100]}")
        # Description paragraph (first non-heading, non-empty paragraph)
        para = re.search(r'(?:^|\n\n)([^#\n`][^\n]{50,300})', readme)
        if para:
            lines.append(f"描述: {para.group(1).strip()[:200]}")
        return "\n".join(lines) if lines else "未提取到项目描述"

    # ------------------------------------------------------------------
    # Dependency assurance
    # ------------------------------------------------------------------

    def _ensure_dependencies(self, target: Path, venv_python: str,
                             command: str) -> tuple[bool, str]:
        """Check required tooling and install if missing. Returns (ok, message)."""
        needed = []

        # Notebook execution needs jupyter + nbconvert
        if "jupyter" in command or "nbconvert" in command:
            needed.append("jupyter")
            needed.append("nbconvert")

        if not needed:
            return True, ""

        installed = []
        for pkg in needed:
            ok, _ = self._check_package(venv_python, pkg)
            if not ok:
                self._log.info(f"Missing package: {pkg}, installing...")
                install_ok, msg = self._pip_install(venv_python, pkg)
                if install_ok:
                    installed.append(pkg)
                else:
                    return False, f"无法安装 {pkg}: {msg}"
            else:
                installed.append(pkg)

        if installed:
            return True, f"已就绪: {', '.join(installed)}"
        return True, ""

    def _check_package(self, venv_python: str, package: str) -> tuple[bool, str]:
        """Check if a Python package is installed in the venv."""
        try:
            r = subprocess.run(
                [venv_python, "-c", f"import {package}; print('OK')"],
                capture_output=True, text=True, timeout=30,
            )
            return r.returncode == 0, r.stderr.strip()
        except Exception as e:
            return False, str(e)

    def _pip_install(self, venv_python: str, package: str) -> tuple[bool, str]:
        """Install a package using pip in the venv."""
        try:
            r = subprocess.run(
                [venv_python, "-m", "pip", "install", package],
                capture_output=True, text=True, timeout=300,
                env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                     "PYTHONUNBUFFERED": "1"},
            )
            if r.returncode == 0:
                return True, f"{package} installed"
            last_line = r.stderr.strip().split("\n")[-1] if r.stderr else "unknown"
            return False, last_line[:200]
        except subprocess.TimeoutExpired:
            return False, f"pip install {package} 超时"
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _run_in_venv(self, target: Path, venv_python: str, command: str,
                     timeout: int) -> dict:
        """Execute a command inside the venv."""
        # If command is a full python call, extract script + args
        # If command uses bash/sh, run it with bash
        result = {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "command": command,
        }

        try:
            if command.startswith("bash "):
                # Shell command: run with bash
                shell_cmd = command  # "bash script.sh"
                proc = subprocess.run(
                    shell_cmd.split(),
                    capture_output=True, text=True, timeout=timeout,
                    cwd=str(target),
                    env={
                        **os.environ,
                        "VIRTUAL_ENV": str(target / self.VENV_DIR),
                        "PATH": self._venv_path_env(target),
                        "PYTHONUNBUFFERED": "1",
                    },
                )
            else:
                # Python command or raw command
                if command.startswith(venv_python):
                    parts = command.split()
                else:
                    parts = command.split()

                proc = subprocess.run(
                    parts,
                    capture_output=True, text=True, timeout=timeout,
                    cwd=str(target),
                    env={
                        **os.environ,
                        "VIRTUAL_ENV": str(target / self.VENV_DIR),
                        "PATH": self._venv_path_env(target),
                        "PYTHONUNBUFFERED": "1",
                    },
                )

            result["exit_code"] = proc.returncode
            result["stdout"] = proc.stdout
            result["stderr"] = proc.stderr

            if proc.returncode == 0:
                result["success"] = True
            else:
                result["success"] = False

        except subprocess.TimeoutExpired:
            result["stderr"] = f"执行超时 ({timeout}s)"
        except FileNotFoundError as e:
            result["stderr"] = f"命令未找到: {e}"
        except Exception as e:
            result["stderr"] = f"执行异常: {e}"

        return result

    def _venv_path_env(self, target: Path) -> str:
        """Build PATH that prioritizes venv binaries."""
        venv_bin = target / self.VENV_DIR / ("Scripts" if sys.platform == "win32" else "bin")
        return f"{venv_bin}{os.pathsep}{os.environ.get('PATH', '')}"

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _build_output(self, target: Path, analysis: dict, command: str,
                      cmd_source: str, exec_result: dict, venv_python: str) -> str:
        lines = []
        status = "成功" if exec_result["success"] else "失败"
        lines.append(f"执行{status}!")
        lines.append(f"仓库: {target.name}")
        lines.append(f"路径: {target}")
        lines.append(f"Python: {venv_python}")
        lines.append(f"命令来源: {cmd_source}")
        lines.append(f"命令: {command}")
        lines.append(f"退出码: {exec_result['exit_code']}")
        lines.append("")

        # Analysis summary
        if analysis["readme_summary"]:
            lines.append("--- 项目分析 ---")
            lines.append(analysis["readme_summary"])
            lines.append(f"框架: {analysis['framework']}")
            if analysis["entry_files"]:
                lines.append(f"入口文件: {', '.join(analysis['entry_files'][:5])}")
            if analysis["usage_commands"]:
                lines.append(f"README中发现的命令: {analysis['usage_commands'][0]}")
            lines.append("")

        # Success indicators from README
        if analysis["success_indicators"]:
            lines.append("--- 预期成功指标 ---")
            for ind in analysis["success_indicators"]:
                lines.append(f"  {ind}")
            lines.append("")

        # Output
        stdout = exec_result.get("stdout", "")
        stderr = exec_result.get("stderr", "")

        if stdout:
            lines.append("--- stdout ---")
            # Truncate very long output
            if len(stdout) > 3000:
                lines.append(stdout[:3000])
                lines.append(f"... (输出被截断，完整长度: {len(stdout)} 字符)")
            else:
                lines.append(stdout)

        if stderr:
            lines.append("--- stderr ---")
            if len(stderr) > 1500:
                lines.append(stderr[:1500])
                lines.append(f"... (stderr 被截断，完整长度: {len(stderr)} 字符)")
            else:
                lines.append(stderr)

        if not exec_result["success"]:
            lines.append("")
            lines.append("--- 故障排查建议 ---")
            if "ModuleNotFoundError" in stderr or "No module named" in stderr:
                mod = re.search(r"No module named ['\"]?([\w.]+)", stderr)
                if mod:
                    lines.append(f"  缺少模块: {mod.group(1)}")
                    lines.append(f"  尝试: {venv_python} -m pip install {mod.group(1)}")
            elif "FileNotFoundError" in stderr:
                lines.append("  未找到所需文件，请检查数据文件或路径是否正确。")
            elif "CUDA" in stderr or "cuda" in stderr:
                lines.append("  CUDA相关错误，可能需要安装GPU驱动或使用CPU模式。")
            elif "timeout" in stderr.lower():
                lines.append(f"  执行超时，可尝试增加 timeout 参数或减少数据量。")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers (shared pattern with setup_tool)
    # ------------------------------------------------------------------

    def _list_workspace_repos(self) -> list[Path]:
        if not self.workspace_dir.exists():
            return []
        repos = []
        for p in self.workspace_dir.iterdir():
            if p.is_dir() and (p / ".git").exists():
                repos.append(p)
        return sorted(repos, key=lambda p: p.name)
