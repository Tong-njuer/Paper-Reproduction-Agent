"""Repository indexing and file access utility tool."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from app.tools import BaseTool, ToolResult


class RepoIndexTool(BaseTool):
    """源码目录索引、检索、读取工具。"""

    name = "repo_index_tool"
    description = (
        "Index repository structure, search files, and read source snippets. "
        "Actions: index_tree, read_file, search_text, summarize_repo."
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        action = str(kwargs.get("action", "index_tree")).strip().lower()
        handlers = {
            "index_tree": self._index_tree,
            "read_file": self._read_file,
            "search_text": self._search_text,
            "summarize_repo": self._summarize_repo,
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
            return self._error(f"Repo index tool failed: {exc}", action=action)

    def _index_tree(self, kwargs: Dict[str, Any]) -> ToolResult:
        root = self._resolve_dir(kwargs.get("root_path"))
        max_depth = self._coerce_int(kwargs.get("max_depth", 4), minimum=1, maximum=20)
        include_hash = bool(kwargs.get("include_hash", False))

        nodes: List[Dict[str, Any]] = []
        root_depth = len(root.parts)

        for path in sorted(root.rglob("*")):
            depth = len(path.parts) - root_depth
            if depth > max_depth:
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            item: Dict[str, Any] = {
                "path": rel,
                "type": "dir" if path.is_dir() else "file",
                "depth": depth,
            }
            if path.is_file():
                item["size_bytes"] = path.stat().st_size
                if include_hash:
                    item["sha1"] = self._sha1(path)
            nodes.append(item)

        return self._success(
            output=json.dumps(nodes, ensure_ascii=False, indent=2),
            root_path=str(root),
            max_depth=max_depth,
            count=len(nodes),
            nodes=nodes,
        )

    def _read_file(self, kwargs: Dict[str, Any]) -> ToolResult:
        root = self._resolve_dir(kwargs.get("root_path"))
        rel_path = str(kwargs.get("path", "")).strip()
        if not rel_path:
            return self._error("read_file requires argument: path")

        start_line = self._coerce_int(kwargs.get("start_line", 1), minimum=1, maximum=1_000_000)
        end_line = self._coerce_int(kwargs.get("end_line", start_line + 200), minimum=start_line, maximum=1_000_000)

        file_path = (root / rel_path).resolve()
        if not str(file_path).startswith(str(root)):
            return self._error("Path traversal is not allowed", path=rel_path)
        if not file_path.exists() or not file_path.is_file():
            return self._error(f"File not found: {rel_path}")

        with file_path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()

        start_idx = start_line - 1
        end_idx = min(end_line, len(lines))
        selected = lines[start_idx:end_idx]
        text = "".join(selected)

        return self._success(
            output=text,
            path=rel_path,
            start_line=start_line,
            end_line=end_idx,
            total_lines=len(lines),
        )

    def _search_text(self, kwargs: Dict[str, Any]) -> ToolResult:
        root = self._resolve_dir(kwargs.get("root_path"))
        query = str(kwargs.get("query", "")).strip()
        if not query:
            return self._error("search_text requires argument: query")

        include_pattern = str(kwargs.get("include_pattern", "")).strip()
        max_results = self._coerce_int(kwargs.get("max_results", 100), minimum=1, maximum=5000)
        is_regex = bool(kwargs.get("is_regex", False))

        matcher = re.compile(query, re.IGNORECASE) if is_regex else None

        matches: List[Dict[str, Any]] = []
        for path in root.rglob("*"):
            if len(matches) >= max_results:
                break
            if not path.is_file():
                continue

            rel = str(path.relative_to(root)).replace("\\", "/")
            if include_pattern and include_pattern not in rel:
                continue

            try:
                with path.open("r", encoding="utf-8", errors="ignore") as fh:
                    for line_no, line in enumerate(fh, start=1):
                        hit = matcher.search(line) if matcher else (query.lower() in line.lower())
                        if hit:
                            matches.append(
                                {
                                    "path": rel,
                                    "line": line_no,
                                    "text": line.strip()[:400],
                                }
                            )
                            if len(matches) >= max_results:
                                break
            except OSError:
                continue

        return self._success(
            output=json.dumps(matches, ensure_ascii=False, indent=2),
            query=query,
            count=len(matches),
            matches=matches,
        )

    def _summarize_repo(self, kwargs: Dict[str, Any]) -> ToolResult:
        root = self._resolve_dir(kwargs.get("root_path"))

        summary = {
            "root_path": str(root),
            "languages": self._detect_languages(root),
            "dependency_manifests": self._collect_dependency_manifests(root),
            "entry_candidates": self._collect_entry_candidates(root),
            "test_files": self._collect_test_files(root),
            "file_count": sum(1 for path in root.rglob("*") if path.is_file()),
        }

        return self._success(
            output=json.dumps(summary, ensure_ascii=False, indent=2),
            summary=summary,
        )

    def _resolve_dir(self, value: Any) -> Path:
        raw = str(value or ".").strip()
        path = Path(raw).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise ValueError(f"Directory not found: {path}")
        return path

    def _sha1(self, path: Path) -> str:
        digest = hashlib.sha1()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _coerce_int(self, value: Any, minimum: int, maximum: int) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError):
            result = minimum
        return max(minimum, min(result, maximum))

    def _detect_languages(self, root: Path) -> Dict[str, int]:
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
        }
        counts: Dict[str, int] = {}
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            language = mapping.get(path.suffix.lower())
            if language:
                counts[language] = counts.get(language, 0) + 1
        return counts

    def _collect_dependency_manifests(self, root: Path) -> List[str]:
        names = {
            "requirements.txt",
            "pyproject.toml",
            "package.json",
            "pom.xml",
            "build.gradle",
            "go.mod",
            "cargo.toml",
        }
        result: List[str] = []
        for path in root.rglob("*"):
            if path.is_file() and path.name.lower() in names:
                result.append(str(path.relative_to(root)).replace("\\", "/"))
        return sorted(result)

    def _collect_entry_candidates(self, root: Path) -> List[str]:
        candidates = {"main.py", "app.py", "server.py", "train.py", "run.py", "index.js", "Program.cs"}
        result: List[str] = []
        for path in root.rglob("*"):
            if path.is_file() and path.name in candidates:
                result.append(str(path.relative_to(root)).replace("\\", "/"))
        return sorted(result)

    def _collect_test_files(self, root: Path) -> List[str]:
        result: List[str] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            lower = rel.lower()
            if "/tests/" in f"/{lower}" or lower.startswith("test_") or lower.endswith("_test.py"):
                result.append(rel)
        return sorted(result)
