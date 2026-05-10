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

        # Repo search queries: skip arXiv — it indexes papers, not repos.
        # Go straight to LLM (which knows well-known repo URLs) or web search.
        repo_kw = ["github", "gitlab", "repository", "repo", "源码", "仓库",
                   "clone", "克隆", "code", "implementation", "实现"]
        is_repo_search = any(kw in query.lower() for kw in repo_kw)

        if source in ("llm", "arxiv") and not is_repo_search:
            try:
                arxiv_result = self._search_arxiv(query)
                if arxiv_result.success and arxiv_result.metadata.get("results"):
                    self._enrich_with_llm(arxiv_result, query)
                    return arxiv_result
            except Exception as e:
                self._log.warning(f"arXiv search failed: {e}, trying fallback")

            # arXiv found nothing — try LLM fallback before giving up
            if source == "arxiv":
                self._log.info("arXiv found nothing, trying LLM fallback…")
                try:
                    llm_result = self._search_via_llm(query)
                    if llm_result.success:
                        return llm_result
                except Exception:
                    pass
                return self._fail(
                    f"arXiv 和 LLM 均未找到 '{query}' 的相关论文。"
                    f"请尝试调整搜索词，或使用 source=web / source=wikipedia。"
                )
            return self._search_via_llm(query)

        # Repo search (or explicitly non-arxiv source): skip arXiv entirely.
        # arXiv indexes academic papers, not code repos.  Use LLM (which
        # knows well-known repo URLs) or web search directly.
        if is_repo_search and source in ("llm", "arxiv"):
            self._log.info(f"Repo search detected, using LLM instead of arXiv")
            try:
                llm_result = self._search_via_llm(query)
                if llm_result.success:
                    return llm_result
            except Exception:
                pass
            # LLM failed — try web search as fallback
            try:
                return self._search_web(query)
            except Exception:
                pass
            return self._fail(
                f"LLM 和 web 搜索均未找到 '{query}'。"
                f"请直接提供仓库 URL。"
            )

        # Wikipedia / web — try directly, no arXiv fallback
        try:
            if source == "wikipedia":
                return self._search_wikipedia(query)
            elif source == "web":
                return self._search_web(query)
            else:
                return self._search_via_llm(query)
        except Exception as e:
            self._log.warning(f"External search failed: {e}, falling back to LLM")
            return self._search_via_llm(query)

    def _enrich_with_llm(self, arxiv_result: ToolResult, query: str):
        """Ask LLM to supplement arXiv results with source-code URLs."""
        try:
            results = arxiv_result.metadata.get("results", [])
            paper_title = results[0].get("title", query) if results else query
            resp = self._llm.generate_structured(
                f"论文标题: {paper_title}\n"
                f"用户搜索: {query}\n"
                f"arXiv摘要: {arxiv_result.output[:500]}\n\n"
                f"请提供该论文的官方源码仓库地址（GitHub等）。\n"
                f"要求:\n"
                f"1. 只返回你确认是该论文实现的仓库\n"
                f"2. 如果论文没有公开官方代码，source_url 为空\n"
                f"3. 社区实现或非官方仓库请在 note 中说明\n"
                f'{{"source_url": "源码URL或空字符串", "note": "说明"}}'
            )
            source_url = resp.get("source_url", "")
            if source_url:
                # Append source URL to output and metadata
                arxiv_result.output += f"\n源码: {source_url}\n"
                for r in arxiv_result.metadata.get("results", []):
                    r["source_url"] = source_url
                    if source_url not in r.get("urls", []):
                        r.setdefault("urls", []).append(source_url)
        except Exception as e:
            self._log.warning(f"LLM enrichment skipped: {e}")

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
