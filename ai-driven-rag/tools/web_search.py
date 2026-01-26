"""Web search tool using DuckDuckGo."""
import httpx
from urllib.parse import quote_plus

from .base import Tool


class WebSearchTool(Tool):
    """Real-time web search using DuckDuckGo."""

    name = "web_search"
    description = """Search the internet for real-time information.
Use this tool when:
- User asks about recent news or updates
- Information might not be in stored documents
- User explicitly asks to search the web
- You need current/latest information

Returns web search results with titles, snippets, and URLs."""

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query for web search",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default: 5)",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(
        self,
        query: str,
        max_results: int = 5,
    ) -> dict:
        """Execute web search using DuckDuckGo HTML."""
        try:
            # Use DuckDuckGo HTML search
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    },
                    follow_redirects=True,
                )
                response.raise_for_status()
                html = response.text

            # Parse results from HTML
            results = self._parse_ddg_html(html, max_results)

            return {
                "query": query,
                "source": "duckduckgo",
                "results": results,
                "total": len(results),
            }

        except Exception as e:
            return {
                "query": query,
                "error": str(e),
                "results": [],
                "total": 0,
            }

    def _parse_ddg_html(self, html: str, max_results: int) -> list[dict]:
        """Parse DuckDuckGo HTML response."""
        results = []

        # Simple parsing without external library
        # Look for result blocks
        import re

        # Pattern for result links
        link_pattern = r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
        snippet_pattern = r'<a[^>]+class="result__snippet"[^>]*>([^<]+(?:<[^>]+>[^<]*</[^>]+>)*[^<]*)</a>'

        links = re.findall(link_pattern, html)
        snippets = re.findall(snippet_pattern, html)

        for i, (url, title) in enumerate(links[:max_results]):
            snippet = snippets[i] if i < len(snippets) else ""
            # Clean HTML tags from snippet
            snippet = re.sub(r'<[^>]+>', '', snippet).strip()

            results.append({
                "title": title.strip(),
                "url": url,
                "snippet": snippet[:300],
                "source_type": "web",
            })

        return results

    async def close(self):
        """No cleanup needed."""
        pass
