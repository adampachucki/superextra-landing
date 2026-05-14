"""Fetch web pages as clean Markdown via Jina Reader (r.jina.ai).

`X-Respond-With: readerlm-v2` runs Jina's content-cleaning model so cookie
banners, navigation, ad fluff, and tracking pixels don't eat the response
budget — the practical difference can be 60 KB of GDPR boilerplate vs
6 KB of actual page content. JSON values, prices, and tables survive as
Markdown.
"""
import asyncio
import atexit
import httpx

from .secrets import get_secret

JINA_BASE = "https://r.jina.ai"
MAX_CONTENT_LENGTH = 50_000
TIMEOUT_S = 60.0
# `readerlm-v2` is auth-only and ~25s per page; cap batch fanout so a
# confused model can't kick off 50+ paid LM calls in a single tool turn.
MAX_BATCH = 10

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=TIMEOUT_S)
    return _client


def _cleanup_client():
    global _client
    if _client is not None:
        try:
            asyncio.run(_client.aclose())
        except RuntimeError:
            pass
        _client = None


atexit.register(_cleanup_client)


def _detect_upstream_block(content: str) -> str | None:
    """Jina forwards upstream HTTP errors as 200-OK Markdown bodies.

    Without this check those bodies look like successful fetches with ~300
    chars of error text, and the model treats blocked sites as having "no
    content" instead of trying a different source. Also catches readerlm-v2
    meta-commentary like "(Note: The provided HTML contains an iframe…)"
    which signals the cleaner couldn't extract usable content.
    """
    head = content[:500]
    for code in ("400", "401", "403", "404", "451", "500", "502", "503"):
        if f"Target URL returned error {code}" in head:
            return f"upstream HTTP {code}"
    if "requiring CAPTCHA" in head:
        return "upstream requires CAPTCHA"
    if "Just a moment" in head and len(content) < 2000:
        return "Cloudflare interstitial"
    if "(Note: The provided HTML" in content and len(content) < 1500:
        return "readerlm could not extract content (iframe / SPA)"
    return None


async def fetch_web_content(url: str) -> dict:
    """Read the body of a web page. REQUIRED before citing any URL.

    google_search returns ~200-char snippet previews, not evidence.
    Dates, prices, named entities, quoted text, full article
    arguments, comment threads, and anything below the page fold are
    NOT in the snippet. You cannot answer "what opened or closed
    recently", "what does the article say", "what did the reviewer
    write", or any factual claim from snippets.

    Call this on every URL you intend to cite. Use
    fetch_web_content_batch for several URLs in parallel.

    Returns the page text as Markdown with navigation, cookie
    banners, and ads stripped. Tables come through as pipe-syntax
    tables.

    Args:
        url: The full URL to fetch (e.g. 'https://reddit.com/r/coffee/comments/abc123').
    """
    try:
        headers = {
            "Accept": "text/markdown",
            "X-Respond-With": "readerlm-v2",
            "Authorization": f"Bearer {get_secret('JINA_API_KEY')}",
        }

        resp = await _get_client().get(
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
        block = _detect_upstream_block(content)
        if block:
            return {
                "status": "error",
                "error_message": f"Could not read {url}: {block}",
            }

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


async def fetch_web_content_batch(urls: list[str]) -> dict:
    """Read multiple URLs in parallel. REQUIRED before citing any URL.

    Same evidence rules as fetch_web_content: google_search snippets
    are link previews, not evidence. Every URL you intend to cite
    must pass through this tool (or fetch_web_content). Fetching N
    URLs in parallel takes the time of the slowest one rather than
    the sum.

    Each result is the same shape as `fetch_web_content`. Capped at
    10 URLs per call; pick the most relevant ones.

    Args:
        urls: List of full URLs to fetch (max 10).
    """
    if not urls:
        return {"status": "error", "error_message": "urls is empty"}
    if len(urls) > MAX_BATCH:
        return {
            "status": "error",
            "error_message": (
                f"Too many URLs ({len(urls)}); max {MAX_BATCH} per call. "
                "Pick the most relevant ones or split into multiple calls."
            ),
        }
    results = await asyncio.gather(*(fetch_web_content(u) for u in urls))
    return {"status": "success", "results": results}
