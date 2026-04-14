import atexit
import logging
import os
import httpx

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"
ACTOR_ID = "automation-lab~google-maps-reviews-scraper"

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


def _build_maps_url(name: str, address: str) -> str:
    """Build a Google Maps place URL from name and address."""
    query = f"{name}, {address}".replace(" ", "+")
    return f"https://www.google.com/maps/place/{query}/"


async def get_google_reviews(
    name: str, address: str, max_reviews: int = 50
) -> dict:
    """Fetch Google Maps reviews for a restaurant.

    Returns structured reviews with text, ratings, dates, and reviewer info.
    Uses the restaurant name and full address from Places context — no matching needed.

    Args:
        name: Restaurant name (e.g. 'Wanderlust Speciality Coffee').
              Found in the Places context displayName.
        address: Full street address (e.g. 'Ząbkowska 27/29, 03-736 Warszawa, Poland').
                 Found in the Places context formattedAddress.
        max_reviews: Maximum number of reviews to fetch (default 50, max 200).
    """
    try:
        client = _get_client()
        api_key = _get_api_key()
        max_reviews = min(max_reviews, 200)

        place_url = _build_maps_url(name, address)

        # Use synchronous run endpoint — waits for completion and returns dataset
        resp = await client.post(
            f"{APIFY_BASE}/acts/{ACTOR_ID}/run-sync-get-dataset-items",
            params={"token": api_key},
            json={
                "placeUrls": [place_url],
                "maxReviewsPerPlace": max_reviews,
                "sortBy": "newest",
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
                "error_message": f"No Google reviews found for '{name}'",
            }

        reviews = []
        for item in items:
            review = {
                "text": item.get("text") or item.get("textTranslated", ""),
                "rating": item.get("stars"),
                "date": item.get("publishedAt", ""),
                "language": item.get("originalLanguage") or item.get("language", ""),
                "is_local_guide": item.get("isLocalGuide", False),
                "likes": item.get("likesCount", 0),
            }
            owner_resp = item.get("responseFromOwnerText")
            if owner_resp:
                review["owner_response"] = owner_resp
            reviews.append(review)

        return {
            "status": "success",
            "name": name,
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
