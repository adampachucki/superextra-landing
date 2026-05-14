"""Fetch web pages as clean Markdown via Jina Reader (r.jina.ai).

`X-Respond-With: readerlm-v2` runs Jina's content-cleaning model so cookie
banners, navigation, ad fluff, and tracking pixels don't eat the response
budget — the practical difference can be 60 KB of GDPR boilerplate vs
6 KB of actual page content. JSON values, prices, and tables survive as
Markdown.
"""
import asyncio
import atexit
import contextvars
from urllib.parse import urlparse, urlunparse

import httpx

from .secrets import get_secret

JINA_BASE = "https://r.jina.ai"
MAX_CONTENT_LENGTH = 50_000
TIMEOUT_S = 60.0
# `readerlm-v2` is auth-only and ~25s per page; cap batch fanout so a
# confused model can't kick off 50+ paid LM calls in a single tool turn.
MAX_BATCH = 10

# Gemini grounding exposes article URLs as tokenized redirects on
# `https://vertexaisearch.cloud.google.com/grounding-api-redirect/...`.
# Jina does not unwrap these cleanly — it fetches the redirect page
# itself, not the article — so callers see junk content and retry. We
# resolve the redirect to the real URL before sending it to Jina.
VERTEX_REDIRECT_HOST = "vertexaisearch.cloud.google.com"
VERTEX_REDIRECT_PATH_PREFIX = "/grounding-api-redirect/"
VERTEX_UNWRAP_TIMEOUT_S = 10.0


def _is_vertex_redirect(url: str) -> bool:
    """True if `url` is a Vertex grounding-api-redirect URL.

    Exact parsed check on scheme/host/path — a substring match would
    fire on attacker-controlled URLs that merely embed the redirect
    prefix in a query string or fragment, turning the unwrap step into
    an SSRF-shaped GET from inside Agent Engine.
    """
    try:
        p = urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    return (
        p.scheme == "https"
        and p.hostname == VERTEX_REDIRECT_HOST
        and p.path.startswith(VERTEX_REDIRECT_PATH_PREFIX)
    )

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


# ── Per-run fetch cache ──────────────────────────────────────────────────────
# Same URL fetched twice in one run → second call returns the cached
# result. Stops the dance where the model refetches a URL after a thin or
# blocked response. Cache lives module-global but is keyed by run_id, set
# via a contextvar by FirestoreProgressPlugin's before_run_callback.

_fetch_run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_fetch_run_id", default=None
)
_fetch_cache: dict[tuple[str, str], dict] = {}
# Bounded so that a run whose `after_run_callback` doesn't fire (ADK
# 1.28.0 doesn't call it from a `finally`, so cancelled/aborted runs
# can skip cleanup) cannot grow the cache forever. FIFO eviction by
# insertion order — dict preserves order in 3.7+.
_FETCH_CACHE_MAX_SIZE = 500


def set_fetch_run_id(run_id: str) -> None:
    """Bind the active run id to this asyncio task's context.

    Called once at the start of each Agent Engine invocation. Subsequent
    `fetch_web_content[_batch]` calls inside that task share a per-run
    result cache keyed by (run_id, url).
    """
    _fetch_run_id_var.set(run_id)


def clear_fetch_cache_for_run(run_id: str) -> None:
    """Drop all cached fetch results for one run."""
    for key in [k for k in _fetch_cache if k[0] == run_id]:
        _fetch_cache.pop(key, None)


def _cache_key(url: str) -> tuple[str, str] | None:
    run_id = _fetch_run_id_var.get()
    return (run_id, url) if run_id else None


def _cache_put(key: tuple[str, str], result: dict) -> None:
    while len(_fetch_cache) >= _FETCH_CACHE_MAX_SIZE:
        # Evict oldest insertion (FIFO).
        _fetch_cache.pop(next(iter(_fetch_cache)))
    _fetch_cache[key] = result


def _strip_fragment(url: str) -> str:
    """Drop a URL fragment so `page#a` and `page#b` collapse to one key.

    Fragments are not sent to the origin, so they cannot change the
    fetched content — caching them as distinct keys is a false miss.
    """
    try:
        p = urlparse(url)
    except Exception:  # noqa: BLE001
        return url
    if not p.fragment:
        return url
    return urlunparse(p._replace(fragment=""))


# ── Block detection ──────────────────────────────────────────────────────────


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
    # Generic thin-content guard. Real article bodies almost always have
    # at least one paragraph line >120 chars; navigation lists, paywall
    # gates, and section-index pages don't. Avoids the model retrying
    # path variants when Jina returns a near-empty stub.
    if len(content) < 800:
        longest_line = max((len(line) for line in content.splitlines()), default=0)
        if longest_line < 120:
            return "extracted content too thin to be an article body"
    return None


# ── Vertex grounding redirect unwrap ────────────────────────────────────────


async def _unwrap_vertex_redirect(url: str) -> str:
    """Resolve a Vertex grounding-redirect URL to its destination.

    Returns the original URL when the input is not a Vertex redirect or
    when resolution fails — Jina will then receive the original URL and
    its own error/thin-content path handles the bad result.
    """
    if not _is_vertex_redirect(url):
        return url
    try:
        resp = await _get_client().get(
            url, follow_redirects=False, timeout=VERTEX_UNWRAP_TIMEOUT_S
        )
        loc = resp.headers.get("Location") or resp.headers.get("location")
        if loc:
            return loc
    except Exception:  # noqa: BLE001 — fall back to original URL on any failure
        pass
    return url


# ── Fetch tools ─────────────────────────────────────────────────────────────


async def fetch_web_content(url: str) -> dict:
    """Read the body of a web page.

    Returns the page text as Markdown with navigation, cookie banners,
    and ads stripped. Tables come through as pipe-syntax tables.

    Use this on URLs you want to read the full article body of — news
    pieces, blog posts, forum threads, restaurant pages — when the
    snippet from `google_search` is not enough. Use
    `fetch_web_content_batch` for several URLs in parallel.

    Args:
        url: The full URL to fetch (e.g. 'https://reddit.com/r/coffee/comments/abc123').
    """
    url = await _unwrap_vertex_redirect(url)
    url = _strip_fragment(url)

    cache_key = _cache_key(url)
    if cache_key is not None and cache_key in _fetch_cache:
        cached = dict(_fetch_cache[cache_key])
        cached["cached"] = True
        return cached

    result = await _fetch_uncached(url)

    # Cache every outcome — including errors — so the model doesn't
    # refetch a URL that already returned thin content, an HTTP error,
    # or a domain-root rejection within the same run. Caching successes
    # only leaves the diagnosed retry loop alive.
    if cache_key is not None:
        _cache_put(cache_key, result)
    return result


async def _fetch_uncached(url: str) -> dict:
    """Fetch logic without unwrap or cache. Always returns a dict."""
    parsed = urlparse(url)
    if not parsed.path or parsed.path == "/":
        return {
            "status": "error",
            "error_message": (
                f"{url} is a domain root, not an article. Search for the "
                "specific article URL and pass that instead."
            ),
        }

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
    """Read multiple URLs in parallel. Returns one result per URL.

    Fetching N URLs in parallel takes the time of the slowest one rather
    than the sum. Each result is the same shape as `fetch_web_content`.
    Capped at 10 URLs per call; pick the most relevant ones.

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
