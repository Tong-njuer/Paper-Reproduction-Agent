"""Source acquisition and repository integrity analysis tool."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from app.tools import BaseTool, ToolResult


class SourceTool(BaseTool):
    """源码获取、候选识别与完整性分析工具。"""

    name = "source_tool"
    description = (
        "Acquire and analyze source bundle for reproduction. "
        "Actions: discover_candidates, clone_repo, download_archive, analyze_source."
    )

    _DEFAULT_TIMEOUT_SECONDS = 30

    def execute(self, **kwargs: Any) -> ToolResult:
        action = str(kwargs.get("action", "analyze_source")).strip().lower()
        handlers = {
            "discover_candidates": self._discover_candidates,
            "clone_repo": self._clone_repo,
            "download_archive": self._download_archive,
            "analyze_source": self._analyze_source,
        }

        handler = handlers.get(action)
        if handler is None:
            return self._error(
                f"Unsupported action: {action}",
                supported_actions=sorted(handlers.keys()),
            )

        try:
            return handler(kwargs)
        except Exception as exc:  # pragma: no cover
            return self._error(f"Source tool failed: {exc}", action=action)

    def _discover_candidates(self, kwargs: Dict[str, Any]) -> ToolResult:
        text = str(kwargs.get("text", ""))
        explicit_urls = kwargs.get("candidate_urls") or []

        discovered: List[str] = []
        if isinstance(explicit_urls, list):
            for item in explicit_urls:
                value = str(item).strip()
                if value:
                    discovered.append(value)

        # 从论文文本中抽取链接。
        for match in re.findall(r"https?://[^\s)\]>\"]+", text):
            discovered.append(match.strip())

        # 优先保留常见代码托管平台。
        host_priority = {
            "github.com": 1,
            "gitlab.com": 2,
            "huggingface.co": 3,
            "gitee.com": 4,
        }

        normalized: List[str] = []
        for url in discovered:
            url = url.rstrip(".,;")
            if url not in normalized:
                normalized.append(url)

        scored: List[Dict[str, Any]] = []
        for url in normalized:
            host = urlparse(url).netloc.lower()
            score = 0.5
            for key, weight in host_priority.items():
                if key in host:
                    score = 1.0 - weight * 0.1
                    break
            if "/issues" in url or "/pull/" in url:
                score -= 0.2
            scored.append({"url": url, "host": host, "confidence": round(max(0.1, min(score, 0.99)), 2)})

        scored.sort(key=lambda item: item["confidence"], reverse=True)

        return self._success(
            output=json.dumps(scored, ensure_ascii=False, indent=2),
            candidates=scored,
            count=len(scored),
        )

    def _clone_repo(self, kwargs: Dict[str, Any]) -> ToolResult:
        repo_url = str(kwargs.get("repo_url", "")).strip()
        dest_dir = str(kwargs.get("dest_dir", "")).strip()
        branch = str(kwargs.get("branch", "")).strip()
        depth = kwargs.get("depth", 1)
        timeout = self._coerce_timeout(kwargs.get("timeout", self._DEFAULT_TIMEOUT_SECONDS * 4))

        if not repo_url:
            return self._error("Missing required argument: repo_url")
        if not dest_dir:
            return self._error("Missing required argument: dest_dir")

        target_path = Path(dest_dir).expanduser().resolve()
        if target_path.exists() and any(target_path.iterdir()):
            return self._error("Destination directory already exists and is not empty", dest_dir=str(target_path))

        target_path.mkdir(parents=True, exist_ok=True)

        clone_cmd = ["git", "clone", repo_url, str(target_path)]
        if branch:
            clone_cmd.extend(["--branch", branch])

        try:
            clone_depth = int(depth)
            if clone_depth > 0:
                clone_cmd.extend(["--depth", str(clone_depth)])
        except (TypeError, ValueError):
            pass

        result = subprocess.run(
            clone_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return self._error(
                f"git clone failed with return code {result.returncode}",
                repo_url=repo_url,
                dest_dir=str(target_path),
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
                returncode=result.returncode,
            )

        commit = self._read_git_head_commit(target_path)
        return self._success(
            output=f"Repository cloned to {target_path}",
            repo_url=repo_url,
            dest_dir=str(target_path),
            commit=commit,
            stdout=result.stdout.strip(),
        )

    def _download_archive(self, kwargs: Dict[str, Any]) -> ToolResult:
        url = str(kwargs.get("url", "")).strip()
        output_path = str(kwargs.get("output_path", "")).strip()
        timeout = self._coerce_timeout(kwargs.get("timeout", self._DEFAULT_TIMEOUT_SECONDS * 2))

        if not url:
            return self._error("Missing required argument: url")
        if not output_path:
            return self._error("Missing required argument: output_path")

        path = Path(output_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with requests.get(url, timeout=timeout, stream=True) as response:
                response.raise_for_status()
                with path.open("wb") as fh:
                    for chunk in response.iter_content(chunk_size=1024 * 128):
                        if chunk:
                            fh.write(chunk)
        except requests.Timeout:
            return self._error("Archive download timed out", url=url, output_path=str(path), retryable=True)
        except requests.RequestException as exc:
            return self._error(f"Archive download failed: {exc}", url=url, output_path=str(path), retryable=True)

        sha256 = self._sha256_file(path)
        return self._success(
            output=f"Archive downloaded: {path}",
            url=url,
            output_path=str(path),
            sha256=sha256,
            size_bytes=path.stat().st_size,
        )

    def _analyze_source(self, kwargs: Dict[str, Any]) -> ToolResult:
        source_path = str(kwargs.get("source_path", "")).strip()
        if not source_path:
            return self._error("Missing required argument: source_path")

        root = Path(source_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return self._error(f"Source path not found: {root}")

        dependency_files = self._find_dependency_files(root)
        entrypoints = self._find_entrypoints(root)
        test_files = self._find_tests(root)
        readme_files = self._glob_names(root, ["README", "README.md", "readme.md"])
        scripts = self._glob_by_suffix(root, [".sh", ".ps1", ".bat"])
        large_files = self._find_large_files(root, threshold_mb=float(kwargs.get("large_file_threshold_mb", 50)))
        license_files = self._glob_names(root, ["LICENSE", "LICENSE.txt", "license", "license.txt"])

        bundle = {
            "repo_path": str(root),
            "dependency_files": dependency_files,
            "entrypoints": entrypoints,
            "test_files": test_files,
            "readme_files": readme_files,
            "script_files": scripts,
            "large_files": large_files,
            "license_files": license_files,
            "file_count": self._count_files(root),
        }

        completeness = {
            "has_readme": len(readme_files) > 0,
            "has_dependency_file": len(dependency_files) > 0,
            "has_test_or_example": len(test_files) > 0 or len(scripts) > 0,
            "has_entrypoint": len(entrypoints) > 0,
            "has_license": len(license_files) > 0,
        }
        completeness["score"] = round(sum(1 for flag in completeness.values() if flag is True) / 5.0, 2)

        return self._success(
            output=json.dumps({"bundle": bundle, "completeness": completeness}, ensure_ascii=False, indent=2),
            bundle=bundle,
            completeness=completeness,
        )

    def _find_dependency_files(self, root: Path) -> List[str]:
        names = [
            "requirements.txt",
            "pyproject.toml",
            "poetry.lock",
            "package.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "pom.xml",
            "build.gradle",
            "Cargo.toml",
            "go.mod",
            "environment.yml",
        ]
        return self._glob_names(root, names)

    def _find_entrypoints(self, root: Path) -> List[str]:
        candidates = [
            "main.py",
            "app.py",
            "server.py",
            "train.py",
            "run.py",
            "index.js",
            "src/main.py",
            "Program.cs",
        ]
        found = []
        for rel in candidates:
            path = root / rel
            if path.exists() and path.is_file():
                found.append(str(path.relative_to(root)).replace("\\", "/"))
        return found

    def _find_tests(self, root: Path) -> List[str]:
        matches: List[str] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            lower = rel.lower()
            if (
                "/test" in lower
                or "/tests" in lower
                or lower.startswith("test_")
                or lower.endswith("_test.py")
                or lower.endswith(".spec.js")
            ):
                matches.append(rel)
        return matches[:500]

    def _find_large_files(self, root: Path, threshold_mb: float) -> List[Dict[str, Any]]:
        threshold_bytes = int(max(threshold_mb, 1.0) * 1024 * 1024)
        items: List[Dict[str, Any]] = []
        for path in root.rglob("*"):
            if path.is_file():
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if size >= threshold_bytes:
                    items.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "size_bytes": size,
                            "size_mb": round(size / (1024 * 1024), 2),
                        }
                    )
        items.sort(key=lambda item: item["size_bytes"], reverse=True)
        return items[:100]

    def _glob_names(self, root: Path, names: List[str]) -> List[str]:
        lookup = {name.lower() for name in names}
        matches: List[str] = []
        for path in root.rglob("*"):
            if path.is_file() and path.name.lower() in lookup:
                matches.append(str(path.relative_to(root)).replace("\\", "/"))
        return sorted(matches)

    def _glob_by_suffix(self, root: Path, suffixes: List[str]) -> List[str]:
        lookup = {suffix.lower() for suffix in suffixes}
        matches: List[str] = []
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in lookup:
                matches.append(str(path.relative_to(root)).replace("\\", "/"))
        return sorted(matches)

    def _count_files(self, root: Path) -> int:
        count = 0
        for path in root.rglob("*"):
            if path.is_file():
                count += 1
        return count

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _read_git_head_commit(self, repo_path: Path) -> Optional[str]:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        commit = result.stdout.strip()
        return commit or None

    def _coerce_timeout(self, value: Any) -> int:
        try:
            timeout = int(value)
        except (TypeError, ValueError):
            return self._DEFAULT_TIMEOUT_SECONDS
        return max(1, min(timeout, 600))
