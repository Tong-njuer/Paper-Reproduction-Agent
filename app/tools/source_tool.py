import re

from app.core.llm import get_llm
from app.core.logging import get_logger
from app.tools import BaseTool, ToolResult


class SourceTool(BaseTool):
    name = "source_tool"
    description = "查找论文源码仓库。参数: paper_info(论文信息文本), urls(候选URL列表，逗号分隔)"

    def __init__(self):
        self._log = get_logger("source_tool")

    def execute(self, paper_info: str = "", urls: str = "", **kwargs) -> ToolResult:
        self._log.info(f"Finding source: info_len={len(paper_info)}, urls={urls[:100] if urls else 'none'}")

        candidates = []

        # Parse URLs parameter
        if urls:
            candidates.extend(self._parse_urls(urls))

        # Extract URLs from paper info
        if paper_info:
            candidates.extend(self._extract_urls(paper_info))

        # Score and filter
        repos = self._score_repos(candidates)

        if not repos:
            # Try to infer common patterns
            inferred = self._infer_repo(paper_info)
            if inferred:
                output = f"未直接找到源码链接，根据论文信息推断可能的仓库:\n"
                for r in inferred:
                    output += f"  - {r['url']} (置信度: {r['confidence']})\n"
                return self._ok(output=output, repos=inferred, found_directly=False)

            # Fall back to LLM knowledge for papers that don't cite their repo
            llm_repos = self._lookup_repo_via_llm(paper_info)
            if llm_repos:
                # Verify the top candidate actually exists before returning
                verified = self._verify_repo_url(llm_repos[0]["url"])
                if verified:
                    output = self._format_repo_output(llm_repos)
                    top = llm_repos[0]
                    return self._ok(output=output, repos=llm_repos, top_repo=top, found_directly=True)
                else:
                    # Top URL doesn't exist — try remaining candidates
                    self._log.warning(f"LLM-suggested repo URL not found: {llm_repos[0]['url']}")
                    for r in llm_repos[1:]:
                        if self._verify_repo_url(r["url"]):
                            output = self._format_repo_output([r])
                            return self._ok(output=output, repos=[r], top_repo=r, found_directly=True)
                    # None verified — return unverified but flag as untested
                    output = self._format_repo_output(llm_repos)
                    output += "\n⚠️ 无法验证仓库是否存在，克隆时可能失败。"
                    top = llm_repos[0]
                    return self._ok(output=output, repos=llm_repos, top_repo=top, found_directly=True)

            return self._fail("未能找到源码仓库地址，建议在论文中搜索 'github' 或 'code' 等关键词")

        # Verify the top repo candidate exists
        top = repos[0]
        if not self._verify_repo_url(top["url"]):
            self._log.warning(f"Top candidate URL not found: {top['url']}")
            # Try remaining candidates
            for r in repos[1:]:
                if self._verify_repo_url(r["url"]):
                    output = f"找到 {len(repos)} 个源码仓库候选 (已验证:{r['url']}):\n"
                    for i, rr in enumerate(repos[:5], 1):
                        marker = " ✅" if rr['url'] == r['url'] else ""
                        output += f"\n{i}. {rr['url']}{marker}\n   平台: {rr['platform']}\n   来源: {rr['source']}"
                        if rr.get("context"):
                            output += f"\n   上下文: {rr['context'][:100]}"
                    return self._ok(output=output, repos=repos[:5], top_repo=r, found_directly=True)
            # None verified
            output = self._format_repo_output(repos[:5])
            output += "\n⚠️ 无法验证仓库是否存在，克隆时可能失败。"
            return self._ok(output=output, repos=repos[:5], top_repo=top, found_directly=True)

        output = self._format_repo_output(repos[:5])
        return self._ok(output=output, repos=repos[:5], top_repo=top, found_directly=True)

    def _format_repo_output(self, repos: list) -> str:
        """Build a human-readable string from a list of repo dicts."""
        output = f"找到 {len(repos)} 个源码仓库候选:\n"
        for i, r in enumerate(repos, 1):
            output += f"\n{i}. {r['url']}\n   平台: {r['platform']}\n   置信度: {r.get('confidence', 'N/A')}"
            if r.get("evidence"):
                output += f"\n   依据: {r['evidence']}"
            if r.get("context"):
                output += f"\n   上下文: {r['context'][:100]}"
        return output

    @staticmethod
    def _verify_repo_url(url: str) -> bool:
        """Quick lightweight check that a GitHub repo URL actually exists.

        Uses a HEAD request to GitHub's API — fast (~1s) and doesn't count
        against API rate limits for simple requests.
        """
        import re
        import requests
        # Only verify GitHub URLs for now
        m = re.match(r'https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$', url)
        if not m:
            return True  # Non-GitHub URLs pass (can't easily verify)
        owner, repo = m.group(1), m.group(2).rstrip("/")
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        try:
            resp = requests.head(api_url, timeout=5, headers={"Accept": "application/vnd.github.v3+json"})
            return resp.status_code == 200
        except Exception:
            return True  # Can't verify, assume exists (better than false negative)

    def _parse_urls(self, urls_str: str) -> list:
        result = []
        for url in urls_str.replace(",", " ").split():
            url = url.strip()
            if url and re.match(r'https?://', url):
                result.append({"url": url, "source": "provided", "context": ""})
        return result

    def _extract_urls(self, text: str) -> list:
        found = re.findall(r'https?://[^\s<>",{}|\\^`\[\]]+', text)
        return [{"url": u, "source": "extracted", "context": ""} for u in found]

    def _score_repos(self, candidates: list) -> list:
        platform_weights = {
            "github.com": 10, "gitlab.com": 8, "bitbucket.org": 6,
            "gitee.com": 5, "huggingface.co": 7, "bitbucket": 6,
        }
        # Domains that are never code repositories
        non_repo_domains = [
            "arxiv.org", "doi.org", "scholar.google", "semanticscholar.org",
            "dl.acm.org", "ieeexplore.ieee.org", "link.springer.com",
            "sciencedirect.com", "nature.com", "aclanthology.org",
            "openreview.net", "jmlr.org", "neurips.cc", "icml.cc",
            "cv-foundation.org", "proceedings.mlr.press",
        ]

        scored = []
        for c in candidates:
            url = c["url"].lower()
            platform = "unknown"
            score = 0

            # Exclude academic / non-repo domains immediately
            for nd in non_repo_domains:
                if nd in url:
                    score = -10
                    break

            if score < 0:
                scored.append({
                    "url": c["url"], "platform": platform,
                    "source": c.get("source", "unknown"),
                    "context": c.get("context", ""), "score": score,
                })
                continue

            for plat, weight in platform_weights.items():
                if plat in url:
                    platform = plat
                    score = weight
                    break

            # Deprioritize non-repo URL patterns
            skip_patterns = ["/issues", "/pull/", "/wiki", "/tree/", "/blob/",
                             "/releases", "/tags", "/actions"]
            for sp in skip_patterns:
                if sp in url:
                    score -= 3

            # Prefer URLs that look like repos (user/repo pattern)
            if re.search(r'/([^/]+)/([^/]+?)(?:\.git)?$', url):
                score += 2

            scored.append({
                "url": c["url"],
                "platform": platform,
                "source": c.get("source", "unknown"),
                "context": c.get("context", ""),
                "score": score,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return [s for s in scored if s["score"] > 0]

    def _infer_repo(self, paper_info: str) -> list:
        if not paper_info:
            return []

        # Look for common patterns: "code is available at", "github.com/xxx/yyy"
        repo_urls = re.findall(
            r'(?:github|gitlab|bitbucket)\.com/[\w.-]+/[\w.-]+',
            paper_info, re.I
        )
        inferred = []
        for url in repo_urls[:3]:
            inferred.append({
                "url": f"https://{url}",
                "platform": url.split(".")[0],
                "source": "inferred",
                "confidence": 0.5 if url.lower() in paper_info.lower() else 0.3,
            })
        return inferred

    def _lookup_repo_via_llm(self, paper_info: str) -> list:
        """Ask LLM for the known source-code repository of a paper.

        Many papers (BERT, GPT, ResNet, etc.) don't cite their repo in the
        paper text, but the LLM training data includes this mapping.
        """
        if not paper_info:
            return []
        try:
            llm = get_llm()
            # Use first ~1500 chars — enough for title, authors, abstract
            context = paper_info[:1500]
            resp = llm.generate_structured(
                f"以下是论文信息，请提供该论文的官方源码仓库地址（GitHub 等）。\n\n"
                f"论文信息:\n{context}\n\n"
                f"要求:\n"
                f"1. 只返回你确信是该论文官方实现的仓库，不要猜测\n"
                f"2. 如果不确定或论文没有公开官方代码，repos 为空数组\n"
                f"3. evidence 字段说明你是如何确认该仓库与论文关联的\n\n"
                f"返回 JSON:\n"
                f'{{"repos": [{{"url": "仓库URL", "platform": "github", '
                f'"confidence": 0.9, "evidence": "关联证据"}}]}}'
            )
            repos = resp.get("repos", [])
            result = []
            for r in repos:
                url = r.get("url", "")
                if url and re.match(r'https?://', url):
                    result.append({
                        "url": url,
                        "platform": r.get("platform", "unknown"),
                        "source": "llm",
                        "confidence": r.get("confidence", 0.7),
                        "evidence": r.get("evidence", ""),
                    })
            return result
        except Exception as e:
            self._log.warning(f"LLM source lookup skipped: {e}")
            return []
