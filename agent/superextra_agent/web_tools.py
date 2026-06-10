"""Source URL canonicalization for the source drawer.

Gemini grounding exposes article URLs as tokenized redirects on
`https://vertexaisearch.cloud.google.com/grounding-api-redirect/...`.
`resolve_source_display_url` unwraps those to the real destination and
canonicalizes the result so the UI can show and dedupe a stable public URL.
"""
from typing import Any
from urllib.parse import urlparse, urlunparse

from .http_client import LazyAsyncClient

TIMEOUT_S = 15.0

# Gemini grounding exposes article URLs as tokenized redirects on
# vertexaisearch.cloud.google.com/grounding-api-redirect/... — resolve them to
# the real article URL before showing or deduping a source.
VERTEX_REDIRECT_HOST = "vertexaisearch.cloud.google.com"
VERTEX_REDIRECT_PATH_PREFIX = "/grounding-api-redirect/"
VERTEX_UNWRAP_TIMEOUT_S = 5.0

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


_get_client = LazyAsyncClient(timeout=TIMEOUT_S)


def _strip_fragment(url: str) -> str:
    """Drop a URL fragment so `page#a` and `page#b` collapse to one URL.

    Fragments are not sent to the origin, so they cannot change the
    fetched content — treating them as distinct is a false miss.
    """
    try:
        p = urlparse(url)
    except Exception:  # noqa: BLE001
        return url
    if not p.fragment:
        return url
    return urlunparse(p._replace(fragment=""))


def _is_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _canonical_source_url(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    url = _strip_fragment(raw.strip())
    return url if _is_http_url(url) else None


async def _unwrap_vertex_redirect(url: str) -> str:
    """Resolve a Vertex grounding-redirect URL to its destination.

    Returns the original URL when the input is not a Vertex redirect or
    when resolution fails.
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


async def resolve_source_display_url(raw: Any) -> str | None:
    """Return the public URL to show/dedupe for a source drawer entry."""
    url = _canonical_source_url(raw)
    if url is None:
        return None
    return _canonical_source_url(await _unwrap_vertex_redirect(url)) or url
