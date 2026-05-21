import re

import httpx

from .place_state import tool_source_key
from .secrets import get_secret

BASE_URL = "https://serpapi.com/search.json"

# Anchored to /Restaurant_Review explicitly — Hotel_Review and Attraction_Review
# URLs are not valid inputs to SerpAPI's `tripadvisor_reviews` engine. The `slug`
# group is consumed by firestore_events for human-readable timeline labels.
_TA_REVIEW_RE = re.compile(
    r"/Restaurant_Review-g\d+-d(?P<place_id>\d+)-Reviews(?:-or\d+)?-(?P<slug>[^/]+?)\.html",
    re.IGNORECASE,
)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


def _get_api_key() -> str:
    return get_secret("SERPAPI_API_KEY")


async def get_tripadvisor_reviews(url: str, num_pages: int = 5, tool_context=None) -> dict:
    """Fetch TripAdvisor reviews for a restaurant page.

    Returns full review text, ratings, trip types, reviewer origins, and
    owner-response flags. Each page returns 10 reviews. Default is 5 pages
    (50 reviews); max 10 pages.

    The URL must come from a `search_serpapi` result.

    Args:
        url: Full TripAdvisor Restaurant_Review page URL from a search result.
        num_pages: Number of pages to fetch (10 reviews each). Default 5, max 10.
    """
    try:
        match = _TA_REVIEW_RE.search(url or "")
        if not match:
            return {
                "status": "error",
                "error_message": f"URL is not a TripAdvisor Restaurant_Review page: {url}",
            }
        place_id = match.group("place_id")

        client = _get_client()
        api_key = _get_api_key()
        num_pages = min(num_pages, 10)

        all_reviews = []
        total_reviews = None

        for page in range(num_pages):
            resp = await client.get(BASE_URL, params={
                "engine": "tripadvisor_reviews",
                "place_id": place_id,
                "offset": page * 10,
                "api_key": api_key,
            })
            if resp.status_code != 200:
                return {"status": "error", "error_message": f"SerpAPI reviews error {resp.status_code}: {resp.text}"}

            data = resp.json()
            if total_reviews is None:
                total_reviews = data.get("search_information", {}).get("total_reviews")

            reviews = data.get("reviews", [])
            if not reviews:
                break  # No more reviews

            for r in reviews:
                review = {
                    "title": r.get("title"),
                    "text": r.get("snippet"),
                    "rating": r.get("rating"),
                    "date": r.get("date"),
                    "original_language": r.get("original_language"),
                }
                trip_info = r.get("trip_info", {})
                if trip_info:
                    review["trip_type"] = trip_info.get("type")
                    review["travel_date"] = trip_info.get("date")
                author = r.get("author", {})
                if author.get("hometown"):
                    review["author_hometown"] = author["hometown"]
                review["votes"] = r.get("votes", 0)
                review["has_owner_response"] = "response" in r
                all_reviews.append(review)

        if tool_context is not None:
            tool_context.state[tool_source_key("tripadvisor", url)] = {
                "provider": "tripadvisor",
                "title": "TripAdvisor",
                "url": url,
                "domain": "tripadvisor.com",
            }

        return {
            "status": "success",
            "url": url,
            "place_id": place_id,
            "total_reviews": total_reviews,
            "fetched_reviews": len(all_reviews),
            "reviews": all_reviews,
        }
    except Exception as e:
        return {"status": "error", "error_message": str(e)}
