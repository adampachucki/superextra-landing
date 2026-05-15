"""Explicit web search tools backed by SerpAPI."""

from __future__ import annotations

import time
from typing import Any, Optional
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

import httpx

from .cloud_logging import emit_cloud_log
from .secrets import get_secret
from .web_tools import read_public_pages

BASE_URL = "https://serpapi.com/search.json"
TIMEOUT_S = 20.0
MAX_RESULTS = 20
MAX_READ_LIMIT = 10
SERPAPI_PAGE_SIZE = 10
FRESHNESS_TBS = {
    "day": "qdr:d",
    "week": "qdr:w",
    "month": "qdr:m",
    "year": "qdr:y",
}
_SKIP_READ_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "pinterest.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
}
_READABLE_SEARCH_EXCLUSIONS = (
    "-site:facebook.com -site:instagram.com -site:linkedin.com "
    "-site:pinterest.com -site:tiktok.com -site:twitter.com "
    "-site:x.com -site:youtube.com -site:youtu.be"
)
_TRACKING_QUERY_PARAMS = {
    "dclid",
    "fbclid",
    "gclid",
    "gbraid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "srsltid",
    "wbraid",
}

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=TIMEOUT_S)
    return _client


def _get_api_key() -> str:
    return get_secret("SERPAPI_API_KEY")


