import atexit
import os
import httpx

JINA_BASE = "https://r.jina.ai"
MAX_CONTENT_LENGTH = 15_000

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


def _cleanup_client():
    global _client
    if _client is not None:
        try:
            import asyncio
            asyncio.run(_client.aclose())
        except RuntimeError:
            pass
        _client = None


atexit.register(_cleanup_client)


async def fetch_web_content(url: str) -> dict:
    """Fetch and read the content of a web page as clean Markdown.

    Use this to read the full content of a page found via google_search —
    articles, blog posts, forum threads, Reddit discussions, etc.
    Returns the page text as Markdown, stripped of navigation and ads.

    Args:
        url: The full URL to fetch (e.g. 'https://reddit.com/r/coffee/comments/abc123').
    """
    try:
        client = _get_client()
        headers = {
            "Accept": "text/markdown",
        }
        api_key = os.environ.get("JINA_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        resp = await client.get(
            f"{JINA_BASE}/{url}",
            headers=headers,
            follow_redirects=True,
        )

        if resp.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Failed to fetch {url}: HTTP {resp.status_code}",
            }

        content = resp.text
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated]"

        return {
            "status": "success",
            "url": url,
            "content": content,
        }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "error_message": f"Timeout fetching {url}",
        }
    except Exception as e:
        return {"status": "error", "error_message": str(e)}
