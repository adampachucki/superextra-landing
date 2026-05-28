import re

import httpx

from .apify_tools import _run_actor_sync
from .place_state import tool_source_key
from .secrets import get_secret

BASE_URL = "https://serpapi.com/search.json"
TRIPADVISOR_REVIEWS_ACTOR = "maxcopell~tripadvisor-reviews"
SERPAPI_PAGE_SIZE = 10
TRIPADVISOR_FAST_MAX_REVIEWS = 100
TRIPADVISOR_DEEP_MAX_REVIEWS = 300

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


def _emit_tripadvisor_source(tool_context, url: str) -> None:
    if tool_context is not None:
        tool_context.state[tool_source_key("tripadvisor", url)] = {
            "provider": "tripadvisor",
            "title": "TripAdvisor",
            "url": url,
            "domain": "tripadvisor.com",
        }


def _trim_serpapi_review(review: dict) -> dict:
    out = {
        "title": review.get("title"),
        "text": review.get("snippet"),
        "rating": review.get("rating"),
        "date": review.get("date"),
        "original_language": review.get("original_language"),
    }
    trip_info = review.get("trip_info", {})
    if isinstance(trip_info, dict) and trip_info:
        out["trip_type"] = trip_info.get("type")
        out["travel_date"] = trip_info.get("date")
    author = review.get("author", {})
    if isinstance(author, dict):
        if author.get("hometown"):
            out["author_hometown"] = author["hometown"]
        if author.get("contributions") is not None:
            out["author_contributions"] = author.get("contributions")
    out["votes"] = review.get("votes", 0)
    out["has_owner_response"] = "response" in review
    return out


def _trim_tripadvisor_place_info(place_info: dict | None) -> dict:
    if not isinstance(place_info, dict):
        return {}
    keep = (
        "id",
        "name",
        "rating",
        "numberOfReviews",
        "locationString",
        "webUrl",
        "website",
        "address",
        "ratingHistogram",
    )
    return {k: place_info[k] for k in keep if k in place_info}


