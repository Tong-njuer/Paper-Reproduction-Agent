"""Paper ingestion and structured requirement extraction tool."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from app.tools import BaseTool, ToolResult


class PaperTool(BaseTool):
    """论文读取与复现要素抽取工具。"""

    name = "paper_tool"
    description = (
        "Ingest paper from text/pdf/url/identifier and extract structured "
        "requirements for reproduction workflow."
    )

    _DEFAULT_TIMEOUT_SECONDS = 15

    def execute(self, **kwargs: Any) -> ToolResult:
        action = str(kwargs.get("action", "extract")).strip().lower()

        handlers = {
            "extract": self._extract,
            "resolve_identifier": self._resolve_identifier,
            "extract_from_text": self._extract_from_text,
            "extract_from_pdf": self._extract_from_pdf,
            "extract_from_url": self._extract_from_url,
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
            return self._error(f"Paper tool failed: {exc}", action=action)

    def _extract(self, kwargs: Dict[str, Any]) -> ToolResult:
        if kwargs.get("text"):
            return self._extract_from_text(kwargs)
        if kwargs.get("pdf_path"):
            return self._extract_from_pdf(kwargs)
        if kwargs.get("url"):
            return self._extract_from_url(kwargs)
        if kwargs.get("identifier"):
            resolved = self._resolve_identifier(kwargs)
            if not resolved.success:
                return resolved
            url = resolved.metadata.get("url")
            return self._extract_from_url({**kwargs, "url": url})

        return self._error("extract requires one of: text, pdf_path, url, identifier")

    def _resolve_identifier(self, kwargs: Dict[str, Any]) -> ToolResult:
        identifier = str(kwargs.get("identifier", "")).strip()
        if not identifier:
            return self._error("Missing required argument: identifier")

        doi_match = re.match(r"^(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)$", identifier)
        if doi_match:
            url = f"https://doi.org/{identifier}"
            return self._success(output=url, identifier=identifier, identifier_type="doi", url=url)

        arxiv_match = re.match(r"^(arxiv:)?(\d{4}\.\d{4,5})(v\d+)?$", identifier, re.IGNORECASE)
        if arxiv_match:
            arxiv_id = arxiv_match.group(2)
            url = f"https://arxiv.org/abs/{arxiv_id}"
            return self._success(output=url, identifier=identifier, identifier_type="arxiv", url=url)

        if identifier.startswith("http://") or identifier.startswith("https://"):
            return self._success(output=identifier, identifier=identifier, identifier_type="url", url=identifier)

        return self._error(
            "Identifier format not recognized. Use DOI, arXiv id, or URL.",
            identifier=identifier,
        )

    def _extract_from_text(self, kwargs: Dict[str, Any]) -> ToolResult:
        text = str(kwargs.get("text", "")).strip()
        if not text:
            return self._error("Missing required argument: text")

        structured = self._parse_structure(text)
        return self._success(
            output=json.dumps(structured, ensure_ascii=False, indent=2),
            source_type="text",
            paper=structured,
        )

    def _extract_from_pdf(self, kwargs: Dict[str, Any]) -> ToolResult:
        pdf_path = Path(str(kwargs.get("pdf_path", "")).strip())
        if not str(pdf_path):
            return self._error("Missing required argument: pdf_path")
        if not pdf_path.exists() or not pdf_path.is_file():
            return self._error(f"PDF file not found: {pdf_path}")

        text = self._read_pdf_text(pdf_path)
        if not text.strip():
            return self._error("No text extracted from PDF", pdf_path=str(pdf_path))

        structured = self._parse_structure(text)
        return self._success(
            output=json.dumps(structured, ensure_ascii=False, indent=2),
            source_type="pdf",
            pdf_path=str(pdf_path),
            paper=structured,
        )

    def _extract_from_url(self, kwargs: Dict[str, Any]) -> ToolResult:
        url = str(kwargs.get("url", "")).strip()
        timeout = self._coerce_timeout(kwargs.get("timeout", self._DEFAULT_TIMEOUT_SECONDS))
        if not url:
            return self._error("Missing required argument: url")

        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            html = response.text
        except requests.Timeout:
            return self._error("URL fetch timed out", url=url, retryable=True)
        except requests.RequestException as exc:
            return self._error(f"URL fetch failed: {exc}", url=url, retryable=True)

        text = self._html_to_text(html)
        structured = self._parse_structure(text)
        structured["source_url"] = url

        return self._success(
            output=json.dumps(structured, ensure_ascii=False, indent=2),
            source_type="url",
            url=url,
            paper=structured,
        )

    def _read_pdf_text(self, pdf_path: Path) -> str:
        try:
            import fitz  # type: ignore

            chunks: List[str] = []
            with fitz.open(pdf_path) as doc:
                for page in doc:
                    chunks.append(page.get_text("text"))
            return "\n".join(chunks)
        except ImportError:
            raise ValueError("PyMuPDF is required for PDF parsing. Please install pymupdf.")

    def _parse_structure(self, text: str) -> Dict[str, Any]:
        normalized = self._normalize_text(text)

        title = self._guess_title(normalized)
        abstract = self._extract_section(normalized, ["abstract"], ["introduction", "1."])
        methods = self._extract_section(
            normalized,
            ["method", "approach", "methodology"],
            ["experiment", "results", "evaluation"],
        )
        experiments = self._extract_section(
            normalized,
            ["experiment", "evaluation", "results"],
            ["conclusion", "discussion", "references"],
        )

        datasets = self._extract_entities(
            normalized,
            [
                "cifar-10",
                "cifar10",
                "imagenet",
                "mnist",
                "wikitext",
                "squad",
                "ms-coco",
                "coco",
                "openwebtext",
            ],
        )
        metrics = self._extract_entities(
            normalized,
            ["accuracy", "f1", "bleu", "rouge", "mse", "mae", "auc", "precision", "recall"],
        )

        risks = self._infer_reproduction_risks(normalized)
        tasks = self._build_reproduction_tasks(datasets=datasets, metrics=metrics)

        return {
            "title": title,
            "abstract": abstract,
            "methods": methods,
            "experiments": experiments,
            "datasets": datasets,
            "metrics": metrics,
            "reproduction_risks": risks,
            "reproduction_tasks": tasks,
        }

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def _guess_title(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "Unknown Title"

        for line in lines[:8]:
            if len(line.split()) >= 4 and len(line) <= 180 and not line.lower().startswith("abstract"):
                return line
        return lines[0]

    def _extract_section(self, text: str, starts: List[str], ends: List[str]) -> str:
        lower = text.lower()
        start_idx = -1
        for start in starts:
            idx = lower.find(f"\n{start}")
            if idx == -1:
                idx = lower.find(start)
            if idx != -1:
                start_idx = idx
                break

        if start_idx == -1:
            return ""

        end_idx = len(text)
        for end in ends:
            idx = lower.find(f"\n{end}", start_idx + 1)
            if idx != -1:
                end_idx = min(end_idx, idx)

        section = text[start_idx:end_idx].strip()
        return section[:4000]

    def _extract_entities(self, text: str, candidates: List[str]) -> List[str]:
        lower = text.lower()
        found: List[str] = []
        for candidate in candidates:
            if candidate.lower() in lower:
                found.append(candidate)
        # 去重并保序
        deduped: List[str] = []
        for item in found:
            if item not in deduped:
                deduped.append(item)
        return deduped

    def _infer_reproduction_risks(self, text: str) -> List[str]:
        risks: List[str] = []
        lower = text.lower()

        if "code" not in lower and "github" not in lower:
            risks.append("No explicit code reference detected")
        if "dataset" not in lower and "data" not in lower:
            risks.append("Dataset description may be incomplete")
        if "hyperparameter" not in lower and "learning rate" not in lower:
            risks.append("Hyperparameter details may be missing")
        if "gpu" in lower and "memory" in lower:
            risks.append("Hardware constraints likely required")

        if not risks:
            risks.append("No obvious critical risk detected by heuristic parser")
        return risks

    def _build_reproduction_tasks(self, datasets: List[str], metrics: List[str]) -> List[str]:
        tasks = [
            "Parse paper and extract method pipeline",
            "Locate official code repository and pin commit",
            "Prepare isolated environment and install dependencies",
            "Run smoke test and baseline evaluation",
            "Run reproduction experiments and collect artifacts",
            "Compare reproduced metrics with paper-reported results",
            "Generate structured reproduction report",
        ]
        if datasets:
            tasks.insert(3, f"Prepare datasets: {', '.join(datasets)}")
        if metrics:
            tasks.append(f"Validate target metrics: {', '.join(metrics)}")
        return tasks

    def _html_to_text(self, html: str) -> str:
        # 优先使用 trafilatura 获取正文，失败再使用轻量降级。
        try:
            import trafilatura  # type: ignore

            extracted = trafilatura.extract(html)
            if extracted:
                return extracted
        except Exception:
            pass

        text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _coerce_timeout(self, value: Any) -> int:
        try:
            timeout = int(value)
        except (TypeError, ValueError):
            return self._DEFAULT_TIMEOUT_SECONDS
        return max(1, min(timeout, 60))
