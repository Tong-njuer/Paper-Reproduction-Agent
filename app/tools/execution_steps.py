"""
Split execution sub-tools that replace the monolithic execute_tool.
These give the planner visibility into each phase of execution:
  1. read_repo_tool  — analyze repo structure & extract README info
  2. plan_run_tool  — determine the exact command to run
  3. run_tool       — execute the command inside the venv
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger
from app.core.config import get_config
from app.tools import BaseTool, ToolResult


# ---------------------------------------------------------------------------
# Shared helpers (extracted from execute_tool / setup_tool)
# ---------------------------------------------------------------------------

VENV_DIR = ".venv"

ENTRY_SCRIPTS = [
    "main.py", "run.py", "train.py", "eval.py", "demo.py",
    "predict.py", "test.py", "infer.py", "inference.py",
    "run.sh", "start.sh",
]
ENTRY_NOTEBOOKS = [
    "main.ipynb", "demo.ipynb", "train.ipynb",
    "denoising.ipynb", "inpainting.ipynb",
    "super_resolution.ipynb", "restoration.ipynb",
]


def _workspace() -> Path:
    return Path(get_config().agent.workspace_dir).resolve()


def _list_repos() -> list[Path]:
    ws = _workspace()
    if not ws.exists():
        return []
    repos = []
    for p in ws.iterdir():
        if p.is_dir() and (p / ".git").exists():
            repos.append(p)
    return sorted(repos, key=lambda p: p.name)


def _resolve_repo(repo_path: str, repo_name: str, log) -> tuple[Optional[Path], str]:
    if repo_path:
        target = Path(repo_path).resolve()
    elif repo_name:
        target = _workspace() / repo_name
    else:
        repos = _list_repos()
        if len(repos) == 0:
            return None, "workspace 中没有找到任何仓库。请先克隆或指定 repo_name/repo_path。"
        elif len(repos) == 1:
            target = repos[0]
            log.info(f"Auto-detected single repo: {target.name}")
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
                return p.read_text(encoding="utf-8", errors="ignore")[:10000]
            except Exception:
                return ""
    return ""


def _venv_path_env(target: Path) -> str:
    venv_bin = target / VENV_DIR / ("Scripts" if sys.platform == "win32" else "bin")
    return f"{venv_bin}{os.pathsep}{os.environ.get('PATH', '')}"


# ---------------------------------------------------------------------------
# ReadRepoTool
# ---------------------------------------------------------------------------

class ReadRepoTool(BaseTool):
    name = "read_repo_tool"
    description = (
        "阅读仓库源码，分析README和入口文件，提取执行所需的关键信息。"
        "参数: repo_name(仓库名) 或 repo_path(仓库路径)"
    )

    def __init__(self):
        self._log = get_logger("read_repo_tool")

    def execute(self, repo_name: str = "", repo_path: str = "",
                **kwargs) -> ToolResult:
        target, err = _resolve_repo(repo_path, repo_name, self._log)
        if err:
            return self._fail(err)

        self._log.info(f"Analyzing repo: {target.name}")

        # Read README
        readme = _read_readme(target)

        # Find entry files
        entry_files = self._find_entry_files(target)

        # Extract usage commands from README
        usage_commands = self._extract_usage_commands(readme)

        # Detect framework
        framework = self._detect_framework(readme)

        # Extract success indicators
        success_indicators = self._extract_success_indicators(readme)

        # Summarize README
        readme_summary = self._summarize_readme(readme)

        # Build output
        output = self._build_output(
            target, readme_summary, framework,
            entry_files, usage_commands, success_indicators,
        )

        return self._ok(
            output=output,
            repo_name=target.name,
            local_path=str(target),
            readme_summary=readme_summary,
            entry_files=entry_files,
            usage_commands=usage_commands,
            framework=framework,
            success_indicators=success_indicators,
        )

    # ------------------------------------------------------------------
    # Analysis methods
    # ------------------------------------------------------------------

    def _find_entry_files(self, target: Path) -> list[str]:
        found = []
        for name in ENTRY_SCRIPTS:
            if (target / name).exists():
                found.append(name)
        for name in ENTRY_NOTEBOOKS:
            if (target / name).exists():
                found.append(name)
        # Any .ipynb in root
        for p in target.glob("*.ipynb"):
            rel = str(p.relative_to(target))
            if rel not in found:
                found.append(rel)
        # One level deep
        for d in target.iterdir():
            if d.is_dir() and not d.name.startswith(".") and d.name != VENV_DIR:
                for name in ENTRY_SCRIPTS:
                    if (d / name).exists():
                        found.append(str((d / name).relative_to(target)))
        return found[:10]

    def _extract_usage_commands(self, readme: str) -> list[str]:
        commands = []
        # Code blocks
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
                elif re.search(r'(?:\./|bash\s+)\S+\.sh', line):
                    commands.append(line)
                elif re.search(r'python3?\s+-m\s+\S+', line):
                    commands.append(line)

        # Inline code `python main.py ...`
        inline = re.findall(r'`([^`]*python[^`]*\.py[^`]*)`', readme)
        for line in inline:
            line = line.strip()
            if "\n" in line:
                continue
            if re.search(r'python3?\s+\S+\.py', line):
                commands.append(line)

        # Deduplicate
        seen = set()
        unique = []
        for c in commands:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique[:10]

    def _detect_framework(self, readme: str) -> str:
        for fw in ["PyTorch", "TensorFlow", "JAX", "Keras", "transformers",
                    "diffusers", "scikit-learn", "sklearn"]:
            if fw.lower() in readme.lower():
                return fw
        return "unknown"

    def _extract_success_indicators(self, readme: str) -> list[str]:
        indicators = []
        output_section = re.search(
            r'(?:output|result|预期|输出|结果).{0,200}```[^\n]*\n(.+?)\n```',
            readme, re.DOTALL | re.I,
        )
        if output_section:
            indicators.append(output_section.group(1).strip()[:500])
        numbers = re.findall(
            r'(?:accuracy|PSNR|SSIM|BLEU|F1|mAP|AUC)[^0-9]*(\d+\.?\d*)',
            readme, re.I,
        )
        for n in numbers[:3]:
            indicators.append(f"Expected metric value: {n}")
        return indicators[:5]

    def _summarize_readme(self, readme: str) -> str:
        lines = []
        title = re.search(r'^#\s+(.+)$', readme, re.MULTILINE)
        if title:
            lines.append(f"项目: {title.group(1).strip()[:100]}")
        para = re.search(r'(?:^|\n\n)([^#\n`][^\n]{50,300})', readme)
        if para:
            lines.append(f"描述: {para.group(1).strip()[:200]}")
        return "\n".join(lines) if lines else "未提取到项目描述"

    def _build_output(self, target: Path, readme_summary: str, framework: str,
                      entry_files: list[str], usage_commands: list[str],
                      success_indicators: list[str]) -> str:
        lines = [
            f"仓库分析完成: {target.name}",
            f"路径: {target}",
            "",
            "--- README摘要 ---",
            readme_summary,
            f"框架: {framework}",
            "",
        ]
        if entry_files:
            lines.append(f"入口文件: {', '.join(entry_files[:8])}")
        if usage_commands:
            lines.append(f"README中发现 {len(usage_commands)} 条可执行命令")
            for c in usage_commands[:3]:
                lines.append(f"  $ {c}")
        if success_indicators:
            lines.append("")
            lines.append("--- 预期成功指标 ---")
            for ind in success_indicators:
                lines.append(f"  - {ind}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# PlanRunTool
# ---------------------------------------------------------------------------

class PlanRunTool(BaseTool):
    name = "plan_run_tool"
    description = (
        "确定执行命令。根据仓库分析结果，确定要在虚拟环境中运行的精确命令。"
        "参数: repo_name(仓库名) 或 repo_path(仓库路径), "
        "command(指定命令，可选), script(指定脚本名，可选)"
    )

    def __init__(self):
        self._log = get_logger("plan_run_tool")

    def execute(self, repo_name: str = "", repo_path: str = "",
                command: str = "", script: str = "",
                timeout: int = 600, **kwargs) -> ToolResult:
        target, err = _resolve_repo(repo_path, repo_name, self._log)
        if err:
            return self._fail(err)

        venv_python = _find_venv_python(target)
        if not venv_python:
            return self._fail(
                f"虚拟环境未找到: {target / VENV_DIR}。请先运行 setup_tool 配置环境。",
                repo_name=target.name,
                local_path=str(target),
            )

        # Re-analyze repo to determine entry point (lightweight, no README re-read needed)
        entry_files = self._find_entry_files(target)

        if command:
            final_cmd = command
            cmd_source = "用户指定"
        elif script:
            final_cmd = f"{venv_python} {script}"
            cmd_source = f"用户指定脚本: {script}"
        elif entry_files:
            best = entry_files[0]
            if best.endswith(".ipynb"):
                final_cmd = self._notebook_command(best, venv_python, target)
                cmd_source = f"自动检测(Jupyter): {best}"
            else:
                final_cmd = f"{venv_python} {best}"
                cmd_source = f"自动检测: {best}"
        else:
            return self._fail(
                "未检测到入口文件（.py/.ipynb）。请使用 command 或 script 参数指定。",
                repo_name=target.name,
                local_path=str(target),
                entry_files_found=[],
            )

        self._log.info(f"Planned command [{cmd_source}]: {final_cmd}")

        output = (
            f"执行计划确定: {target.name}\n"
            f"命令来源: {cmd_source}\n"
            f"命令: {final_cmd}\n"
            f"Python: {venv_python}\n"
            f"超时: {timeout}s"
        )

        return self._ok(
            output=output,
            repo_name=target.name,
            local_path=str(target),
            venv_python=venv_python,
            command=final_cmd,
            cmd_source=cmd_source,
            timeout=timeout,
        )

    def _find_entry_files(self, target: Path) -> list[str]:
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

    def _notebook_command(self, notebook: str, venv_python: str, target: Path) -> str:
        output_name = Path(notebook).stem + "_output.ipynb"
        return (
            f"{venv_python} -m jupyter nbconvert "
            f"--execute --to notebook "
            f"--ExecutePreprocessor.timeout=600 "
            f"--output {output_name} "
            f"{notebook}"
        )


# ---------------------------------------------------------------------------
# RunTool
# ---------------------------------------------------------------------------

class RunTool(BaseTool):
    name = "run_tool"
    description = (
        "在虚拟环境中执行命令并捕获输出。"
        "参数: repo_name(仓库名) 或 repo_path(仓库路径), "
        "command(完整执行命令，必需), timeout(超时秒数，默认600)"
    )

    def __init__(self):
        self._log = get_logger("run_tool")

    def execute(self, repo_name: str = "", repo_path: str = "",
                command: str = "", timeout: int = 600, **kwargs) -> ToolResult:
        if not command:
            return self._fail("必须提供 command 参数。请先运行 plan_run_tool 确定执行命令。")

        target, err = _resolve_repo(repo_path, repo_name, self._log)
        if err:
            return self._fail(err)

        venv_python = _find_venv_python(target)
        if not venv_python:
            return self._fail(
                f"虚拟环境未找到: {target / VENV_DIR}。请先运行 setup_tool 配置环境。",
                repo_name=target.name,
                local_path=str(target),
            )

        self._log.info(f"Executing: {command} (cwd={target})")

        # Ensure required tooling (jupyter for notebooks)
        self._ensure_dependencies(target, venv_python, command)

        # Run in venv
        exec_result = self._run_in_venv(target, venv_python, command, timeout)

        output = self._build_output(target, command, exec_result)

        if exec_result["success"]:
            return self._ok(
                output=output,
                repo_name=target.name,
                local_path=str(target),
                venv_python=venv_python,
                command=command,
                exit_code=exec_result["exit_code"],
                stdout=exec_result["stdout"][:5000],
            )
        else:
            error_summary = (
                f"执行失败 (退出码 {exec_result['exit_code']})\n"
                f"命令: {command}\n"
                f"stderr: {exec_result['stderr'][:1000]}"
            )
            return self._fail(
                error=error_summary,
                repo_name=target.name,
                local_path=str(target),
                venv_python=venv_python,
                command=command,
                exit_code=exec_result["exit_code"],
                stderr=exec_result["stderr"][:2000],
                stdout=exec_result["stdout"][:2000],
            )

    # ------------------------------------------------------------------
    # Dependency assurance
    # ------------------------------------------------------------------

    def _ensure_dependencies(self, target: Path, venv_python: str, command: str):
        needed = []
        if "jupyter" in command or "nbconvert" in command:
            needed.extend(["jupyter", "nbconvert"])

        for pkg in needed:
            ok, _ = self._check_package(venv_python, pkg)
            if not ok:
                self._log.info(f"Missing package: {pkg}, installing...")
                self._pip_install(venv_python, pkg)

    def _check_package(self, venv_python: str, package: str) -> tuple[bool, str]:
        try:
            r = subprocess.run(
                [venv_python, "-c", f"import {package}; print('OK')"],
                capture_output=True, text=True, timeout=30,
            )
            return r.returncode == 0, r.stderr.strip()
        except Exception as e:
            return False, str(e)

    def _pip_install(self, venv_python: str, package: str) -> tuple[bool, str]:
        try:
            r = subprocess.run(
                [venv_python, "-m", "pip", "install", package],
                capture_output=True, text=True, timeout=300,
                env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                     "PYTHONUNBUFFERED": "1"},
            )
            if r.returncode == 0:
                return True, f"{package} installed"
            return False, r.stderr.strip().split("\n")[-1][:200] if r.stderr else "unknown"
        except subprocess.TimeoutExpired:
            return False, f"pip install {package} 超时"
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _run_in_venv(self, target: Path, venv_python: str, command: str,
                     timeout: int) -> dict:
        result = {
            "success": False, "exit_code": -1,
            "stdout": "", "stderr": "", "command": command,
        }

        try:
            if command.startswith("bash "):
                proc = subprocess.run(
                    command.split(),
                    capture_output=True, text=True, timeout=timeout,
                    cwd=str(target),
                    env={
                        **os.environ,
                        "VIRTUAL_ENV": str(target / VENV_DIR),
                        "PATH": _venv_path_env(target),
                        "PYTHONUNBUFFERED": "1",
                    },
                )
            else:
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
                        "VIRTUAL_ENV": str(target / VENV_DIR),
                        "PATH": _venv_path_env(target),
                        "PYTHONUNBUFFERED": "1",
                    },
                )

            result["exit_code"] = proc.returncode
            result["stdout"] = proc.stdout
            result["stderr"] = proc.stderr
            result["success"] = proc.returncode == 0

        except subprocess.TimeoutExpired:
            result["stderr"] = f"执行超时 ({timeout}s)"
        except FileNotFoundError as e:
            result["stderr"] = f"命令未找到: {e}"
        except Exception as e:
            result["stderr"] = f"执行异常: {e}"

        return result

    def _build_output(self, target: Path, command: str,
                      exec_result: dict) -> str:
        status = "成功" if exec_result["success"] else "失败"
        lines = [
            f"执行{status}!",
            f"仓库: {target.name}",
            f"路径: {target}",
            f"命令: {command}",
            f"退出码: {exec_result['exit_code']}",
            "",
        ]

        stdout = exec_result.get("stdout", "")
        stderr = exec_result.get("stderr", "")

        if stdout:
            lines.append("--- stdout ---")
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
                    lines.append(f"  尝试: pip install {mod.group(1)}")
            elif "FileNotFoundError" in stderr:
                lines.append("  未找到所需文件，请检查数据文件或路径是否正确。")
            elif "CUDA" in stderr or "cuda" in stderr:
                lines.append("  CUDA相关错误，可能需要安装GPU驱动或使用CPU模式。")

        return "\n".join(lines)
