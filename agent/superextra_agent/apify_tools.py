import atexit
import logging
import os
import httpx

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"
ACTOR_ID = "compass~google-maps-reviews-scraper"

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        # Sync endpoint can take a while — generous timeout
        _client = httpx.AsyncClient(timeout=120.0)
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


def _get_api_key() -> str:
    key = os.environ.get("APIFY_TOKEN", "")
    if not key:
        raise RuntimeError("APIFY_TOKEN environment variable is not set")
    return key


async def get_google_reviews(place_id: str, max_reviews: int = 50, tool_context=None) -> dict:
    """Fetch Google Maps reviews for a restaurant using its Place ID.

    Returns structured reviews with text, ratings, dates, and reviewer info.
    Uses the Google Maps Place ID directly — no name matching needed.

    Args:
        place_id: Google Places ID (e.g. 'ChIJMRpv9_HNHkcRdzbAYDXx7fc').
                  Found in the Places context data.
        max_reviews: Maximum number of reviews to fetch (default 50, max 200).
    """
    try:
        client = _get_client()
        api_key = _get_api_key()
        max_reviews = min(max_reviews, 200)

        # Use synchronous run endpoint — waits for completion and returns dataset
        resp = await client.post(
            f"{APIFY_BASE}/acts/{ACTOR_ID}/run-sync-get-dataset-items",
            params={"token": api_key},
            json={
                "placeIds": [place_id],
                "maxReviews": max_reviews,
                "reviewsSort": "newest",
            },
            timeout=120.0,
        )

        if resp.status_code not in (200, 201):
            return {
                "status": "error",
                "error_message": f"Apify API error {resp.status_code}: {resp.text[:500]}",
            }

        items = resp.json()
        if not isinstance(items, list):
            return {
                "status": "error",
                "error_message": "Unexpected Apify response format",
            }
        if not items:
            return {
                "status": "error",
                "error_message": f"No Google reviews found for place {place_id}",
            }

        reviews = []
        for item in items:
            review = {
                "text": item.get("text") or item.get("textTranslated", ""),
                "rating": item.get("stars"),
                "date": item.get("publishedAtDate") or item.get("publishAt", ""),
                "language": item.get("originalLanguage") or item.get("language", ""),
                "is_local_guide": item.get("isLocalGuide", False),
                "likes": item.get("likesCount", 0),
            }
            owner_resp = item.get("responseFromOwnerText")
            if owner_resp:
                review["owner_response"] = owner_resp
            reviews.append(review)

        # Attach a provider source entry pointing at the Google Maps page.
        # URL is the deterministic `googleMapsUri` captured by
        # `get_restaurant_details` for the target place; skip silently if
        # the state key is absent (e.g. tool called for a non-target
        # competitor), since we have no reliable URL to cite.
        if tool_context and reviews:
            maps_uri = tool_context.state.get("_target_google_maps_uri")
            if maps_uri:
                existing = tool_context.state.get("temp:_tool_sources", []) or []
                tool_context.state["temp:_tool_sources"] = existing + [{
                    "title": f"Google Reviews ({len(reviews)} reviews analysed)",
                    "url": maps_uri,
                    "domain": "google.com",
                }]

        return {
            "status": "success",
            "place_id": place_id,
            "total_fetched": len(reviews),
            "reviews": reviews,
        }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "error_message": "Apify actor timed out after 120s — try with fewer reviews",
        }
    except Exception as e:
        return {"status": "error", "error_message": str(e)}
