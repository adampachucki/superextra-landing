"""Apify-backed structured providers.

Thin wrappers around Apify actors that take a single venue identifier
(Google Place ID for `get_google_reviews`; a platform URL for the social
fetchers) and return a trimmed, model-friendly subset of the actor's dataset
items.

Each public function emits one source pill via `tool_source_key(...)`
into `tool_context.state` so the run-state pipeline can fold it into the
per-turn source list. Per-platform trimming happens inline in each
function — raw actor responses can be 100s of KB and embed image URL
arrays the model can't use.
"""
import atexit

import httpx

from .place_state import source_title, tool_source_key
from .secrets import get_secret

APIFY_BASE = "https://api.apify.com/v2"
GOOGLE_REVIEWS_ACTOR = "compass~google-maps-reviews-scraper"
TRIPADVISOR_PAGE_ACTOR = "maxcopell~tripadvisor"
FACEBOOK_PAGE_ACTOR = "apify~facebook-pages-scraper"
FACEBOOK_POSTS_ACTOR = "apify~facebook-posts-scraper"
INSTAGRAM_ACTOR = "apify~instagram-scraper"
GOOGLE_REVIEWS_MAX_REVIEWS = 200

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
    return get_secret("APIFY_TOKEN")


async def _run_actor_sync(actor: str, payload: dict) -> dict:
    """POST to an Apify actor's sync endpoint and return the dataset items.

    Returns `{"status": "success", "items": [...]}` on 200/201, else
    `{"status": "error", "error_message": "..."}`. Callers are responsible
    for per-platform trimming and source-pill emission.
    """
    try:
        client = _get_client()
        api_key = _get_api_key()
        resp = await client.post(
            f"{APIFY_BASE}/acts/{actor}/run-sync-get-dataset-items",
            params={"token": api_key},
            json=payload,
            timeout=120.0,
        )
        if resp.status_code not in (200, 201):
            return {
                "status": "error",
                "error_message": f"Apify {actor} error {resp.status_code}: {resp.text[:300]}",
            }
        items = resp.json()
        if not isinstance(items, list):
            return {
                "status": "error",
                "error_message": f"Apify {actor} returned unexpected response shape",
            }
        return {"status": "success", "items": items}
    except httpx.TimeoutException:
        return {
            "status": "error",
            "error_message": f"Apify {actor} timed out after 120s",
        }
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error_message": str(e)}


def _emit_source_pill(
    tool_context,
    *,
    provider: str,
    url: str,
    title: str,
    domain: str,
) -> None:
    """Write one source-pill entry into tool_context.state.

    Key is `tool_source_key(provider, url)` — URL is the stable anchor since
    fetchers take arbitrary platform URLs that may not map to the session's
    target Place ID.
    """
    if tool_context is None or not url:
        return
    tool_context.state[tool_source_key(provider, url)] = {
        "provider": provider,
        "title": title,
        "url": url,
        "domain": domain,
    }


def _compact_google_review(item: dict) -> dict:
    review = {
        "text": item.get("text") or item.get("textTranslated", ""),
        "rating": item.get("stars") or item.get("rating"),
        "date": item.get("publishedAtDate") or item.get("publishAt", ""),
        "language": item.get("originalLanguage") or item.get("language", ""),
        "is_local_guide": item.get("isLocalGuide", False),
        "likes": item.get("likesCount", 0),
    }
    owner_resp = item.get("responseFromOwnerText")
    if owner_resp:
        review["owner_response"] = owner_resp
    detailed_rating = item.get("reviewDetailedRating")
    if isinstance(detailed_rating, dict) and detailed_rating:
        review["subratings"] = detailed_rating
    context = item.get("reviewContext")
    if isinstance(context, dict) and context:
        review["context"] = context
    visited_in = item.get("visitedIn")
    if visited_in:
        review["visited_in"] = visited_in
    images = item.get("reviewImageUrls")
    if isinstance(images, list) and images:
        review["review_image_count"] = len(images)
    return review


