"""Wiki and documentation lookup tool."""

from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import quote

import requests

from app.tools import BaseTool, ToolResult


class WikiTool(BaseTool):
    """检索维基百科条目并返回摘要。"""

    name = "wiki_tool"
    description = (
        "Search Wikipedia and return a summary. "
        "Args: query (required), lang='en', max_results=3, timeout=10."
    )

    _DEFAULT_TIMEOUT = 10
    _MAX_RESULTS = 5

    def execute(self, **kwargs: Any) -> ToolResult:
        query = str(kwargs.get("query", "")).strip()
        lang = str(kwargs.get("lang", "en")).strip() or "en"
        timeout = self._coerce_timeout(kwargs.get("timeout", self._DEFAULT_TIMEOUT))
        max_results = self._coerce_max_results(kwargs.get("max_results", 3))

        if not query:
            return self._error("Missing required argument: query")

        search_url = f"https://{lang}.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": max_results,
        }

        try:
            response = requests.get(search_url, params=search_params, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            search_items = payload.get("query", {}).get("search", [])

            if not search_items:
                return self._error(
                    f"No wiki results found for query: {query}",
                    query=query,
                    lang=lang,
                    retryable=False,
                )

            top_title = search_items[0].get("title", "")
            summary = self._fetch_summary(lang=lang, title=top_title, timeout=timeout)

            candidates: List[str] = [item.get("title", "") for item in search_items if item.get("title")]
            page_url = f"https://{lang}.wikipedia.org/wiki/{quote(top_title.replace(' ', '_'))}"

            return self._success(
                output=summary,
                query=query,
                lang=lang,
                title=top_title,
                page_url=page_url,
                candidates=candidates,
            )
        except requests.Timeout:
            return self._error(
                "Wiki request timed out.",
                query=query,
                lang=lang,
                retryable=True,
            )
        except requests.RequestException as exc:
            return self._error(
                f"Wiki request failed: {exc}",
                query=query,
                lang=lang,
                retryable=True,
            )
        except Exception as exc:  # pragma: no cover
            return self._error(
                f"Unexpected wiki tool error: {exc}",
                query=query,
                lang=lang,
            )

    def _fetch_summary(self, lang: str, title: str, timeout: int) -> str:
        rest_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
        response = requests.get(rest_url, timeout=timeout)
        response.raise_for_status()

        payload: Dict[str, Any] = response.json()
        extract = str(payload.get("extract", "")).strip()
        page_title = str(payload.get("title", title)).strip()

        if not extract:
            return f"{page_title}: summary not available."
        return f"{page_title}: {extract}"

    def _coerce_timeout(self, value: Any) -> int:
        try:
            timeout = int(value)
        except (TypeError, ValueError):
            return self._DEFAULT_TIMEOUT
        return max(1, min(timeout, 30))

    def _coerce_max_results(self, value: Any) -> int:
        try:
            max_results = int(value)
        except (TypeError, ValueError):
            return 3
        return max(1, min(max_results, self._MAX_RESULTS))
