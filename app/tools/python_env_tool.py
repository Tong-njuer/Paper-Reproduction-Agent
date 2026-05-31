"""
PythonEnvTool — 环境侦察与 Python 版本管理

职责:
1. 扫描项目文件 (setup.py, requirements.txt, pyproject.toml, README.md) 检测所需的 Python 版本
2. 在系统中查找可用的 Python 解释器
3. 使用正确的 Python 版本创建虚拟环境
4. 清理已创建的虚拟环境

支持 Windows (py launcher) 和 Linux/macOS。
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from app.core.config import get_config
from app.core.logging import get_logger
from app.tools import BaseTool, ToolResult


VENV_DIR = ".venv"
REQUIREMENT_FILES = [
    "requirements.txt", "requirements-dev.txt",
    "setup.py", "setup.cfg", "pyproject.toml",
    "environment.yml", "environment.yaml",
    "Pipfile",
]


class PythonEnvTool(BaseTool):
    name = "python_env_tool"
    description = (
        "环境侦察工具：检测项目所需的 Python 版本，查找系统中可用的 Python 解释器，"
        "使用正确的版本创建虚拟环境。"
        "参数: action(recon|setup|find_python|cleanup), "
        "repo_name(仓库名) 或 repo_path(仓库路径), "
        "python_version(可选，指定目标 Python 版本)"
    )

    def __init__(self):
        self._log = get_logger("python_env")

    @property
    def workspace_dir(self) -> Path:
        return Path(get_config().agent.workspace_dir).resolve()

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def execute(self, action: str = "recon", repo_name: str = "",
                repo_path: str = "", python_version: str = "",
                **kwargs) -> ToolResult:
        # Resolve repo path
        target, err = self._resolve_repo(repo_name, repo_path)
        if err:
            return self._fail(err)

        if action == "recon":
            return self._recon(target)
        elif action == "setup":
            return self._setup(target, python_version)
        elif action == "find_python":
            return self._find_python(target, python_version)
        elif action == "cleanup":
            return self._cleanup_venv(target)
        else:
            return self._fail(f"未知 action: {action}，支持: recon, setup, find_python, cleanup")

    # ------------------------------------------------------------------
    # Action: recon — detect required Python version
    # ------------------------------------------------------------------

    def _recon(self, target: Path) -> ToolResult:
        """Scan project files to detect required Python version."""
        self._log.info(f"Environment recon for: {target.name}")

        # 1. Read all project files
        readme = self._read_file(target, "README.md", 4000)
        req_txt = self._read_file(target, "requirements.txt", 8000)
        setup_py = self._read_file(target, "setup.py", 6000)
        pyproject = self._read_file(target, "pyproject.toml", 6000)
        setup_cfg = self._read_file(target, "setup.cfg", 4000)

        # 2. Detect Python version constraints
        python_version_spec = ""
        python_version = ""

        # Check setup.py: python_requires
        if setup_py:
            m = re.search(
                r'python_requires\s*=\s*["\']([^"\']+)["\']',
                setup_py
            )
            if m:
                python_version_spec = m.group(1)
                python_version = self._extract_min_version(python_version_spec)

        # Check setup.cfg: python_requires
        if not python_version and setup_cfg:
            m = re.search(
                r'python_requires\s*=\s*(\S+)',
                setup_cfg
            )
            if m:
                python_version_spec = m.group(1)
                python_version = self._extract_min_version(python_version_spec)

        # Check pyproject.toml: requires-python
        if not python_version and pyproject:
            m = re.search(
                r'requires-python\s*=\s*["\']([^"\']+)["\']',
                pyproject
            )
            if m:
                python_version_spec = m.group(1)
                python_version = self._extract_min_version(python_version_spec)

        # Check README for Python version mentions
        if not python_version and readme:
            m = re.search(
                r'(?:Python|python)\s*(?:version\s*)?(?:>=?|~=)?\s*(\d+\.\d+)',
                readme
            )
            if m:
                python_version = m.group(1)
                python_version_spec = f">={python_version}"

        # Detect frameworks and version requirements from dependencies
        # TensorFlow 1.x → Python 3.7 (TF 1.x only supports up to 3.7)
        # TensorFlow 2.x → Python 3.8+
        # PyTorch 1.x → Python 3.8+
        framework = self._detect_framework(readme, req_txt, setup_py, pyproject)
        if not python_version:
            # Check if requirements include tensorflow 1.x (implies Python 3.7)
            all_text = " ".join([req_txt or "", setup_py or "", pyproject or "", readme or ""]).lower()
            # TensorFlow 1.x: look for "tensorflow==1." or "tensorflow>=1.,<2" patterns
            if re.search(r'tensorflow[\s\-]*(?:==|>=|~=)\s*1\.', all_text):
                python_version = "3.7"
                python_version_spec = ">=3.7, <3.8"
                self._log.info("Detected TensorFlow 1.x dependency → Python 3.7 required")
            # Also check for explicit upper bound on Python
            elif not python_version:
                m = re.search(r'python_requires\s*=\s*["\'][^"\']*?(?:<|<=)\s*(\d+\.\d+)',
                              setup_py or "")
                if m:
                    python_version = m.group(1)
                    python_version_spec = f"<={python_version}"

        # 3. Find available Python interpreters
        available_pythons = self._list_available_python_versions()

        # 4. Check if the existing venv is suitable
        existing_venv_python = self._get_venv_python_version(target)
        venv_status = "not_exists"
        if existing_venv_python:
            if not python_version or existing_venv_python.startswith(python_version):
                venv_status = "ok"
            else:
                venv_status = f"version_mismatch (has {existing_venv_python}, need {python_version})"

        # 5. Build output
        lines = [
            f"## 环境侦察报告: {target.name}",
            f"",
            f"### Python 版本要求",
        ]

        if python_version:
            lines.append(f"- 所需 Python 版本: {python_version_spec} (最小值: {python_version})")
        else:
            lines.append(f"- 未检测到明确的 Python 版本要求，使用系统默认版本")
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
            python_version_spec = f">={python_version}"

        lines.extend([
            f"",
            f"### 可用 Python 解释器",
        ])
        if available_pythons:
            lines.append(f"- 系统已安装的 Python 版本:")
            for ver in available_pythons:
                marker = " ← 推荐" if ver.startswith(python_version) else ""
                lines.append(f"  - Python {ver}{marker}")
        else:
            lines.append(f"- 系统 Python: {sys.executable} ({sys.version})")
            lines.append(f"- 未检测到 py launcher，使用当前 Python")

        if framework:
            lines.append(f"- 检测到的框架: {framework}")

        lines.extend([
            f"",
            f"### 虚拟环境状态",
        ])
        if venv_status == "ok":
            lines.append(f"- 虚拟环境已存在且版本匹配: {existing_venv_python}")
        elif venv_status.startswith("version_mismatch"):
            lines.append(f"- ⚠️ {venv_status}")
            lines.append(f"- 建议使用 `action=cleanup` 清除旧环境后重新创建")
        else:
            lines.append(f"- 虚拟环境不存在，需要创建")

        lines.extend([
            f"",
            f"### 建议操作",
        ])
        if venv_status == "ok":
            lines.append(f"- 无需操作，虚拟环境已就绪")
            lines.append(f"- 可直接使用 execute_session_tool 开始执行")
        elif python_version:
            # Find if we have a matching interpreter
            matching = [v for v in available_pythons if v.startswith(python_version)]
            if matching:
                lines.append(f"- 使用 `action=setup` 创建虚拟环境（将使用 Python {matching[0]}）")
            else:
                lines.append(f"- 项目需要 Python {python_version}，但系统中未找到匹配版本")
                lines.append(f"- 请安装 Python {python_version} 后再试，或使用 `action=find_python` 查看更多信息")
        else:
            lines.append(f"- 使用 `action=setup` 创建虚拟环境（使用系统默认 Python）")

        output = "\n".join(lines)
        return self._ok(
            output=output,
            repo_name=target.name,
            local_path=str(target),
            python_version=python_version,
            python_version_spec=python_version_spec,
            available_pythons=available_pythons,
            venv_status=venv_status,
            framework=framework,
        )

    # ------------------------------------------------------------------
    # Action: setup — create venv with the right Python version
    # ------------------------------------------------------------------

    def _setup(self, target: Path, python_version: str = "") -> ToolResult:
        """Set up the virtual environment with the correct Python version."""
        self._log.info(f"Setting up venv for: {target.name}")

        # If no version specified, run recon first
        if not python_version:
            recon_result = self._recon(target)
            py_ver = recon_result.metadata.get("python_version", "")
            if py_ver:
                python_version = py_ver

        # Find the right Python interpreter
        python_exe = self._resolve_python_executable(python_version)
        if not python_exe:
            msg = (
                f"无法找到 Python {python_version or '合适版本'} 的解释器。\n"
                f"请先安装所需的 Python 版本，或使用 python_env_tool action=find_python 查看可用版本。"
            )
            return self._fail(msg, repo_name=target.name, local_path=str(target))

        # Check if venv already exists
        venv_path = target / VENV_DIR
        if venv_path.exists():
            existing_ver = self._get_venv_python_version(target)
            if existing_ver:
                if not python_version or existing_ver.startswith(python_version):
                    self._log.info(f"Venv already exists with Python {existing_ver}, skipping")
                    return self._ok(
                        output=f"虚拟环境已存在 (Python {existing_ver})，跳过创建。",
                        venv_path=str(venv_path),
                        python_path=str(venv_path / self._venv_python_bin()),
                        python_version=existing_ver,
                    )
                else:
                    self._log.info(
                        f"Venv version mismatch (has {existing_ver}, "
                        f"need {python_version}), removing old venv"
                    )
                    shutil.rmtree(venv_path)
            else:
                # venv exists but can't read version — treat as broken, recreate
                self._log.warning(
                    f"Venv exists but unreadable, removing and recreating"
                )
                shutil.rmtree(venv_path)

        # Create venv
        self._log.info(f"Creating venv with: {python_exe}")
        try:
            result = subprocess.run(
                [python_exe, "-m", "venv", str(venv_path)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                # Try with virtualenv as fallback
                self._log.warning(f"venv module failed, trying virtualenv: {result.stderr[:200]}")
                result = subprocess.run(
                    [python_exe, "-m", "virtualenv", str(venv_path)],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    return self._fail(
                        f"虚拟环境创建失败:\n"
                        f"  Python: {python_exe}\n"
                        f"  命令: {python_exe} -m venv {venv_path}\n"
                        f"  错误: {result.stderr[:500]}",
                        repo_name=target.name, local_path=str(target),
                    )
        except subprocess.TimeoutExpired:
            return self._fail(
                f"虚拟环境创建超时 (120s): {python_exe} -m venv {venv_path}",
                repo_name=target.name, local_path=str(target),
            )
        except FileNotFoundError:
            return self._fail(
                f"Python 解释器未找到: {python_exe}",
                repo_name=target.name, local_path=str(target),
            )

        # Verify venv
        venv_python = str(venv_path / self._venv_python_bin())
        if not Path(venv_python).exists():
            return self._fail(
                f"虚拟环境创建后 Python 解释器未找到: {venv_python}",
                repo_name=target.name, local_path=str(target),
            )

        # Get created Python version
        try:
            ver_result = subprocess.run(
                [venv_python, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            created_version = ver_result.stdout.strip() or ver_result.stderr.strip()
        except Exception:
            created_version = python_version

        self._log.info(f"Venv created successfully: {created_version}")
        return self._ok(
            output=(
                f"✅ 虚拟环境创建成功\n"
                f"  - 位置: {venv_path}\n"
                f"  - Python: {created_version}\n"
                f"  - 解释器: {venv_python}"
            ),
            venv_path=str(venv_path),
            python_path=venv_python,
            python_version=created_version,
            repo_name=target.name,
            local_path=str(target),
        )

    # ------------------------------------------------------------------
    # Action: find_python — list available Python interpreters
    # ------------------------------------------------------------------

    def _find_python(self, target: Path, python_version: str = "") -> ToolResult:
        """Find available Python interpreters on the system."""
        available = self._list_available_python_versions()
        lines = [
            "## 可用 Python 解释器",
            "",
        ]

        if not available:
            lines.append(f"当前 Python: {sys.executable}")
            lines.append(f"版本: {sys.version}")
            lines.append("")
            lines.append("提示: 未检测到 py launcher，可以使用以下命令安装其他 Python 版本:")
            lines.append("  - Windows: 从 python.org 下载安装")
            lines.append("  - 或安装 pyenv-win: `pip install pyenv-win`")
        else:
            lines.append(f"{'版本':<12} {'路径':<50}")
            lines.append("-" * 62)
            for ver in sorted(set(available), reverse=True):
                exe = self._find_python_for_version(ver)
                path = exe if exe else "(未找到)"
                marker = " ← 项目需要" if python_version and ver.startswith(python_version) else ""
                lines.append(f"{ver:<12} {path:<50}{marker}")

        if python_version:
            matching = [v for v in available if v.startswith(python_version)]
            if matching:
                lines.append(f"\n✅ 找到匹配 Python {python_version} 的版本")
            else:
                lines.append(f"\n❌ 未找到匹配 Python {python_version} 的版本")
                lines.append(f"请安装 Python {python_version} 后再试。")

        return self._ok(
            output="\n".join(lines),
            available_pythons=available,
        )

    # ------------------------------------------------------------------
    # Action: cleanup — remove venv
    # ------------------------------------------------------------------

    def _cleanup_venv(self, target: Path) -> ToolResult:
        """Remove the virtual environment from a repository."""
        venv_path = target / VENV_DIR
        if not venv_path.exists():
            return self._ok(
                output=f"虚拟环境不存在 ({venv_path})，无需清理。",
                repo_name=target.name,
            )

        # Check if it's actually a venv (not just a directory named .venv)
        venv_marker = venv_path / "pyvenv.cfg"
        if not venv_marker.exists():
            return self._fail(
                f"'{venv_path}' 不是有效的虚拟环境（未找到 pyvenv.cfg），拒绝删除。"
            )

        try:
            size = self._dir_size(venv_path)
            shutil.rmtree(venv_path)
            return self._ok(
                output=(
                    f"已删除虚拟环境: {venv_path}\n"
                    f"释放空间: {self._fmt_size(size)}"
                ),
                repo_name=target.name,
                freed_size=size,
            )
        except Exception as e:
            return self._fail(f"删除虚拟环境失败: {e}", repo_name=target.name)

    # ------------------------------------------------------------------
    # Helpers — Python version detection
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_min_version(spec: str) -> str:
        """Extract minimum version from a PEP 440 specifier like '>=3.8, <4.0'."""
        m = re.search(r'(?:>=?|~=|==)\s*(\d+\.\d+)', spec)
        if m:
            return m.group(1)
        # Just a bare version number
        m = re.search(r'(\d+\.\d+)', spec)
        if m:
            return m.group(1)
        return ""

    def _list_available_python_versions(self) -> list:
        """List all available Python versions on this system.

        Uses `py --list` on Windows, `python3 --version` etc. on Linux/macOS.
        """
        versions = []

        # Strategy 1: Windows py launcher
        if sys.platform == "win32":
            try:
                result = subprocess.run(
                    ["py", "--list"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        m = re.search(r'[-*]?\s*(\d+\.\d+)', line)
                        if m:
                            ver = m.group(1)
                            if ver not in versions:
                                versions.append(ver)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        # Strategy 2: Check common Python executables
        common_names = []
        if sys.platform == "win32":
            for major in range(3, 13):
                for minor in range(21, -1, -1):
                    common_names.append(f"python3.{minor}")
                    common_names.append(f"python{major}.{minor}")
            common_names = list(dict.fromkeys(common_names))  # deduplicate preserving order
        else:
            # Linux/macOS: check python3.x
            for minor in range(21, -1, -1):
                common_names.append(f"python3.{minor}")

        for name in common_names:
            try:
                result = subprocess.run(
                    [name, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    ver_str = result.stdout.strip() or result.stderr.strip()
                    m = re.search(r'(\d+\.\d+)', ver_str)
                    if m:
                        ver = m.group(1)
                        if ver not in versions:
                            versions.append(ver)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        # Strategy 3: Current Python
        current_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        if current_ver not in versions:
            versions.append(current_ver)

        return sorted(versions, key=lambda v: tuple(map(int, v.split("."))), reverse=True)

    def _resolve_python_executable(self, python_version: str = "") -> Optional[str]:
        """Find the system Python executable for the given version.

        Priority:
        1. Configured PYTHON_EXECUTABLE from env (for Docker where Python 3.7 is at /usr/bin/python3.7)
        2. Specific version match via `python3.X` / `py -X.Y`
        3. Current Python (if compatible)
        4. Common Python names
        """
        # Priority 1: configured python_executable from env (PYTHON_EXECUTABLE)
        configured = get_config().agent.python_executable
        if configured:
            configured_path = Path(configured)
            if configured_path.exists():
                if not python_version or self._is_python_suitable(configured, python_version):
                    self._log.info(f"Using configured python_executable: {configured}")
                    return configured
                # Version mismatch — see if the configured Python is actually
                # the version we need (the Dockerfile sets PYTHON_EXECUTABLE
                # which may be Python 3.7, but we need to verify)

        if python_version:
            # Priority 2: find specific version
            exe = self._find_python_for_version(python_version)
            if exe:
                return exe
            # Also check if configured python matches the requested version
            if configured and self._is_python_suitable(configured, python_version):
                return configured

        # Priority 3: current Python
        if self._is_python_suitable(sys.executable, python_version):
            return sys.executable

        # Priority 4: try common names
        for minor in range(21, -1, -1):
            name = f"python3.{minor}" if sys.platform != "win32" else f"python{minor}"
            try:
                result = subprocess.run(
                    [name, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    return name
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        return None

    def _find_python_for_version(self, version: str) -> Optional[str]:
        """Find a Python executable path matching the given version."""
        # Windows: py -X.Y
        if sys.platform == "win32":
            try:
                result = subprocess.run(
                    ["py", f"-{version}", "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    # Get the executable path
                    result2 = subprocess.run(
                        ["py", f"-{version}", "-c", "import sys; print(sys.executable)"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if result2.returncode == 0:
                        path = result2.stdout.strip()
                        if Path(path).exists():
                            return path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        # Linux/macOS: check common names
        for name in [f"python{version}", f"python{version.split('.')[0]}"]:
            try:
                result = subprocess.run(
                    [name, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    ver_str = result.stdout.strip() or result.stderr.strip()
                    if version in ver_str:
                        # Get path
                        result2 = subprocess.run(
                            ["which", name] if sys.platform != "win32" else ["where", name],
                            capture_output=True, text=True, timeout=5,
                        )
                        if result2.returncode == 0:
                            return result2.stdout.strip().split("\n")[0]
                        return name
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        return None

    @staticmethod
    def _is_python_suitable(exe: str, required_version: str) -> bool:
        """Check if the given Python executable meets the version requirement."""
        if not required_version:
            return True
        try:
            result = subprocess.run(
                [exe, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                ver_str = result.stdout.strip() or result.stderr.strip()
                return required_version in ver_str
        except Exception:
            pass
        return False

    def _get_venv_python_version(self, target: Path) -> str:
        """Get the Python version of an existing venv."""
        venv_python = target / VENV_DIR / self._venv_python_bin()
        if not venv_python.exists():
            return ""
        try:
            result = subprocess.run(
                [str(venv_python), "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                ver_str = result.stdout.strip() or result.stderr.strip()
                m = re.search(r'(\d+\.\d+)', ver_str)
                if m:
                    return m.group(1)
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------
    # Helpers — file/system utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _venv_python_bin() -> str:
        """Return the path to python executable inside a venv."""
        if sys.platform == "win32":
            return "Scripts/python.exe"
        return "bin/python"

    @staticmethod
    def _read_file(target: Path, filename: str, max_chars: int = 8000) -> str:
        """Read a file from the target directory, return empty string if not found."""
        p = target / filename
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="ignore")[:max_chars]
            except Exception:
                return ""
        return ""

    @staticmethod
    def _detect_framework(*texts: str) -> str:
        """Detect ML framework from project files."""
        combined = " ".join(t.lower() for t in texts if t)
        for fw in ["PyTorch", "TensorFlow", "JAX", "Keras", "transformers",
                    "diffusers", "scikit-learn", "sklearn", "flax"]:
            if fw.lower() in combined:
                return fw
        return ""

    def _resolve_repo(self, repo_name: str, repo_path: str) -> tuple:
        """Resolve repo path from name or path.

        When multiple repos exist and no name/path is given,
        auto-pick the most recently modified one (by .git mtime).
        Exposes `_pick_most_recent_repo` so orchestrator can get it too.
        """
        if repo_path:
            target = Path(repo_path).resolve()
        elif repo_name:
            target = self.workspace_dir / repo_name
        else:
            repos = self._list_repos()
            if len(repos) == 0:
                return None, "workspace 中没有找到任何仓库。"
            elif len(repos) == 1:
                target = repos[0]
            else:
                # Auto-pick the most recently cloned/used repo
                best = self._pick_most_recent_repo(repos)
                if best:
                    self._log.info(f"Auto-picked most recent repo: {best.name}")
                    target = best
                else:
                    names = "\n".join(f"  - {r.name}" for r in repos)
                    return None, f"workspace 中有多个仓库，请指定 repo_name:\n{names}"

        if not target.exists():
            return None, f"仓库路径不存在: {target}"
        return target, ""

    @staticmethod
    def _pick_most_recent_repo(repos: list) -> Optional[Path]:
        """Among multiple repos, pick the most recently modified one.

        Uses .git HEAD modification time as a proxy for "most recently used".
        Returns None if repos list is empty.
        """
        if not repos:
            return None
        best = None
        best_mtime = 0
        for r in repos:
            git_dir = r / ".git"
            if git_dir.exists():
                try:
                    mtime = git_dir.stat().st_mtime
                    if mtime > best_mtime:
                        best_mtime = mtime
                        best = r
                except OSError:
                    continue
        return best or repos[-1]

    def _list_repos(self) -> list:
        """List all cloned repos in the workspace."""
        ws = self.workspace_dir
        if not ws.exists():
            return []
        return sorted(
            [p for p in ws.iterdir() if p.is_dir() and (p / ".git").exists()],
            key=lambda p: p.name,
        )

    @staticmethod
    def _dir_size(path: Path) -> int:
        """Calculate total size of a directory."""
        total = 0
        try:
            for p in path.rglob("*"):
                if p.is_file():
                    total += p.stat().st_size
        except Exception:
            pass
        return total

    @staticmethod
    def _fmt_size(size: int) -> str:
        """Format byte size to human-readable string."""
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
