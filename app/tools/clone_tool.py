import os
import subprocess
from pathlib import Path

from app.core.logging import get_logger
from app.core.config import get_config
from app.tools import BaseTool, ToolResult


class CloneRepoTool(BaseTool):
    name = "clone_tool"
    description = "克隆Git仓库到工作区。参数: repo_url(仓库地址), branch(分支，默认main)"

    def __init__(self):
        self._log = get_logger("clone_tool")

    @property
    def workspace_dir(self) -> Path:
        cfg = get_config()
        return Path(cfg.agent.workspace_dir).resolve()

    FALLBACK_BRANCHES = ["main", "master"]

    def execute(self, repo_url: str = "", branch: str = "", **kwargs) -> ToolResult:
        if not repo_url:
            return self._fail("repo_url 不能为空")

        repo_name = self._repo_name(repo_url)
        target = self.workspace_dir / repo_name
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        if target.exists():
            self._log.info(f"Repo already exists at {target}, pulling instead")
            return self._pull(target, branch or "main")

        # Determine which branches to try
        branches_to_try = [branch] if branch else []
        default_branch = self._detect_default_branch(repo_url)
        if default_branch and default_branch not in branches_to_try:
            branches_to_try.append(default_branch)
        for fb in self.FALLBACK_BRANCHES:
            if fb not in branches_to_try:
                branches_to_try.append(fb)

        last_error = None
        for attempt, br in enumerate(branches_to_try):
            self._log.info(
                f"Cloning {repo_url} (branch={br}, attempt {attempt+1}/{len(branches_to_try)}) -> {target}"
            )
            result, error = self._clone_attempt(repo_url, br, target)
            if result:
                self._log.info(f"Clone success: {target}")
                return self._build_ok(target, repo_url, br, repo_name)
            last_error = error
            # Clean up failed clone dir before retrying
            if target.exists():
                self._rmdir(target)

        self._log.error(f"All {len(branches_to_try)} branch attempts failed for {repo_url}")
        return self._fail(
            f"克隆失败，尝试了 {len(branches_to_try)} 个分支 ({', '.join(branches_to_try)}) 均未成功。"
            f"最后错误: {last_error}"
        )

    def _clone_attempt(self, repo_url: str, branch: str, target: Path):
        try:
            r = subprocess.run(
                ["git", "clone", "--branch", branch, "--single-branch",
                 "--depth", "1", repo_url, str(target)],
                capture_output=True, text=True, timeout=300,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except subprocess.TimeoutExpired:
            return None, "克隆超时（300s），仓库可能过大或网络不稳定"
        if r.returncode != 0:
            err = r.stderr.strip().split("\n")[-1] if r.stderr else "unknown"
            return None, err
        return True, None

    def _detect_default_branch(self, repo_url: str) -> str | None:
        try:
            r = subprocess.run(
                ["git", "ls-remote", "--symref", repo_url, "HEAD"],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            # Parse: "ref: refs/heads/master\tHEAD"
            for line in r.stdout.splitlines():
                if line.startswith("ref: refs/heads/") and "HEAD" in line:
                    branch = line.split("/")[-1].split("\t")[0].strip()
                    self._log.info(f"Detected default branch: {branch}")
                    return branch
        except Exception:
            pass
        return None

    def _build_ok(self, target: Path, repo_url: str, branch: str, repo_name: str) -> ToolResult:
        output = (
            f"克隆成功!\n"
            f"仓库: {repo_url}\n"
            f"分支: {branch}\n"
            f"本地路径: {target}\n"
        )
        try:
            items = sorted(
                p.name for p in target.iterdir()
                if not p.name.startswith(".git")
            )
            output += f"\n文件/目录 ({len(items)} 项):\n" + "\n".join(
                f"  {'D' if (target / i).is_dir() else 'F'} {i}"
                for i in items[:30]
            )
        except Exception:
            pass
        return self._ok(output=output, repo_name=repo_name, local_path=str(target))

    @staticmethod
    def _rmdir(path: Path):
        import shutil
        try:
            shutil.rmtree(str(path), ignore_errors=True)
        except Exception:
            pass

    def _pull(self, target: Path, branch: str) -> ToolResult:
        # Detect current branch before attempting pulls
        current_branch = self._current_branch(target) or branch

        # Build ordered list of branches to try
        branches_to_try = []
        for b in [branch, current_branch] + self.FALLBACK_BRANCHES:
            if b and b not in branches_to_try:
                branches_to_try.append(b)

        last_error = None
        for br in branches_to_try:
            try:
                result = subprocess.run(
                    ["git", "-C", str(target), "pull", "origin", br],
                    capture_output=True, text=True, timeout=60,
                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                )
            except subprocess.TimeoutExpired:
                return self._fail("拉取超时")

            if result.returncode == 0:
                return self._ok(
                    output=f"仓库已存在，已拉取最新代码 ({br}): {target}",
                    repo_name=target.name,
                    local_path=str(target),
                )
            last_error = result.stderr.strip()

        # Pull failed, but the repo is still available locally
        self._log.warning(f"Pull failed for all branches, but repo exists: {last_error}")
        return self._ok(
            output=f"仓库已存在于本地: {target}\n(拉取更新失败，但之前克隆的代码可用)",
            repo_name=target.name,
            local_path=str(target),
        )

    @staticmethod
    def _current_branch(target: Path) -> str | None:
        try:
            r = subprocess.run(
                ["git", "-C", str(target), "branch", "--show-current"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def _repo_name(url: str) -> str:
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name or "repo"