def _author_contributions(contributions) -> int | None:
    if isinstance(contributions, int) and not isinstance(contributions, bool):
        return contributions
    if not isinstance(contributions, dict):
        return None
    total = contributions.get("totalContributions")
    if isinstance(total, int) and not isinstance(total, bool):
        return total
    numeric = [
        value
        for value in contributions.values()
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    if numeric:
        return sum(numeric)
    return None


def _trim_apify_review(item: dict) -> dict:
    out = {
        "title": item.get("title"),
        "text": item.get("text"),
        "rating": item.get("rating"),
        "date": item.get("publishedDate"),
        "original_language": item.get("originalLanguage") or item.get("lang"),
        "trip_type": item.get("tripType"),
        "travel_date": item.get("travelDate"),
        "votes": item.get("helpfulVotes", 0),
        "has_owner_response": bool(item.get("ownerResponse")),
    }
    user = item.get("user")
    if isinstance(user, dict):
        location = user.get("userLocation")
        if isinstance(location, dict) and location.get("name"):
            out["author_hometown"] = location["name"]
        contributions = _author_contributions(user.get("contributions"))
        if contributions is not None:
            out["author_contributions"] = contributions
    owner_response = item.get("ownerResponse")
    if isinstance(owner_response, dict) and owner_response:
        out["owner_response"] = {
            k: owner_response[k]
            for k in ("text", "publishedDate", "lang")
            if k in owner_response
        }
    subratings = item.get("subratings")
    if isinstance(subratings, list) and subratings:
        out["subratings"] = subratings
    photos = item.get("photos")
    if isinstance(photos, list) and photos:
        out["photo_count"] = len(photos)
    return out


async def _fetch_tripadvisor_reviews_serpapi(
    *,
    url: str,
    place_id: str,
    max_reviews: int,
) -> dict:
    client = _get_client()
    api_key = _get_api_key()
    target = min(max_reviews, TRIPADVISOR_FAST_MAX_REVIEWS)
    pages = (target + SERPAPI_PAGE_SIZE - 1) // SERPAPI_PAGE_SIZE

    all_reviews = []
    total_reviews = None

    for page in range(pages):
        resp = await client.get(BASE_URL, params={
            "engine": "tripadvisor_reviews",
            "place_id": place_id,
            "offset": page * SERPAPI_PAGE_SIZE,
            "api_key": api_key,
        })
        if resp.status_code != 200:
            return {
                "status": "error",
                "error_message": f"SerpAPI reviews error {resp.status_code}: {resp.text}",
            }

        data = resp.json()
        if total_reviews is None:
            total_reviews = data.get("search_information", {}).get("total_reviews")

        reviews = data.get("reviews", [])
        if not reviews:
            if page == 0 and data.get("error"):
                return {
                    "status": "error",
                    "error_message": f"SerpAPI reviews error: {data['error']}",
                }
            break

        for review in reviews:
            if isinstance(review, dict):
                all_reviews.append(_trim_serpapi_review(review))
                if len(all_reviews) >= target:
                    break
        if len(all_reviews) >= target:
            break

    return {
        "status": "success",
        "url": url,
        "place_id": place_id,
        "backend": "serpapi",
        "total_reviews": total_reviews,
        "fetched_reviews": len(all_reviews),
        "reviews": all_reviews,
    }


async def _fetch_tripadvisor_reviews_apify(
    *,
    url: str,
    place_id: str,
    max_reviews: int,
) -> dict:
    target = min(max_reviews, TRIPADVISOR_DEEP_MAX_REVIEWS)
    result = await _run_actor_sync(
        TRIPADVISOR_REVIEWS_ACTOR,
        {
            "startUrls": [{"url": url}],
            "maxReviews": target,
            "scrapeReviewerInfo": True,
            "disableMachineTranslations": True,
        },
    )
    if result["status"] != "success":
        return result

    items = [i for i in result["items"] if isinstance(i, dict)]
    place_info = next(
        (i.get("placeInfo") for i in items if isinstance(i.get("placeInfo"), dict)),
        {},
    )
    trimmed_place_info = _trim_tripadvisor_place_info(place_info)

    return {
        "status": "success",
        "url": url,
        "place_id": place_id,
        "backend": "apify",
        "total_reviews": trimmed_place_info.get("numberOfReviews"),
        "fetched_reviews": len(items),
        "place_info": trimmed_place_info,
        "reviews": [_trim_apify_review(item) for item in items],
    }


async def get_tripadvisor_reviews(
    url: str,
    max_reviews: int = 50,
    mode: str = "fast",
    tool_context=None,
) -> dict:
    """Fetch TripAdvisor reviews for a restaurant page.

    Default `mode="fast"` uses SerpAPI for up to 50 reviews. It can fetch up to
    100 reviews on the fast path when requested. Use
    `mode="deep"` or `max_reviews > 100` when owner responses, deeper history,
    subratings, or the place rating histogram matter; that path uses Apify and
    returns up to 300 reviews.

    The URL must come from a `search_serpapi` result.

    Args:
        url: Full TripAdvisor Restaurant_Review page URL from a search result.
        max_reviews: Number of reviews to fetch. Default 50. Deep path max 300.
        mode: "fast" for SerpAPI, "deep" for Apify. `max_reviews > 100`
              selects deep mode automatically.
    """
    try:
        match = _TA_REVIEW_RE.search(url or "")
        if not match:
            return {
                "status": "error",
                "error_message": f"URL is not a TripAdvisor Restaurant_Review page: {url}",
            }
        place_id = match.group("place_id")
        max_reviews = max(1, max_reviews)
        deep = mode.strip().lower() in {"deep", "full", "apify"} or max_reviews > TRIPADVISOR_FAST_MAX_REVIEWS

        if deep:
            result = await _fetch_tripadvisor_reviews_apify(
                url=url,
                place_id=place_id,
                max_reviews=max_reviews,
            )
        else:
            result = await _fetch_tripadvisor_reviews_serpapi(
                url=url,
                place_id=place_id,
                max_reviews=max_reviews,
            )
        if result.get("status") == "success":
            _emit_tripadvisor_source(tool_context, url)
        return result
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error_message": str(e)}