async def get_google_reviews(
    place_id: str,
    max_reviews: int = 50,
    tool_context=None,
) -> dict:
    """Fetch Google Maps reviews for a restaurant using its Place ID.

    Uses the Google Maps Place ID directly — no name matching needed. Returns
    structured reviews with text, ratings, dates, owner responses, and
    per-review subratings when the reviews actor exposes them.

    Args:
        place_id: Google Places ID (e.g. 'ChIJMRpv9_HNHkcRdzbAYDXx7fc').
                  Found in the Places context data.
        max_reviews: Maximum number of reviews to fetch (default 50, max 200).
    """
    max_reviews = max(1, min(max_reviews, GOOGLE_REVIEWS_MAX_REVIEWS))
    result = await _run_actor_sync(
        GOOGLE_REVIEWS_ACTOR,
        {
            "placeIds": [place_id],
            "maxReviews": max_reviews,
            "reviewsSort": "newest",
            "reviewsOrigin": "google",
            "personalData": False,
        },
    )
    if result["status"] != "success":
        return result
    items = result["items"]
    if not items:
        return {
            "status": "error",
            "error_message": f"No Google reviews found for place {place_id}",
        }
    reviews = [_compact_google_review(i) for i in items if isinstance(i, dict)]

    if tool_context:
        tool_context.state[tool_source_key("google_reviews", place_id)] = {
            "provider": "google_reviews",
            "title": source_title(tool_context.state, place_id, "Google Reviews"),
            "url": f"https://www.google.com/maps/place/?q=place_id:{place_id}",
            "domain": "google.com",
            "place_id": place_id,
        }

    return {
        "status": "success",
        "place_id": place_id,
        "total_fetched": len(reviews),
        "reviews": reviews,
    }


# ── social_analyst platform fetchers ─────────────────────────────────────────


def _trim_tripadvisor_item(item: dict) -> dict:
    keep = (
        "name", "address", "rating", "rawRanking", "numberOfReviews",
        "rankingPosition", "rankingString", "cuisines", "priceLevel",
        "hours", "website", "phone", "mealTypes", "reviewTags",
        "travelerChoiceAward", "type", "webUrl",
    )
    return {k: item[k] for k in keep if k in item}


async def fetch_tripadvisor_page(url: str, tool_context=None) -> dict:
    """Fetch a TripAdvisor business page (restaurant, hotel, attraction).

    Returns the venue's structured TripAdvisor data: rating, ranking position,
    review count, cuisines, hours, address, contact info. Does NOT return
    review bodies — use review_analyst's `get_tripadvisor_reviews` for those.

    The URL must come from a `search_serpapi` result. Do not pass a URL
    you guessed from a venue name — TA URLs include opaque numeric IDs
    (`-g<geo>-d<place>-`) that cannot be reliably constructed, and an
    unverified URL may point at a same-name venue elsewhere.

    Args:
        url: Full TripAdvisor restaurant/hotel page URL from search results.
    """
    result = await _run_actor_sync(
        TRIPADVISOR_PAGE_ACTOR,
        {
            "startUrls": [{"url": url}],
            "maxItemsPerQuery": 1,
            "includeReviews": False,
        },
    )
    if result["status"] != "success":
        return result
    items = [_trim_tripadvisor_item(i) for i in result["items"] if isinstance(i, dict)]
    if not items:
        return {"status": "error", "error_message": f"No TripAdvisor data at {url}"}
    _emit_source_pill(
        tool_context,
        provider="tripadvisor",
        url=url,
        title="TripAdvisor",
        domain="tripadvisor.com",
    )
    return {"status": "success", "url": url, "items": items}


def _trim_facebook_page_item(item: dict) -> dict:
    keep = (
        "title", "pageName", "pageId", "facebookUrl", "pageUrl",
        "likes", "followers", "address", "email", "websites",
        "categories", "business_hours", "intro", "instagram",
        "alternativeSocialMedia", "rating", "ratings",
        # Load-bearing for marketing_brand's public-ad-signals scope:
        "ad_status", "pageAdLibrary",
    )
    return {k: item[k] for k in keep if k in item}


