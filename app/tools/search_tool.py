import json
import urllib.parse

import requests

from app.core.llm import get_llm
from app.core.logging import get_logger
from app.tools import BaseTool, ToolResult


class SearchTool(BaseTool):
    name = "search_tool"
    description = (
        "搜索论文信息。参数: query(搜索词), source(llm/web/wikipedia/arxiv)，默认llm"
    )

    def __init__(self):
        self._log = get_logger("search_tool")
        self._llm = get_llm()

    def execute(self, query: str = "", source: str = "llm", **kwargs) -> ToolResult:
        if not query:
            return self._fail("缺少搜索关键词 (query)")

        self._log.info(f"Search: [{source}] {query[:80]}")

        # Primary: LLM-based search (works everywhere, no API blocks)
        if source == "llm":
            return self._search_via_llm(query)

        # External API fallbacks
        try:
            if source == "arxiv":
                return self._search_arxiv(query)
            elif source == "wikipedia":
                return self._search_wikipedia(query)
            elif source == "web":
                return self._search_web(query)
            else:
                return self._search_via_llm(query)
        except Exception as e:
            self._log.warning(f"External search failed: {e}, falling back to LLM")
            return self._search_via_llm(query)

    def _search_via_llm(self, query: str) -> ToolResult:
        """Use LLM to search for paper information. LLMs have vast training data."""
        prompt = f"""请搜索以下论文的信息，提供: 论文标题、作者、发表年份、arXiv链接（如有）、
以及官方源码仓库地址（GitHub等，如有）。

查询: {query}

请以JSON格式返回，如果找不到信息请如实说明:
{{
    "title": "论文标题",
    "authors": "作者列表",
    "year": "发表年份",
    "arxiv_url": "arXiv链接或空字符串",
    "source_url": "官方源码仓库URL或空字符串",
    "abstract": "简短摘要",
    "additional_urls": ["其他相关链接"],
    "note": "补充说明"
}}"""

        try:
            resp = self._llm.generate_structured(prompt)
            title = resp.get("title", "")
            arxiv_url = resp.get("arxiv_url", "")
            source_url = resp.get("source_url", "")
            abstract = resp.get("abstract", "")
            authors = resp.get("authors", "")
            year = resp.get("year", "")
            note = resp.get("note", "")

            urls = [u for u in [arxiv_url, source_url] if u]
            urls.extend(resp.get("additional_urls", []))

            output = f"搜索 '{query}' 结果:\n"
            output += f"标题: {title}\n"
            output += f"作者: {authors}\n"
            output += f"年份: {year}\n"
            output += f"摘要: {abstract[:300]}\n"
            if arxiv_url:
                output += f"arXiv: {arxiv_url}\n"
            if source_url:
                output += f"源码: {source_url}\n"
            if note:
                output += f"备注: {note}\n"

            results = [{
                "title": title, "authors": authors, "year": year,
                "abstract": abstract, "arxiv_url": arxiv_url,
                "source_url": source_url, "urls": urls,
                "source": "llm",
            }]

            return self._ok(output=output, results=results, source="llm")

        except Exception as e:
            self._log.error(f"LLM search failed: {e}")
            return self._fail(f"搜索失败: {e}")

    def _search_arxiv(self, query: str) -> ToolResult:
        encoded = urllib.parse.quote(query)
        url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&start=0&max_results=5"
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"arXiv API returned {resp.status_code}")

        import xml.etree.ElementTree as ET
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        root = ET.fromstring(resp.text)
        entries = root.findall("atom:entry", ns)

        if not entries:
            return self._ok(
                output=f"arXiv 未找到 '{query}' 的相关论文",
                results=[], source="arxiv",
            )

        results = []
        for entry in entries[:5]:
            title = self._text(entry, "atom:title", ns)
            summary = self._text(entry, "atom:summary", ns)
            arxiv_url = ""
            for link in entry.findall("atom:link", ns):
                if link.get("type") == "text/html" or not link.get("type"):
                    arxiv_url = link.get("href", "")
                    break
            results.append({
                "title": title.strip() if title else "",
                "summary": (summary or "")[:500].strip(),
                "url": arxiv_url, "source": "arxiv",
            })

        output = f"arXiv 搜索 '{query}' 找到 {len(results)} 篇论文:\n"
        for i, r in enumerate(results, 1):
            output += f"\n{i}. {r['title']}\n   URL: {r['url']}\n   摘要: {r['summary'][:150]}..."
        return self._ok(output=output, results=results, source="arxiv")

    def _search_wikipedia(self, query: str) -> ToolResult:
        encoded = urllib.parse.quote(query)
        search_url = (
            f"https://en.wikipedia.org/w/api.php"
            f"?action=opensearch&search={encoded}&limit=5&format=json"
        )
        resp = requests.get(search_url, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"Wikipedia API returned {resp.status_code}")
        data = resp.json()
        titles = data[1] if len(data) > 1 else []
        urls = data[3] if len(data) > 3 else []

        if not titles:
            return self._ok(
                output=f"Wikipedia 未找到 '{query}'", results=[], source="wikipedia")

        results = []
        for i, title in enumerate(titles):
            summary = ""
            page_title = urls[i].split("/")[-1] if i < len(urls) and urls[i] else ""
            if page_title:
                try:
                    sr = requests.get(
                        f"https://en.wikipedia.org/api/rest_v1/page/summary/{page_title}",
                        timeout=10)
                    if sr.status_code == 200:
                        summary = sr.json().get("extract", "")[:500]
                except Exception:
                    pass
            results.append({
                "title": title, "summary": summary,
                "url": urls[i] if i < len(urls) else "",
                "source": "wikipedia",
            })

        output = f"Wikipedia 搜索 '{query}' 找到 {len(results)} 个条目:\n"
        for i, r in enumerate(results, 1):
            output += f"\n{i}. {r['title']}\n   URL: {r['url']}\n   摘要: {r['summary'][:150]}..."
        return self._ok(output=output, results=results, source="wikipedia")

    def _search_web(self, query: str) -> ToolResult:
        encoded = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            heading = data.get("Heading", "")
            abstract = data.get("AbstractText", "")
            abstract_url = data.get("AbstractURL", "")
            if heading:
                output = f"搜索 '{query}':\n标题: {heading}\n摘要: {abstract[:300]}"
                if abstract_url:
                    output += f"\nURL: {abstract_url}"
                return self._ok(
                    output=output,
                    results=[{"title": heading, "summary": abstract, "url": abstract_url}],
                    source="duckduckgo",
                )
        raise RuntimeError("DuckDuckGo returned no results")

    @staticmethod
    def _text(element, tag, ns):
        el = element.find(tag, ns)
        return el.text if el is not None else ""
