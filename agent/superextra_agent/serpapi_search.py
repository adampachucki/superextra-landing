"""SerpAPI-backed Google search for specialist URL discovery.

`google_search` (Gemini grounding) reliably finds IG/FB URLs but hangs
or fails on TripAdvisor (controlled A/B 2026-05-21: 2/10 found, 8/10
timeouts past 90s, even with neutral prompting). SerpAPI's general
Google engine returns the same TripAdvisor URLs as the specialized
TA engine (9/10 agreement) and matches Gemini hit rate on IG/FB —
all while running in 1-3s instead of 7-90s.

Used by social_analyst (IG/FB/TA URL discovery) and review_analyst
(TripAdvisor Restaurant_Review URL discovery before pulling reviews
via get_tripadvisor_reviews). One reliable discovery backend instead
of mixing grounding + specialized resolvers per platform.
"""
from urllib.parse import urlparse

import httpx

from .http_client import LazyAsyncClient
from .secrets import get_secret

SERPAPI_BASE = "https://serpapi.com/search.json"
TIMEOUT_S = 30.0
DEFAULT_NUM_RESULTS = 10

_get_client = LazyAsyncClient(timeout=TIMEOUT_S)


def _domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").replace("www.", "").lower()
    except Exception:
        return ""


async def search_serpapi(query: str, location: str = "") -> dict:
    """Search the web for a venue's platform-profile URLs via SerpAPI's
    Google engine. Returns ranked organic results — title, url, snippet,
    domain — suitable for picking the right profile URL to pass into a
    platform fetcher (TripAdvisor, Facebook, Instagram).

    Use this for finding social-platform URLs. Examples:
      search_serpapi('Monsun Gdynia tripadvisor')
      search_serpapi('Monsun Gdynia instagram')
      search_serpapi('Le Bernardin New York facebook')

    Args:
        query: The search query. Include the venue name, the city/area,
            and the platform keyword (tripadvisor / instagram / facebook).
        location: Optional Google-Search location string (e.g.
            "Gdynia, Poland") to bias ranking toward a geographic area.
            Omit when the query already includes the city.
    """
    try:
        api_key = get_secret("SERPAPI_API_KEY")
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error_message": f"SERPAPI_API_KEY not available: {e}"}

    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": DEFAULT_NUM_RESULTS,
    }
    if location:
        params["location"] = location

    try:
        resp = await _get_client().get(SERPAPI_BASE, params=params)
    except httpx.TimeoutException:
        return {"status": "error", "error_message": f"SerpAPI timed out after {TIMEOUT_S}s"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error_message": str(e)}

    if resp.status_code != 200:
        return {
            "status": "error",
            "error_message": f"SerpAPI HTTP {resp.status_code}: {resp.text[:200]}",
        }

    organic = resp.json().get("organic_results") or []
    results = []
    for r in organic:
        link = r.get("link") or ""
        if not link:
            continue
        results.append({
            "position": r.get("position"),
            "title": r.get("title", ""),
            "url": link,
            "snippet": r.get("snippet", ""),
            "domain": _domain(link),
        })

    return {"status": "success", "query": query, "results": results}
