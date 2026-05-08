"""
ErrorHandlerTool — operates outside the planner to handle errors without replanning.
Called by the orchestrator BEFORE reflection when a step fails.

Handles: import_error, cmd_not_found, pip_failed, missing_file, venv_failed,
         no_entry_point, missing_requirements.

Returns whether the error was fixed, a description of the fix, and optionally
updated step context (e.g. corrected command).
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


VENV_DIR = ".venv"

# Known fix strategies keyed by error_type
FIX_STRATEGIES = [
    "import_error",      # pip install missing module
    "pip_failed",        # retry pip install with different flags
    "cmd_not_found",     # search for alternative entry files
    "no_entry_point",    # search for any .py/.ipynb to suggest
    "missing_file",      # check data dir, look for file
    "venv_failed",       # recreate venv
    "missing_requirements",  # try setup.py / pyproject.toml
]


class ErrorHandlerTool(BaseTool):
    name = "error_handler_tool"
    description = (
        "处理执行过程中出现的错误，尝试自动修复。此工具在规划器外部运行，"
        "修复成功后返回原计划步骤继续执行。"
        "参数: error(错误信息), error_type(错误类型), "
        "repo_name(仓库名), repo_path(仓库路径，可选), "
        "venv_python(虚拟环境Python路径，可选)"
    )

    def __init__(self):
        self._log = get_logger("error_handler")

    @property
    def workspace_dir(self) -> Path:
        return Path(get_config().agent.workspace_dir).resolve()

    def execute(self, error: str = "", error_type: str = "unknown",
                repo_name: str = "", repo_path: str = "",
                venv_python: str = "", **kwargs) -> ToolResult:
        self._log.info(f"Handling error [{error_type}]: {error[:120]}")

        # Resolve the target repo
        target = self._resolve_target(repo_path, repo_name)
        if target is None:
            return self._fail(
                "无法确定仓库路径，请指定 repo_name 或 repo_path。",
                fixed=False,
            )

        if not venv_python:
            venv_python = self._find_venv_python(target)

        # Dispatch to the right handler
        handler = getattr(self, f"_handle_{error_type}", None)
        if handler:
            return handler(error, target, venv_python, **kwargs)
        else:
            # Try to classify from error message
            return self._handle_unknown(error, target, venv_python)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_import_error(self, error: str, target: Path,
                             venv_python: Optional[str], **kwargs) -> ToolResult:
        """Extract missing module name, pip install it."""
        mod_match = re.search(r"No module named ['\"]?([\w.]+)", error)
        if not mod_match:
            return self._fail("无法从错误信息中提取缺失的模块名", fixed=False)

        module = mod_match.group(1)
        # Normalize: import names may differ from pip names
        pip_name = self._import_to_pip(module)

        if not venv_python:
            return self._fail(f"venv Python 不可用，无法安装 {pip_name}", fixed=False)

        self._log.info(f"Installing missing package: {pip_name} (import: {module})")
        ok, msg = self._pip_install(venv_python, pip_name)

        if ok:
            return self._ok(
                output=f"已安装缺失的依赖: {pip_name}",
                fixed=True,
                action=f"pip install {pip_name}",
                detail=msg,
            )
        else:
            # Try alternative package names
            for alt in self._alternatives(module):
                self._log.info(f"Trying alternative: {alt}")
                ok2, msg2 = self._pip_install(venv_python, alt)
                if ok2:
                    return self._ok(
                        output=f"已安装替代依赖: {alt}",
                        fixed=True,
                        action=f"pip install {alt}",
                        detail=msg2,
                    )
            return self._fail(
                f"无法安装 {pip_name}: {msg}",
                fixed=False,
                attempted=f"pip install {pip_name}",
            )

    def _handle_pip_failed(self, error: str, target: Path,
                           venv_python: Optional[str], **kwargs) -> ToolResult:
        """Retry pip install with different options."""
        if not venv_python:
            return self._fail("venv Python 不可用，无法重试安装", fixed=False)

        # Try upgrading pip first
        self._log.info("Upgrading pip and retrying...")
        self._pip_install(venv_python, "pip", upgrade=True)

        # If there's a specific package mentioned, try individual install
        pkg_match = re.search(r'(?:install|uninstall)\s+(\S+)', error)
        if pkg_match:
            pkg = pkg_match.group(1).rstrip(".,;:")
            ok, msg = self._pip_install(venv_python, pkg, no_deps=False)
            if ok:
                return self._ok(
                    output=f"重试安装 {pkg} 成功",
                    fixed=True,
                    action=f"pip install {pkg}",
                    detail=msg,
                )
            # Try without dependencies
            ok, msg = self._pip_install(venv_python, pkg, no_deps=True)
            if ok:
                return self._ok(
                    output=f"重试安装 {pkg} (--no-deps) 成功",
                    fixed=True,
                    action=f"pip install --no-deps {pkg}",
                    detail=msg,
                )

        return self._fail(
            "pip 安装失败，可能需要手动检查依赖兼容性",
            fixed=False,
        )

    def _handle_cmd_not_found(self, error: str, target: Path,
                              venv_python: Optional[str], **kwargs) -> ToolResult:
        """Search for alternative entry files in the repo."""
        entry_files = self._find_entry_files(target)

        if not entry_files:
            return self._fail(
                "仓库中未找到任何入口文件（.py/.ipynb），需手动指定命令",
                fixed=False,
            )

        # Build suggested commands
        suggestions = []
        for f in entry_files[:5]:
            if f.endswith(".ipynb"):
                output_name = Path(f).stem + "_output.ipynb"
                cmd = (
                    f"{venv_python} -m jupyter nbconvert "
                    f"--execute --to notebook "
                    f"--ExecutePreprocessor.timeout=600 "
                    f"--output {output_name} {f}"
                )
            else:
                cmd = f"{venv_python} {f}"
            suggestions.append(cmd)

        return self._ok(
            output=f"发现 {len(entry_files)} 个入口文件。建议使用: {suggestions[0]}",
            fixed=True,
            corrected_command=suggestions[0],
            alternatives=suggestions[1:3],
            entry_files=entry_files[:5],
        )

    def _handle_no_entry_point(self, error: str, target: Path,
                               venv_python: Optional[str], **kwargs) -> ToolResult:
        """Same logic as cmd_not_found — find any entry file."""
        return self._handle_cmd_not_found(error, target, venv_python, **kwargs)

    def _handle_missing_file(self, error: str, target: Path,
                             venv_python: Optional[str], **kwargs) -> ToolResult:
        """Check for data directories and suggest paths."""
        # Extract missing filename
        file_match = re.search(r"No such file.*?['\"]?([^'\"]+)['\"]?", error)
        filename = file_match.group(1).strip() if file_match else ""

        if filename:
            # Try to locate the file in the repo
            found = list(target.rglob(Path(filename).name))[:5]
            if found:
                rel_paths = [str(f.relative_to(target)) for f in found]
                return self._ok(
                    output=f"找到 {filename} 的可能位置: {', '.join(rel_paths)}",
                    fixed=True,
                    found_paths=rel_paths,
                )

        # Check for data/ directory
        data_dirs = [d for d in target.iterdir()
                     if d.is_dir() and d.name.lower() in ("data", "datasets", "dataset", "input", "output")]
        if data_dirs:
            return self._ok(
                output=f"检测到数据目录: {', '.join(d.name for d in data_dirs)}。请检查数据文件是否完整。",
                fixed=False,
                data_dirs=[d.name for d in data_dirs],
            )

        return self._fail(
            "未找到缺失文件，可能需从外部下载数据",
            fixed=False,
        )

    def _handle_venv_failed(self, error: str, target: Path,
                            venv_python: Optional[str], **kwargs) -> ToolResult:
        """Try to recreate the venv."""
        import shutil
        venv_path = target / VENV_DIR

        if venv_path.exists():
            self._log.info(f"Removing broken venv: {venv_path}")
            shutil.rmtree(str(venv_path), ignore_errors=True)

        python_exe = sys.executable
        self._log.info(f"Recreating venv with {python_exe}")
        try:
            r = subprocess.run(
                [python_exe, "-m", "venv", str(venv_path)],
                capture_output=True, text=True, timeout=120,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            if r.returncode == 0:
                new_python = _find_venv_python_static(target)
                return self._ok(
                    output=f"虚拟环境已重新创建: {venv_path}",
                    fixed=True,
                    venv_python=str(new_python) if new_python else "",
                )
            return self._fail(f"重新创建 venv 失败: {r.stderr[:200]}", fixed=False)
        except Exception as e:
            return self._fail(f"重新创建 venv 异常: {e}", fixed=False)

    def _handle_missing_requirements(self, error: str, target: Path,
                                     venv_python: Optional[str], **kwargs) -> ToolResult:
        """Try setup.py / pyproject.toml install."""
        if not venv_python:
            return self._fail("venv Python 不可用", fixed=False)

        for setup_file in ("setup.py", "pyproject.toml"):
            if (target / setup_file).exists():
                ok, msg = self._pip_install(venv_python, "-e", str(target))
                if ok:
                    return self._ok(
                        output=f"通过 {setup_file} 安装成功",
                        fixed=True,
                        action=f"pip install -e {target}",
                    )
        return self._fail(
            "未找到 setup.py 或 pyproject.toml，无法自动安装",
            fixed=False,
        )

    def _handle_unknown(self, error: str, target: Path,
                        venv_python: Optional[str]) -> ToolResult:
        """Try to auto-detect the error type and apply the right fix."""
        el = error.lower()

        if any(kw in el for kw in ["modulenotfound", "no module named"]):
            return self._handle_import_error(error, target, venv_python)
        elif any(kw in el for kw in ["pip", "安装失败", "install failed"]):
            return self._handle_pip_failed(error, target, venv_python)
        elif any(kw in el for kw in ["命令未找到", "command not found"]):
            return self._handle_cmd_not_found(error, target, venv_python)
        elif any(kw in el for kw in ["filenotfound", "no such file"]):
            return self._handle_missing_file(error, target, venv_python)
        elif any(kw in el for kw in ["venv", "虚拟环境"]):
            return self._handle_venv_failed(error, target, venv_python)

        return self._fail(
            f"无法自动处理此类型错误: {error[:150]}",
            fixed=False,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_target(self, repo_path: str, repo_name: str) -> Optional[Path]:
        if repo_path:
            target = Path(repo_path).resolve()
        elif repo_name:
            target = self.workspace_dir / repo_name
        else:
            repos = self._list_repos()
            if len(repos) == 1:
                target = repos[0]
            elif len(repos) == 0:
                return None
            else:
                return None  # ambiguous
        return target if target.exists() else None

    def _list_repos(self) -> list[Path]:
        if not self.workspace_dir.exists():
            return []
        repos = []
        for p in self.workspace_dir.iterdir():
            if p.is_dir() and (p / ".git").exists():
                repos.append(p)
        return sorted(repos, key=lambda p: p.name)

    @staticmethod
    def _find_venv_python(target: Path) -> Optional[str]:
        venv_path = target / VENV_DIR
        if not venv_path.exists():
            return None
        if sys.platform == "win32":
            py = venv_path / "Scripts" / "python.exe"
        else:
            py = venv_path / "bin" / "python"
        return str(py) if py.exists() else None

    def _find_entry_files(self, target: Path) -> list[str]:
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

    def _pip_install(self, venv_python: str, *args, upgrade: bool = False,
                     no_deps: bool = False) -> tuple[bool, str]:
        cmd = [venv_python, "-m", "pip", "install"]
        if upgrade:
            cmd.append("--upgrade")
        if no_deps:
            cmd.append("--no-deps")
        cmd.extend(args)
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                     "PYTHONUNBUFFERED": "1"},
            )
            if r.returncode == 0:
                return True, r.stdout.strip().split("\n")[-1][:200] if r.stdout else "ok"
            return False, (r.stderr or r.stdout).strip().split("\n")[-1][:200]
        except subprocess.TimeoutExpired:
            return False, "pip 超时"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _import_to_pip(module: str) -> str:
        mapping = {
            "sklearn": "scikit-learn",
            "cv2": "opencv-python",
            "PIL": "pillow",
            "yaml": "pyyaml",
            "bs4": "beautifulsoup4",
            "lightning": "pytorch-lightning",
            "tensorflow": "tensorflow",
            "torch": "torch",
            "numpy": "numpy",
            "pandas": "pandas",
            "matplotlib": "matplotlib",
            "scipy": "scipy",
            "tqdm": "tqdm",
            "wandb": "wandb",
            "einops": "einops",
            "h5py": "h5py",
            "imageio": "imageio",
        }
        return mapping.get(module, module)

    @staticmethod
    def _alternatives(module: str) -> list[str]:
        alts = {
            "cv2": ["opencv-python-headless", "opencv-contrib-python"],
            "PIL": ["pillow", "Pillow"],
            "sklearn": ["scikit-learn"],
            "google.colab": [],  # can't install colab
        }
        return alts.get(module, [])


def _find_venv_python_static(target: Path) -> Optional[str]:
    venv_path = target / VENV_DIR
    if not venv_path.exists():
        return None
    if sys.platform == "win32":
        py = venv_path / "Scripts" / "python.exe"
    else:
        py = venv_path / "bin" / "python"
    return str(py) if py.exists() else None
