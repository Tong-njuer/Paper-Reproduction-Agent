import urllib.parse

import requests

from app.core.logging import get_logger
from app.tools import BaseTool, ToolResult


class FetchTool(BaseTool):
    name = "fetch_tool"
    description = "获取网页/论文内容。参数: url(目标URL), timeout(超时秒数，默认30)"

    def __init__(self):
        self._log = get_logger("fetch_tool")

    def execute(self, url: str = "", timeout: int = 30, **kwargs) -> ToolResult:
        if not url:
            return self._fail("缺少 URL 参数")

        self._log.info(f"Fetch: {url}")

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
            }
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            text = resp.text

            # Extract content
            title = ""
            body = ""

            # Try trafilatura for HTML
            try:
                import trafilatura
                extracted = trafilatura.extract(text, include_comments=False,
                                                include_tables=False)
                if extracted:
                    body = extracted
                    # Extract title
                    doc = trafilatura.extract(text, output_format="xml",
                                              include_comments=False)
                    if doc:
                        import re
                        m = re.search(r'<head><title>(.*?)</title>', doc)
                        if m:
                            title = m.group(1)
            except Exception:
                pass

            # Fallback: simple HTML title extraction
            if not title:
                import re
                m = re.search(r'<title>(.*?)</title>', text, re.I | re.S)
                if m:
                    title = m.group(1).strip()

            # Limit body length
            body = (body or text)[:3000]

            # Extract all URLs
            urls = self._extract_urls(text)

            output = f"获取成功: {title}\n\n"
            output += body[:2000]
            if len(body) > 2000:
                output += "\n\n[内容已截断]"

            if urls:
                output += f"\n\n发现的链接 ({len(urls)}个):\n"
                for u in urls[:10]:
                    output += f"  - {u}\n"

            return self._ok(
                output=output,
                title=title, body=body, urls=urls[:20],
                content_length=len(text),
            )

        except requests.exceptions.Timeout:
            return self._fail(f"请求超时 ({timeout}s): {url}")
        except requests.exceptions.HTTPError as e:
            return self._fail(f"HTTP 错误 {e.response.status_code}: {url}")
        except requests.exceptions.ConnectionError:
            return self._fail(f"连接失败: {url}")
        except Exception as e:
            self._log.error(f"Fetch failed: {e}")
            return self._fail(f"获取失败: {e}")

    @staticmethod
    def _extract_urls(text: str) -> list:
        import re
        return re.findall(r'https?://[^\s<>",{}|\\^`\[\]]+', text)
