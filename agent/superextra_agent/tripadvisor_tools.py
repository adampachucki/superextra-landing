import atexit
import os
import httpx

BASE_URL = "https://serpapi.com/search.json"

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0)
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
    key = os.environ.get("SERPAPI_API_KEY", "")
    if not key:
        raise RuntimeError("SERPAPI_API_KEY environment variable is not set")
    return key


async def find_tripadvisor_restaurant(name: str, area: str) -> dict:
    """Find a restaurant on TripAdvisor and return its full profile.

    Searches TripAdvisor for the restaurant, then fetches detailed place data
    including ranking, cuisines, dining options, nearby restaurants, and sample
    reviews. Costs 2 SerpAPI calls.

    Args:
        name: Restaurant name (e.g. 'Umami P-Berg').
        area: City or neighborhood for search context (e.g. 'Prenzlauer Berg Berlin').
    """
    try:
        client = _get_client()
        api_key = _get_api_key()

        # Step 1: Search for the restaurant
        search_resp = await client.get(BASE_URL, params={
            "engine": "tripadvisor",
            "q": f"{name} {area}",
            "api_key": api_key,
        })
        if search_resp.status_code != 200:
            return {"status": "error", "error_message": f"SerpAPI search error {search_resp.status_code}: {search_resp.text}"}

        search_data = search_resp.json()
        places = search_data.get("places", [])
        if not places:
            return {"status": "error", "error_message": f"No TripAdvisor results found for '{name} {area}'"}

        match = places[0]
        place_id = match.get("place_id")
        if not place_id:
            return {"status": "error", "error_message": "First search result has no place_id"}

        # Step 2: Get full place details
        place_resp = await client.get(BASE_URL, params={
            "engine": "tripadvisor_place",
            "place_id": place_id,
            "api_key": api_key,
        })
        if place_resp.status_code != 200:
            return {"status": "error", "error_message": f"SerpAPI place error {place_resp.status_code}: {place_resp.text}"}

        place_data = place_resp.json().get("place_result", {})

        # Extract nearby restaurants (compact)
        nearby = []
        for r in place_data.get("nearby", {}).get("restaurants", []):
            nearby.append({
                "name": r.get("name"),
                "place_id": r.get("place_id"),
                "rating": r.get("rating"),
                "reviews": r.get("reviews"),
                "distance_km": round(r.get("distance", 0), 2),
            })

        # Extract sample reviews (compact)
        sample_reviews = []
        for r in place_data.get("reviews_list", []):
            review = {
                "title": r.get("title"),
                "text": r.get("snippet"),
                "rating": r.get("rating"),
                "date": r.get("date"),
            }
            author = r.get("author", {})
            if author.get("hometown"):
                review["author_hometown"] = author["hometown"]
            sample_reviews.append(review)

        return {
            "status": "success",
            "place_id": place_id,
            "name": place_data.get("name"),
            "rating": place_data.get("rating"),
            "num_reviews": place_data.get("reviews"),
            "ranking": place_data.get("ranking"),
            "is_claimed": place_data.get("is_claimed"),
            "cuisines": place_data.get("cuisines", []),
            "diets": place_data.get("diets", []),
            "meal_types": place_data.get("meal_types", []),
            "dining_options": place_data.get("dining_options", []),
            "price_level": next(
                (c.get("name") for c in place_data.get("categories", [])
                 if c.get("name", "").startswith(("$", "€", "£", "Mid", "Fine", "Cheap"))),
                None,
            ),
            "address": place_data.get("address"),
            "phone": place_data.get("phone"),
            "email": place_data.get("email"),
            "website": place_data.get("website"),
            "menu_link": place_data.get("menu", {}).get("link") if place_data.get("menu") else None,
            "nearby_restaurants": nearby,
            "sample_reviews": sample_reviews,
        }
    except Exception as e:
        return {"status": "error", "error_message": str(e)}


async def get_tripadvisor_reviews(place_id: str, num_pages: int = 5) -> dict:
    """Fetch TripAdvisor reviews for a restaurant. Returns full review text,
    ratings, trip types, reviewer origins, and owner responses.

    Each page returns 10 reviews. Default is 5 pages (50 reviews).
    Use the place_id from find_tripadvisor_restaurant.

    Args:
        place_id: TripAdvisor place ID (e.g. '6796040').
        num_pages: Number of pages to fetch (10 reviews each). Default 5, max 10.
    """
    try:
        client = _get_client()
        api_key = _get_api_key()
        num_pages = min(num_pages, 10)

        all_reviews = []
        total_reviews = None
        partial = False

        for page in range(num_pages):
            resp = await client.get(BASE_URL, params={
                "engine": "tripadvisor_reviews",
                "place_id": place_id,
                "offset": page * 10,
                "api_key": api_key,
            })
            if resp.status_code != 200:
                if page == 0:
                    return {"status": "error", "error_message": f"SerpAPI reviews error {resp.status_code}: {resp.text}"}
                partial = True
                break  # Return what we have if a later page fails

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

        if total_reviews and len(all_reviews) < total_reviews:
            partial = True

        return {
            "status": "success",
            "place_id": place_id,
            "total_reviews": total_reviews,
            "fetched_reviews": len(all_reviews),
            "partial": partial,
            "reviews": all_reviews,
        }
    except Exception as e:
        return {"status": "error", "error_message": str(e)}