def _domain_for_url(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""


def _clean_optional(value: Optional[str]) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _bounded_num_results(value: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        num = MAX_RESULTS
    return max(1, min(num, MAX_RESULTS))


def _bounded_read_limit(value: int) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = MAX_READ_LIMIT
    return max(1, min(limit, MAX_READ_LIMIT))


def _canonical_candidate_url(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return url
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in _TRACKING_QUERY_PARAMS
            and not key.lower().startswith("utm_")
        ],
        doseq=True,
    )
    return urlunparse(parsed._replace(query=query, fragment=""))


def _skip_read_reason(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return "invalid_url"
    host = (parsed.hostname or "").removeprefix("www.").lower()
    if parsed.scheme not in ("http", "https") or not host:
        return "invalid_url"
    if not parsed.path or parsed.path == "/":
        return "domain_root"
    if any(host == domain or host.endswith(f".{domain}") for domain in _SKIP_READ_DOMAINS):
        return "social_or_app_page"
    if host.endswith(".google.com") or host == "google.com":
        if parsed.path.startswith("/search"):
            return "search_result_page"
    return None


def _search_candidate(result: dict[str, Any], *, skip_reason: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "title": result.get("title") or result.get("domain") or result.get("url"),
        "url": result.get("url"),
        "domain": result.get("domain") or _domain_for_url(str(result.get("url") or "")),
        "position": result.get("position"),
    }
    if skip_reason:
        out["skip_reason"] = skip_reason
    return out


def _read_candidates(results: list[dict[str, Any]], limit: int) -> tuple[list[str], list[dict[str, Any]]]:
    urls: list[str] = []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        raw_url = result.get("url")
        if not isinstance(raw_url, str) or not raw_url.strip():
            continue
        url = _canonical_candidate_url(raw_url.strip())
        if url in seen:
            continue
        seen.add(url)
        skip_reason = _skip_read_reason(url)
        if skip_reason is None and len(urls) >= limit:
            skip_reason = "read_limit_reached"
        candidate = _search_candidate({**result, "url": url}, skip_reason=skip_reason)
        candidate["read_attempted"] = skip_reason is None
        candidates.append(candidate)
        if skip_reason is None:
            urls.append(url)
    return urls, candidates


def _merge_search_results(*result_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for results in result_sets:
        for result in results:
            raw_url = result.get("url")
            if not isinstance(raw_url, str) or not raw_url.strip():
                continue
            url = _canonical_candidate_url(raw_url.strip())
            if url in seen:
                continue
            seen.add(url)
            item = {**result, "url": url, "position": len(merged) + 1}
            merged.append(item)
    return merged


def _readable_supplement_query(query: str) -> str:
    return f"{query} {_READABLE_SEARCH_EXCLUSIONS}"


def _result_source(result: dict[str, Any]) -> dict[str, Any] | None:
    url = result.get("url")
    if not isinstance(url, str) or not url.strip():
        return None
    title = result.get("title")
    domain = result.get("domain")
    return {
        "url": url,
        "title": title if isinstance(title, str) and title.strip() else domain or url,
        "domain": domain if isinstance(domain, str) else _domain_for_url(url),
    }


def _normalize_organic_results(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    organic = payload.get("organic_results")
    if not isinstance(organic, list):
        return []

    results: list[dict[str, Any]] = []
    for raw in organic:
        if not isinstance(raw, dict):
            continue
        url = raw.get("link")
        if not isinstance(url, str) or not url.strip():
            continue
        url = _canonical_candidate_url(url.strip())
        domain = _domain_for_url(url)
        title = raw.get("title")
        snippet = raw.get("snippet")
        source = raw.get("source")
        date = raw.get("date")
        position = raw.get("position")
        item: dict[str, Any] = {
            "title": title.strip() if isinstance(title, str) and title.strip() else domain or url,
            "url": url,
            "domain": domain,
            "snippet": snippet.strip() if isinstance(snippet, str) else "",
            "position": position if isinstance(position, int) else len(results) + 1,
            "result_type": "organic",
        }
        if isinstance(source, str) and source.strip():
            item["source"] = source.strip()
        if isinstance(date, str) and date.strip():
            item["date"] = date.strip()
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _next_start_from_pagination(payload: dict[str, Any]) -> int | None:
    pagination = payload.get("serpapi_pagination")
    if not isinstance(pagination, dict):
        return None
    next_link = pagination.get("next_link")
    if not isinstance(next_link, str) or not next_link.strip():
        return None
    try:
        values = parse_qs(urlparse(next_link).query).get("start")
    except Exception:  # noqa: BLE001
        return None
    if not values:
        return None
    try:
        start = int(values[0])
    except (TypeError, ValueError):
        return None
    return start if start > 0 else None


def _run_id_from_tool_context(tool_context: Any) -> str | None:
    session = getattr(tool_context, "session", None)
    state = getattr(session, "state", None)
    if not isinstance(state, dict):
        return None
    value = state.get("runId")
    return value if isinstance(value, str) and value else None


async def search_web(
    query: str,
    location: Optional[str] = None,
    gl: Optional[str] = None,
    hl: Optional[str] = None,
    num_results: int = MAX_RESULTS,
    freshness: Optional[str] = None,
    tool_context=None,
) -> dict:
    """Search public web results with SerpAPI Google Search.

    Use this for source discovery. Search snippets help choose sources, but
    they are not page evidence. Read the strongest concrete URLs with the
    available Jina page reader before relying on facts below the snippet.

    Returns `status`, normalized `results`, and pill-ready `sources`. Raw
    SerpAPI payloads are intentionally not returned.

    Args:
        query: Search query.
        location: Optional SerpAPI location string, such as "Berlin, Germany".
        gl: Optional two-letter Google country code, such as "de" or "us".
        hl: Optional two-letter Google language code, such as "de" or "en".
        num_results: Number of organic results to return, capped at 20.
        freshness: Optional recency filter: "day", "week", "month", or "year".
    """
    started = time.monotonic()
    cleaned_query = query.strip() if isinstance(query, str) else ""
    count = _bounded_num_results(num_results)
    clean_freshness = _clean_optional(freshness)
    run_id = _run_id_from_tool_context(tool_context)

    if not cleaned_query:
        result = {"status": "error", "error_message": "query is empty"}
        _log_search(
            run_id=run_id,
            query=cleaned_query,
            params={},
            result=result,
            started=started,
            error_reason="empty_query",
        )
        return result

    params: dict[str, Any] = {
        "engine": "google",
        "q": cleaned_query,
    }
    if loc := _clean_optional(location):
        params["location"] = loc
    if country := _clean_optional(gl):
        params["gl"] = country.lower()
    if language := _clean_optional(hl):
        params["hl"] = language.lower()
    if clean_freshness:
        tbs = FRESHNESS_TBS.get(clean_freshness.lower())
        if tbs is None:
            result = {
                "status": "error",
                "error_message": "freshness must be one of: day, week, month, year",
            }
            _log_search(
                run_id=run_id,
                query=cleaned_query,
                params=_safe_params({**params, "num": count}),
                result=result,
                started=started,
                error_reason="invalid_freshness",
            )
            return result
        params["tbs"] = tbs
    try:
        params["api_key"] = _get_api_key()
        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        next_start: int | None = None
        seen_starts: set[int] = set()
        while len(results) < count:
            page_size = min(SERPAPI_PAGE_SIZE, count - len(results))
            page_params = {**params, "num": page_size}
            if next_start is not None:
                page_params["start"] = next_start

            current_start = int(page_params.get("start", 0))
            if current_start in seen_starts:
                break
            seen_starts.add(current_start)

            resp = await _get_client().get(BASE_URL, params=page_params)
            if resp.status_code != 200:
                result = {
                    "status": "error",
                    "error_message": f"SerpAPI search error {resp.status_code}: {resp.text}",
                }
                _log_search(
                    run_id=run_id,
                    query=cleaned_query,
                    params=_safe_params({**params, "num": count}),
                    result=result,
                    started=started,
                    error_reason=f"http_{resp.status_code}",
                )
                return result

            payload = resp.json()
            if not isinstance(payload, dict):
                result = {"status": "error", "error_message": "Unexpected SerpAPI response format"}
                _log_search(
                    run_id=run_id,
                    query=cleaned_query,
                    params=_safe_params({**params, "num": count}),
                    result=result,
                    started=started,
                    error_reason="invalid_json_shape",
                )
                return result

            api_error = payload.get("error")
            metadata = payload.get("search_metadata")
            metadata_status = metadata.get("status") if isinstance(metadata, dict) else None
            if api_error or metadata_status == "Error":
                result = {
                    "status": "error",
                    "error_message": str(api_error or "SerpAPI search status is Error"),
                }
                _log_search(
                    run_id=run_id,
                    query=cleaned_query,
                    params=_safe_params({**params, "num": count}),
                    result=result,
                    started=started,
                    error_reason="api_error",
                )
                return result

            page_results = _normalize_organic_results(payload, page_size)
            for item in page_results:
                url = item["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                item["position"] = len(results) + 1
                results.append(item)
                if len(results) >= count:
                    break
            next_start = _next_start_from_pagination(payload)
            if next_start is None or next_start in seen_starts or len(results) >= count:
                break

        sources = [source for source in (_result_source(item) for item in results) if source]
        result = {
            "status": "success",
            "query": cleaned_query,
            "results": results,
            "sources": sources,
            "result_count": len(results),
        }
        _log_search(
            run_id=run_id,
            query=cleaned_query,
            params=_safe_params({**params, "num": count}),
            result=result,
            started=started,
            error_reason=None,
        )
        return result
    except httpx.TimeoutException:
        result = {"status": "error", "error_message": "Timeout searching SerpAPI"}
        _log_search(
            run_id=run_id,
            query=cleaned_query,
            params=_safe_params({**params, "num": count}),
            result=result,
            started=started,
            error_reason="timeout",
        )
        return result
    except httpx.RequestError as e:
        result = {"status": "error", "error_message": f"Network error searching SerpAPI: {e}"}
        _log_search(
            run_id=run_id,
            query=cleaned_query,
            params=_safe_params({**params, "num": count}),
            result=result,
            started=started,
            error_reason="network_error",
        )
        return result
    except Exception as e:
        result = {"status": "error", "error_message": str(e)}
        _log_search(
            run_id=run_id,
            query=cleaned_query,
            params=_safe_params({**params, "num": count}),
            result=result,
            started=started,
            error_reason="exception",
        )
        return result


def _safe_params(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k != "api_key"}


def _log_search(
    *,
    run_id: str | None,
    query: str,
    params: dict[str, Any],
    result: dict[str, Any],
    started: float,
    error_reason: str | None,
) -> None:
    emit_cloud_log(
        "search_web",
        run_id=run_id,
        query=query,
        params=params,
        status=result.get("status"),
        error_reason=error_reason,
        error_message=result.get("error_message"),
        result_count=len(result.get("results") or []),
        source_count=len(result.get("sources") or []),
        duration_ms=int((time.monotonic() - started) * 1000),
    )


async def search_and_read_public_pages(
    query: str,
    location: Optional[str] = None,
    gl: Optional[str] = None,
    hl: Optional[str] = None,
    num_results: int = MAX_RESULTS,
    read_limit: int = MAX_READ_LIMIT,
    freshness: Optional[str] = None,
    tool_context=None,
) -> dict:
    """Search public web results, then read the strongest concrete pages.

    Primary web-evidence tool for restaurant research. Search results are
    candidates only; `sources` contains only pages that Jina Reader fetched
    successfully. Use this for broad web research before relying on facts from
    public web pages.

    Args:
        query: Search query.
        location: Optional SerpAPI location string, such as "Berlin, Germany".
        gl: Optional two-letter Google country code, such as "de" or "us".
        hl: Optional two-letter Google language code, such as "de" or "en".
        num_results: Organic results to inspect, capped at 20.
        read_limit: Concrete result URLs to batch-read, capped at 10.
        freshness: Optional recency filter: "day", "week", "month", or "year".
    """
    started = time.monotonic()
    run_id = _run_id_from_tool_context(tool_context)
    count = _bounded_num_results(num_results)
    limit = _bounded_read_limit(read_limit)

    search = await search_web(
        query=query,
        location=location,
        gl=gl,
        hl=hl,
        num_results=count,
        freshness=freshness,
        tool_context=tool_context,
    )
    if search.get("status") != "success":
        result = {
            "status": "error",
            "query": query.strip() if isinstance(query, str) else "",
            "error_message": search.get("error_message", "Search failed"),
            "discovered_count": 0,
            "attempted_read_count": 0,
            "successful_read_count": 0,
            "failed_read_count": 0,
            "candidate_results": [],
            "results": [],
            "_error_reason": "search_failed",
        }
        _log_search_and_read(run_id=run_id, result=result, started=started)
        result.pop("_error_reason", None)
        return result

    search_results = [
        item for item in search.get("results") or [] if isinstance(item, dict)
    ]
    search_queries = [search.get("query") or query]
    urls, candidates = _read_candidates(search_results, limit)
    if len(urls) < limit:
        supplement_query = _readable_supplement_query(str(search_queries[0]))
        supplement = await search_web(
            query=supplement_query,
            location=location,
            gl=gl,
            hl=hl,
            num_results=count,
            freshness=freshness,
            tool_context=tool_context,
        )
        if supplement.get("status") == "success":
            supplemental_results = [
                item for item in supplement.get("results") or [] if isinstance(item, dict)
            ]
            search_results = _merge_search_results(search_results, supplemental_results)
            search_queries.append(supplement_query)
            urls, candidates = _read_candidates(search_results, limit)
    if not urls:
        result = {
            "status": "error",
            "query": search.get("query") or query,
            "search_queries": search_queries,
            "error_message": "Search found no concrete readable result URLs",
            "discovered_count": len(search_results),
            "attempted_read_count": 0,
            "successful_read_count": 0,
            "failed_read_count": 0,
            "candidate_results": candidates,
            "results": [],
            "_error_reason": "no_readable_candidates",
        }
        _log_search_and_read(run_id=run_id, result=result, started=started)
        result.pop("_error_reason", None)
        return result

    read_result = await read_public_pages(urls)
    read_items = [
        item for item in read_result.get("results") or [] if isinstance(item, dict)
    ]
    successful = [item for item in read_items if item.get("status") == "success"]
    failed_count = len(read_items) - len(successful)
    result = {
        "status": "success" if successful else "error",
        "query": search.get("query") or query,
        "search_queries": search_queries,
        "discovered_count": len(search_results),
        "attempted_read_count": len(urls),
        "successful_read_count": len(successful),
        "failed_read_count": failed_count,
        "candidate_results": candidates,
        "results": read_items,
        "sources": read_result.get("sources") or [],
    }
    if not successful:
        result["error_message"] = f"All {len(urls)} candidate pages failed to read"
        result["_error_reason"] = "all_reads_failed"
    _log_search_and_read(run_id=run_id, result=result, started=started)
    result.pop("_error_reason", None)
    return result


def _log_search_and_read(
    *,
    run_id: str | None,
    result: dict[str, Any],
    started: float,
) -> None:
    emit_cloud_log(
        "search_and_read_public_pages",
        run_id=run_id,
        query=result.get("query"),
        search_query_count=len(result.get("search_queries") or []),
        status=result.get("status"),
        error_reason=result.get("_error_reason"),
        error_message=result.get("error_message"),
        discovered_count=result.get("discovered_count"),
        attempted_read_count=result.get("attempted_read_count"),
        successful_read_count=result.get("successful_read_count"),
        failed_read_count=result.get("failed_read_count"),
        source_count=len(result.get("sources") or []),
        duration_ms=int((time.monotonic() - started) * 1000),
    )
