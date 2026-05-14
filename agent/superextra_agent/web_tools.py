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
import re
import time
from urllib.parse import urlparse, urlunparse

import httpx

from .cloud_logging import emit_cloud_log
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


def _log_fetch_url(
    *,
    result: dict,
    url: str,
    original_url: str | None,
    duration_ms: int,
    cached: bool,
    unwrap_miss: bool,
) -> None:
    """Emit one structured `fetch_url` Cloud Logging entry per fetch attempt.

    One line per call (cache hit or fresh) with the canonical URL, the
    pre-unwrap URL when vertex unwrap rewrote it, status, error_reason
    tag, duration, cached marker, and (on success) content size in bytes.
    """
    status = result.get("status")
    error_reason: str | None = None
    content_chars: int | None = None

    if status == "success":
        content_chars = len(result.get("content", "") or "")
    else:
        # `unwrap_miss` dominates: when we tried to unwrap a vertex URL
        # and got no Location, the downstream Jina call was fetching the
        # redirect page itself and any error it produced is a derived
        # symptom of the unwrap failure. Tag the root cause instead.
        error_reason = "vertex_unwrap_miss" if unwrap_miss else result.get("_error_reason")

    emit_cloud_log(
        "fetch_url",
        run_id=_fetch_run_id_var.get(),
        url=url,
        original_url=original_url,
        status=status,
        error_reason=error_reason,
        duration_ms=duration_ms,
        cached=cached,
        content_chars=content_chars,
    )


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


def _detect_upstream_block(content: str) -> tuple[str, str] | None:
    """Detect upstream errors and content-extraction misses in Jina's body.

    Returns a `(human_message, reason_tag)` pair so callers get both a
    user-facing description and a stable tag for structured logging.
    Without this check those bodies look like successful fetches with
    ~300 chars of error text, and the model treats blocked sites as
    having "no content" instead of trying a different source. Also
    catches readerlm-v2 meta-commentary like "(Note: The provided HTML
    contains an iframe…)" which signals the cleaner couldn't extract
    usable content.
    """
    head = content[:500]
    upstream = re.search(r"Target URL returned error (\d{3})", head)
    if upstream:
        code = upstream.group(1)
        return f"upstream HTTP {code}", f"upstream_http_{code}"
    if "requiring CAPTCHA" in head:
        return "upstream requires CAPTCHA", "upstream_captcha"
    if "Just a moment" in head and len(content) < 2000:
        return "Cloudflare interstitial", "cloudflare_interstitial"
    if "(Note: The provided HTML" in content and len(content) < 1500:
        return "readerlm could not extract content (iframe / SPA)", "iframe_spa"
    # Generic thin-content guard. Real article bodies almost always have
    # at least one paragraph line >120 chars; navigation lists, paywall
    # gates, and section-index pages don't. Avoids the model retrying
    # path variants when Jina returns a near-empty stub.
    if len(content) < 800:
        longest_line = max((len(line) for line in content.splitlines()), default=0)
        if longest_line < 120:
            return "extracted content too thin to be an article body", "thin_content"
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
    """Read a web page's body. Every URL you intend to cite must come
    through this tool — `google_search` discovers URLs; it does not
    return them as evidence.

    Returns the page text as Markdown with navigation, cookie banners,
    and ads stripped. Tables come through as pipe-syntax tables. Use
    `fetch_web_content_batch` for several URLs in parallel.

    Args:
        url: The full URL to fetch (e.g. 'https://reddit.com/r/coffee/comments/abc123').
    """
    original_url = url
    started = time.monotonic()
    was_vertex_redirect = _is_vertex_redirect(url)

    unwrapped_url = await _unwrap_vertex_redirect(url)
    unwrap_miss = was_vertex_redirect and unwrapped_url == original_url
    vertex_rewrote = was_vertex_redirect and not unwrap_miss

    url = _strip_fragment(unwrapped_url)
    log_original = original_url if vertex_rewrote else None

    cache_key = _cache_key(url)
    if cache_key is not None and cache_key in _fetch_cache:
        cached = dict(_fetch_cache[cache_key])
        cached["cached"] = True
        _log_fetch_url(
            result=cached,
            url=url,
            original_url=log_original,
            duration_ms=int((time.monotonic() - started) * 1000),
            cached=True,
            unwrap_miss=unwrap_miss,
        )
        cached.pop("_error_reason", None)
        return cached

    result = await _fetch_uncached(url)

    # Cache every outcome — including errors — so the model doesn't
    # refetch a URL that already returned thin content, an HTTP error,
    # or a domain-root rejection within the same run. Caching successes
    # only leaves the diagnosed retry loop alive.
    if cache_key is not None:
        _cache_put(cache_key, dict(result))

    _log_fetch_url(
        result=result,
        url=url,
        original_url=log_original,
        duration_ms=int((time.monotonic() - started) * 1000),
        cached=False,
        unwrap_miss=unwrap_miss,
    )
    result.pop("_error_reason", None)
    return result


async def _fetch_uncached(url: str) -> dict:
    """Fetch logic without unwrap or cache. Always returns a dict.

    Error returns carry a private `_error_reason` field with a stable
    tag for structured logging. The caller is expected to log it and
    then pop it before returning to the model.
    """
    parsed = urlparse(url)
    if not parsed.path or parsed.path == "/":
        return {
            "status": "error",
            "error_message": (
                f"{url} is a domain root, not an article. Search for the "
                "specific article URL and pass that instead."
            ),
            "_error_reason": "domain_root",
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
                "_error_reason": f"http_{resp.status_code}",
            }

        content = resp.text
        block = _detect_upstream_block(content)
        if block:
            message, reason = block
            return {
                "status": "error",
                "error_message": f"Could not read {url}: {message}",
                "_error_reason": reason,
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
            "_error_reason": "timeout",
        }
    except httpx.RequestError as e:
        # Connect, read, network, DNS, etc. — anything httpx classifies
        # as a request-side error short of HTTPStatusError (which we
        # don't trigger because we don't call raise_for_status).
        return {
            "status": "error",
            "error_message": f"Network error fetching {url}: {e}",
            "_error_reason": "network_error",
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "_error_reason": "exception",
        }


async def fetch_web_content_batch(urls: list[str]) -> dict:
    """Read multiple web page bodies in parallel. Every URL you intend
    to cite must come through this tool (or `fetch_web_content`) —
    `google_search` discovers URLs; it does not return them as evidence.

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