async def fetch_facebook_page(url: str, tool_context=None) -> dict:
    """Fetch a Facebook page's profile metadata (no recent posts).

    Returns the page's bio, address, follower/like counts, hours, contact
    info, categories, ad-running status, and Instagram cross-link if
    present. For recent posts use `fetch_facebook_posts` separately.

    The URL must come from a `search_serpapi` result — do not guess or
    construct it from a venue name.

    Args:
        url: Full Facebook page URL (e.g. https://www.facebook.com/pagename/).
    """
    result = await _run_actor_sync(
        FACEBOOK_PAGE_ACTOR,
        {"startUrls": [{"url": url}]},
    )
    if result["status"] != "success":
        return result
    items = [_trim_facebook_page_item(i) for i in result["items"] if isinstance(i, dict)]
    if not items:
        return {"status": "error", "error_message": f"No Facebook page data at {url}"}
    _emit_source_pill(
        tool_context,
        provider="facebook",
        url=url,
        title="Facebook page",
        domain="facebook.com",
    )
    return {"status": "success", "url": url, "items": items}


def _trim_facebook_post_item(item: dict) -> dict:
    keep = (
        "text", "time", "timestamp", "postUrl", "url",
        "likes", "reactions", "topReactionsCount",
        "comments", "shares",
    )
    return {k: item[k] for k in keep if k in item}


async def fetch_facebook_posts(url: str, tool_context=None) -> dict:
    """Fetch recent posts from a Facebook page.

    Returns up to 10 recent posts with text, reaction counts, comment
    counts, share counts, and timestamps. Use this for posting cadence,
    content themes, and tone-of-voice signals. For page metadata
    (bio, hours, follower count) use `fetch_facebook_page`.

    The URL must come from a `search_serpapi` result — do not guess or
    construct it from a venue name.

    Args:
        url: Full Facebook page URL (e.g. https://www.facebook.com/pagename/).
    """
    result = await _run_actor_sync(
        FACEBOOK_POSTS_ACTOR,
        {"startUrls": [{"url": url}], "resultsLimit": 10},
    )
    if result["status"] != "success":
        return result
    items = [_trim_facebook_post_item(i) for i in result["items"] if isinstance(i, dict)]
    if not items:
        return {"status": "error", "error_message": f"No Facebook posts at {url}"}
    _emit_source_pill(
        tool_context,
        provider="facebook",
        url=url,
        title="Facebook page",
        domain="facebook.com",
    )
    return {"status": "success", "url": url, "items": items}


def _trim_instagram_post(post: dict) -> dict:
    keep = (
        "caption", "takenAtTimestamp", "likesCount", "commentsCount",
        "shortCode", "url", "type", "videoViewCount",
    )
    return {k: post[k] for k in keep if k in post}


def _trim_instagram_item(item: dict) -> dict:
    keep_top = (
        "username", "fullName", "biography", "followersCount", "followsCount",
        "postsCount", "verified", "isBusinessAccount", "businessCategoryName",
        "businessAddress", "externalUrls", "url",
    )
    out = {k: item[k] for k in keep_top if k in item}
    posts = item.get("latestPosts")
    if isinstance(posts, list):
        out["latestPosts"] = [_trim_instagram_post(p) for p in posts[:5] if isinstance(p, dict)]
    return out


async def fetch_instagram_profile(url: str, tool_context=None) -> dict:
    """Fetch an Instagram public profile's details.

    Returns the profile's bio, follower/following counts, post count,
    verified/business-account flags, business category and address (if
    set), external links, plus the 5 most recent posts (caption,
    timestamp, like/comment counts, shortcode/permalink).

    Works for public business and personal accounts. Private accounts
    return limited data.

    The URL must come from a `search_serpapi` result — do not guess or
    construct it from a venue name.

    Args:
        url: Full Instagram profile URL (e.g. https://www.instagram.com/username/).
    """
    result = await _run_actor_sync(
        INSTAGRAM_ACTOR,
        {"directUrls": [url], "resultsLimit": 5, "resultsType": "details"},
    )
    if result["status"] != "success":
        return result
    items = [_trim_instagram_item(i) for i in result["items"] if isinstance(i, dict)]
    if not items:
        return {"status": "error", "error_message": f"No Instagram profile data at {url}"}
    _emit_source_pill(
        tool_context,
        provider="instagram",
        url=url,
        title="Instagram",
        domain="instagram.com",
    )
    return {"status": "success", "url": url, "items": items}
