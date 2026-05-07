import re

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
            return self._fail("未能找到源码仓库地址，建议在论文中搜索 'github' 或 'code' 等关键词")

        output = f"找到 {len(repos)} 个源码仓库候选:\n"
        for i, r in enumerate(repos[:5], 1):
            output += f"\n{i}. {r['url']}\n   平台: {r['platform']}\n   来源: {r['source']}"
            if r.get("context"):
                output += f"\n   上下文: {r['context'][:100]}"

        top = repos[0] if repos else None
        return self._ok(output=output, repos=repos[:5], top_repo=top, found_directly=len(repos) > 0)

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

        scored = []
        for c in candidates:
            url = c["url"].lower()
            platform = "unknown"
            score = 0

            for plat, weight in platform_weights.items():
                if plat in url:
                    platform = plat
                    score = weight
                    break

            # Deprioritize non-repo URLs
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
