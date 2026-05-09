import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger
from app.core.config import get_config
from app.tools import BaseTool, ToolResult


class SetupTool(BaseTool):
    name = "setup_tool"
    description = (
        "阅读仓库源码（README/requirements等）并配置Python虚拟环境。"
        "参数: repo_name(仓库名，在workspace中查找) 或 repo_path(仓库路径)"
    )

    VENV_DIR = ".venv"
    READABLE_FILES = [
        "README.md", "README.rst", "README.txt", "README",
        "requirements.txt", "requirements-dev.txt",
        "setup.py", "setup.cfg", "pyproject.toml",
        "environment.yml", "environment.yaml",
        "Pipfile", "Makefile", "CMakeLists.txt",
        "INSTALL.md", "CONTRIBUTING.md", "BUILD.md",
        "run.sh", "run.py", "main.py", "train.py", "eval.py",
    ]

    def __init__(self):
        self._log = get_logger("setup_tool")

    @property
    def workspace_dir(self) -> Path:
        cfg = get_config()
        return Path(cfg.agent.workspace_dir).resolve()

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def execute(self, repo_name: str = "", repo_path: str = "",
                python: str = "", **kwargs) -> ToolResult:
        # 1. Resolve repo path
        if repo_path:
            target = Path(repo_path).resolve()
        elif repo_name:
            target = self.workspace_dir / repo_name
        else:
            # Try to find any repo in workspace
            repos = self._list_workspace_repos()
            if len(repos) == 0:
                return self._fail(
                    "workspace 中没有找到任何仓库。请先克隆一个仓库，或指定 repo_name/repo_path。"
                )
            elif len(repos) == 1:
                target = repos[0]
                self._log.info(f"Auto-detected single repo: {target.name}")
            else:
                names = "\n".join(f"  - {r.name}" for r in repos)
                return self._fail(
                    f"workspace 中有多个仓库，请指定 repo_name:\n{names}"
                )

        if not target.exists():
            return self._fail(f"仓库路径不存在: {target}")

        self._log.info(f"Setting up environment for: {target}")

        # 2. Read source files
        readme_content = self._read_readme(target)
        requirements = self._find_requirements(target)
        hint_texts = self._read_hint_files(target)

        # 3. Determine reproduction target from README
        repro_target = self._extract_repro_target(readme_content, hint_texts)

        # 4. Create virtual environment
        python_exe = python or self._resolve_python()
        venv_path = target / self.VENV_DIR
        venv_created = self._create_venv(target, venv_path, python_exe)
        if not venv_created:
            return self._fail(
                f"虚拟环境创建失败: {venv_path}",
                repo_name=target.name,
                local_path=str(target),
                readme_summary=repro_target,
            )

        # 5. Install dependencies
        python_venv = self._venv_python(venv_path)
        install_results = self._install_deps(target, venv_path, python_venv, requirements)

        # 6. Verify installation
        verify_results = self._verify_installation(venv_path, python_venv, requirements)

        # 7. Build output
        output = self._build_output(
            target, repro_target, requirements,
            venv_created, install_results, verify_results,
        )

        return self._ok(
            output=output,
            repo_name=target.name,
            local_path=str(target),
            venv_path=str(venv_path),
            repro_target=repro_target,
            requirements=requirements,
            installed_packages=verify_results.get("installed", []),
        )

    # ------------------------------------------------------------------
    # Read source files
    # ------------------------------------------------------------------

    def _read_readme(self, target: Path) -> str:
        for name in ("README.md", "README.rst", "README.txt", "README"):
            p = target / name
            if p.exists():
                content = self._read_text(p, max_chars=8000)
                self._log.info(f"Read {p.name}: {len(content)} chars")
                return content
        self._log.warning(f"No README found in {target}")
        return ""

    def _find_requirements(self, target: Path) -> list[str]:
        """Return list of requirement file paths found."""
        found = []
        for name in ("requirements.txt", "requirements-dev.txt"):
            p = target / name
            if p.exists():
                found.append(str(p))
        # Also check setup.py / pyproject.toml
        for name in ("setup.py", "pyproject.toml"):
            p = target / name
            if p.exists():
                found.append(str(p))
        # Check environment.yml
        for name in ("environment.yml", "environment.yaml"):
            p = target / name
            if p.exists():
                found.append(str(p))
        return found

    def _read_hint_files(self, target: Path) -> dict[str, str]:
        """Read additional hint files: INSTALL, CONTRIBUTING, BUILD, Makefile, etc."""
        hint_names = [
            "INSTALL.md", "INSTALL", "CONTRIBUTING.md", "BUILD.md",
            "Makefile", "CMakeLists.txt", "setup.cfg",
        ]
        hints = {}
        for name in hint_names:
            p = target / name
            if p.exists():
                hints[name] = self._read_text(p, max_chars=3000)
        # Also read the first 100 lines of key Python entry points
        for name in ("setup.py", "pyproject.toml", "run.sh", "run.py", "main.py"):
            p = target / name
            if p.exists() and name not in hints:
                hints[name] = self._read_text(p, max_chars=2000)
        return hints

    # ------------------------------------------------------------------
    # Extract reproduction target from README
    # ------------------------------------------------------------------

    def _extract_repro_target(self, readme: str, hints: dict[str, str]) -> str:
        """Parse README to find what this repo does and how to reproduce."""
        lines = []

        # Try to find paper title / arxiv link
        arxiv_match = re.search(
            r'(?:arxiv\.org/(?:abs|pdf)/|arXiv:)(\d{4}\.\d{4,5})',
            readme, re.I
        )
        if arxiv_match:
            lines.append(f"arXiv: {arxiv_match.group(0)}")

        # Try to find paper title (usually in first heading)
        title_match = re.search(r'^#\s+(.+)$', readme, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
            # Clean up badge clutter
            title = re.sub(r'\[!\[.*?\]\(.*?\)\]\(.*?\)', '', title).strip()
            lines.append(f"项目: {title}")

        # Try to find "Official implementation" or similar
        impl_match = re.search(
            r'(?:Official|官方的?)\s*(?:implementation|实现|code|代码|PyTorch|TensorFlow)',
            readme, re.I
        )
        if impl_match:
            lines.append(f"类型: {impl_match.group(0)}")

        # Try to find Python version requirement
        py_match = re.search(
            r'Python\s*(?:version\s*)?(?:>=?|~=)?\s*(\d+\.\d+)',
            readme, re.I
        )
        if py_match:
            lines.append(f"Python: >={py_match.group(1)}")

        # Try to find installation section
        if re.search(r'#{1,3}\s*(?:Install|安装|Setup|配置|Getting Started|Quick ?Start)', readme, re.I):
            lines.append("安装说明: README中有详细安装指引")

        # Try to find framework
        for fw in ["PyTorch", "TensorFlow", "JAX", "Keras", "transformers", "diffusers"]:
            if fw.lower() in readme.lower():
                lines.append(f"框架: {fw}")
                break

        return "\n".join(lines) if lines else "未从README中提取到明确的复现目标"

    # ------------------------------------------------------------------
    # Virtual environment
    # ------------------------------------------------------------------

    def _create_venv(self, target: Path, venv_path: Path, python_exe: str) -> bool:
        if venv_path.exists():
            self._log.info(f"venv already exists at {venv_path}, reusing")
            # Verify it's functional
            py = self._venv_python(venv_path)
            if py and self._check_pip_works(py):
                return True
            self._log.warning("Existing venv is broken, recreating...")
            self._rmdir(venv_path)

        self._log.info(f"Creating venv at {venv_path} using {python_exe}")
        try:
            r = subprocess.run(
                [python_exe, "-m", "venv", str(venv_path)],
                capture_output=True, text=True, timeout=120,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            if r.returncode != 0:
                self._log.error(f"venv creation failed: {r.stderr}")
                return False
            self._log.info("venv created successfully")
            return True
        except subprocess.TimeoutExpired:
            self._log.error("venv creation timed out")
            return False
        except Exception as e:
            self._log.error(f"venv creation error: {e}")
            return False

    def _check_pip_works(self, python_venv: str) -> bool:
        try:
            r = subprocess.run(
                [python_venv, "-m", "pip", "--version"],
                capture_output=True, text=True, timeout=15,
            )
            return r.returncode == 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Install dependencies
    # ------------------------------------------------------------------

    def _install_deps(self, target: Path, venv_path: Path,
                      python_venv: Optional[str], requirements: list[str]) -> dict:
        if not python_venv:
            return {"status": "failed", "error": "venv Python 不可用"}

        results = {"status": "ok", "installed": [], "errors": []}

        # First, upgrade pip itself
        self._log.info("Upgrading pip...")
        self._pip_install(python_venv, ["--upgrade", "pip"], results)

        # Install from requirements.txt files
        req_txt_files = [r for r in requirements if r.endswith(".txt")]
        for req_file in req_txt_files:
            self._log.info(f"Installing from {req_file}")
            ok = self._pip_install(python_venv, ["-r", req_file], results)
            if not ok:
                results["errors"].append(f"部分依赖从 {Path(req_file).name} 安装失败")
                self._install_individually(python_venv, req_file, results)

        # Install from setup.py / pyproject.toml (editable install)
        for setup_file in requirements:
            if setup_file.endswith(("setup.py", "pyproject.toml")) and req_txt_files:
                setup_dir = str(Path(setup_file).parent)
                self._log.info(f"Installing from {setup_file} (editable)")
                self._pip_install(python_venv, ["-e", setup_dir], results)

        # If no requirements files at all, try editable install from repo root
        if not requirements:
            self._log.info("No requirements files found, trying editable install from root")
            ok = self._pip_install(python_venv, ["-e", str(target)], results)
            if not ok:
                if (target / "setup.py").exists() or (target / "pyproject.toml").exists():
                    self._pip_install(python_venv, ["-e", str(target)], results)
                else:
                    results["errors"].append(
                        "未找到 requirements.txt/setup.py/pyproject.toml，"
                        "无法自动安装依赖。请手动安装。"
                    )

        return results

    def _pip_install(self, python_venv: str, args: list[str],
                     results: dict) -> bool:
        cmd = [python_venv, "-m", "pip", "install"] + args
        cmd_label = " ".join(args)[:120]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
                env={**os.environ, "PYTHONUNBUFFERED": "1",
                     "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
            )
            for line in r.stdout.splitlines():
                if "Successfully installed" in line:
                    pkgs = line.split("Successfully installed")[-1].strip()
                    results["installed"].extend(
                        p.strip() for p in pkgs.split(",") if p.strip()
                    )
                elif "Requirement already satisfied" in line:
                    pkg = line.split("Requirement already satisfied:")[-1].strip()
                    pkg_name = pkg.split()[0] if pkg else ""
                    if pkg_name and pkg_name not in results.get("installed", []):
                        results.setdefault("already_satisfied", []).append(pkg_name)

            # Save pip output for user visibility
            pip_outputs: list[dict] = results.setdefault("pip_outputs", [])
            pip_outputs.append({
                "label": cmd_label,
                "ok": r.returncode == 0,
                "stdout_tail": (
                    r.stdout.strip().split("\n")[-20:]
                    if r.stdout.strip() else []
                ),
                "stderr_tail": (
                    r.stderr.strip().split("\n")[-10:]
                    if r.stderr.strip() else []
                ),
            })

            if r.returncode != 0:
                last_line = r.stderr.strip().split("\n")[-1] if r.stderr else "unknown error"
                self._log.warning(f"pip install failed (args={args}): {last_line}")
                results["errors"].append(last_line)
                return False
            return True
        except subprocess.TimeoutExpired:
            results["errors"].append("pip install 超时 (600s)")
            return False
        except Exception as e:
            results["errors"].append(str(e))
            return False

    def _install_individually(self, python_venv: str, req_file: str,
                              results: dict):
        try:
            with open(req_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            return

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            pkg = re.split(r'[<>=!~\[\];]', line)[0].strip()
            if pkg:
                self._pip_install(python_venv, [line], results)

    # ------------------------------------------------------------------
    # Verify installation
    # ------------------------------------------------------------------

    def _verify_installation(self, venv_path: Path, python_venv: Optional[str],
                             requirements: list[str]) -> dict:
        if not python_venv:
            return {"status": "unknown", "error": "venv Python 不可用，无法验证"}

        result = {"status": "ok", "installed": [], "missing": []}

        try:
            r = subprocess.run(
                [python_venv, "-m", "pip", "list", "--format=freeze"],
                capture_output=True, text=True, timeout=30,
            )
            installed = set()
            for line in r.stdout.splitlines():
                if "==" in line:
                    pkg = line.split("==")[0].lower()
                    installed.add(pkg)
            result["installed"] = sorted(installed)
        except Exception as e:
            result["status"] = "partial"
            result["error"] = f"无法获取已安装包列表: {e}"
            return result

        # Check if key packages from requirements can be imported
        key_packages = self._extract_key_packages(requirements)
        python_exe = self._venv_python(venv_path)
        if python_exe and key_packages:
            for pkg in key_packages[:20]:  # Check at most 20
                ok, err = self._try_import(python_exe, pkg)
                if ok:
                    result.setdefault("import_ok", []).append(pkg)
                else:
                    result.setdefault("import_failed", []).append(
                        f"{pkg}: {err}"
                    )

        if result.get("import_failed"):
            result["status"] = "partial"

        return result

    def _extract_key_packages(self, requirements: list[str]) -> list[str]:
        """Extract package names from requirements files."""
        packages = []
        for req_path in requirements:
            if not req_path.endswith(".txt"):
                continue
            try:
                with open(req_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or line.startswith("-"):
                            continue
                        pkg = re.split(r'[<>=!~\[\];]', line)[0].strip()
                        if pkg and pkg not in packages:
                            packages.append(pkg)
            except Exception:
                pass
        return packages

    def _try_import(self, python_exe: str, package: str) -> tuple[bool, str]:
        """Try to import a package using the venv Python."""
        # Map common pip package names to import names
        import_map = {
            "scikit-learn": "sklearn",
            "opencv-python": "cv2",
            "opencv-python-headless": "cv2",
            "pillow": "PIL",
            "python-dateutil": "dateutil",
            "pyyaml": "yaml",
            "beautifulsoup4": "bs4",
            "pytorch-lightning": "lightning",
            "tensorflow-gpu": "tensorflow",
        }
        import_name = import_map.get(package.lower(), package.replace("-", "_"))
        code = f"import {import_name}; print('OK')"
        try:
            r = subprocess.run(
                [python_exe, "-c", code],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0:
                return True, ""
            err = (r.stderr or r.stdout).strip().split("\n")[-1][:150]
            return False, err
        except subprocess.TimeoutExpired:
            return False, "import timed out"
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # Build output
    # ------------------------------------------------------------------

    def _build_output(self, target: Path, repro_target: str,
                      requirements: list[str], venv_ok: bool,
                      install_results: dict, verify_results: dict) -> str:
        lines = [
            f"环境配置完成!",
            f"仓库: {target.name}",
            f"路径: {target}",
            f"",
            f"--- 复现目标 ---",
            f"{repro_target}",
            f"",
            f"--- 虚拟环境 ---",
            f"路径: {target / self.VENV_DIR}",
            f"状态: {'已创建' if venv_ok else '失败'}",
        ]

        if requirements:
            lines.append(f"")
            lines.append(f"--- 依赖文件 ---")
            for r in requirements:
                lines.append(f"  {Path(r).name}")

        installed = install_results.get("installed", [])
        already = install_results.get("already_satisfied", [])
        if installed:
            lines.append(f"")
            lines.append(f"--- 新安装的包 ({len(installed)} 个) ---")
            for pkg in installed[:30]:
                lines.append(f"  [OK] {pkg}")
            if len(installed) > 30:
                lines.append(f"  ... 及其他 {len(installed) - 30} 个")
        if already:
            lines.append(f"")
            lines.append(f"--- 已存在的包 ({len(already)} 个) ---")
            for pkg in already[:10]:
                lines.append(f"  - {pkg}")

        errors = install_results.get("errors", [])
        if errors:
            lines.append(f"")
            lines.append(f"--- 安装警告/错误 ---")
            for e in errors[:5]:
                lines.append(f"  [WARN] {str(e)[:200]}")

        # Show pip install console output
        pip_outputs = install_results.get("pip_outputs", [])
        if pip_outputs:
            lines.append(f"")
            lines.append(f"--- pip 安装输出 ({len(pip_outputs)} 步) ---")
            for po in pip_outputs:
                status = "[OK]" if po["ok"] else "[FAIL]"
                lines.append(f"  {status} pip install {po['label']}")
                for line in po["stdout_tail"]:
                    lines.append(f"    | {line[:200]}")
                for line in po["stderr_tail"]:
                    lines.append(f"    | [stderr] {line[:200]}")

        lines.append(f"")
        lines.append(f"--- 验证结果 ---")
        vstatus = verify_results.get("status", "unknown")
        if vstatus == "ok":
            lines.append(f"  [OK] 环境配置完成，所有依赖已安装")
        else:
            lines.append(f"  [WARN] 环境部分配置完成 (status={vstatus})")

        import_ok = verify_results.get("import_ok", [])
        if import_ok:
            lines.append(f"  可导入的包: {', '.join(import_ok[:15])}")
        import_failed = verify_results.get("import_failed", [])
        if import_failed:
            lines.append(f"  导入失败的包:")
            for f in import_failed[:10]:
                lines.append(f"    [FAIL] {f}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_python() -> str:
        """Resolve Python executable: config > python3.8 > python3 > python > sys.executable."""
        cfg = get_config()
        configured = cfg.agent.python_executable
        if configured:
            resolved = shutil.which(configured)
            if resolved:
                get_logger("setup_tool").info(f"Using configured Python: {resolved}")
                return resolved

        # Try python3.8 explicitly (common for TF 1.x compatibility)
        # shutil.which may not find it in Docker, so also check known paths
        candidates = [
            "python3.7",
            "/usr/bin/python3.7",
            "/usr/local/bin/python3.7",
            "python3.8",
            "/usr/bin/python3.8",
            "/usr/local/bin/python3.8",
            "/opt/python3.8/bin/python3.8",
            "python3.9",
            "/usr/bin/python3.9",
            "/usr/local/bin/python3.9",
            "python3",
            "python",
        ]
        for candidate in candidates:
            resolved = shutil.which(candidate) if "/" not in candidate else candidate
            if resolved and Path(resolved).exists():
                # Verify it actually works
                try:
                    r = subprocess.run(
                        [resolved, "--version"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if r.returncode == 0:
                        version = r.stdout.strip() or r.stderr.strip()
                        get_logger("setup_tool").info(
                            f"Resolved Python: {resolved} ({version})"
                        )
                        return resolved
                except Exception:
                    continue

        get_logger("setup_tool").warning(
            f"No suitable Python found, falling back to {sys.executable}"
        )
        return sys.executable

    def _list_workspace_repos(self) -> list[Path]:
        """List directories in workspace that look like repos (have .git)."""
        if not self.workspace_dir.exists():
            return []
        repos = []
        for p in self.workspace_dir.iterdir():
            if p.is_dir() and (p / ".git").exists():
                repos.append(p)
        return sorted(repos, key=lambda p: p.name)

    @staticmethod
    def _read_text(path: Path, max_chars: int) -> str:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            return content[:max_chars]
        except Exception:
            return ""

    @staticmethod
    def _venv_python(venv_path: Path) -> Optional[str]:
        if sys.platform == "win32":
            py = venv_path / "Scripts" / "python.exe"
        else:
            py = venv_path / "bin" / "python"
        return str(py) if py.exists() else None

    @staticmethod
    def _rmdir(path: Path):
        try:
            shutil.rmtree(str(path), ignore_errors=True)
        except Exception:
            pass
