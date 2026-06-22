import httpx
from typing import List, Dict


async def web_search(query: str, max_results: int = 5) -> List[Dict]:
    """
    Search the web using DuckDuckGo Instant Answer API.
    No API key required.
    """
    try:
        # DuckDuckGo Instant Answer API
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_redirect": "1",
                    "no_html": "1",
                    "skip_disambig": "1"
                }
            )
            data = response.json()

        results = []

        # Abstract (main answer)
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", "Answer"),
                "snippet": data["AbstractText"],
                "url": data.get("AbstractURL", ""),
                "source": "DuckDuckGo Abstract"
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:80],
                    "snippet": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                    "source": "DuckDuckGo Related"
                })

        # If no results from instant API, use HTML search fallback
        if not results:
            results = await _fallback_search(query, max_results)

        return results[:max_results]

    except Exception as e:
        return [{"title": "Search Error", "snippet": str(e), "url": "", "source": "error"}]


async def _fallback_search(query: str, max_results: int = 5) -> List[Dict]:
    """Fallback: scrape DuckDuckGo HTML results."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; RAGBot/1.0)"}
            )
            html = response.text

        # Simple extraction without BeautifulSoup
        results = []
        import re

        # Extract result snippets
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
        urls = re.findall(r'class="result__url"[^>]*>(.*?)</span>', html, re.DOTALL)

        for i in range(min(max_results, len(snippets))):
            # Clean HTML tags
            snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            title = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else ""
            url = urls[i].strip() if i < len(urls) else ""
            if snippet:
                results.append({
                    "title": title,
                    "snippet": snippet,
                    "url": url,
                    "source": "DuckDuckGo"
                })

        return results

    except Exception as e:
        return [{"title": "Search Error", "snippet": str(e), "url": "", "source": "error"}]