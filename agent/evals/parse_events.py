"""Parse a captured ADK event stream into a structured run record.

The eval harness consumes raw ADK events, not Firestore state. This parser
reconstructs the source drawer and the discovery-to-read funnel from grounding
metadata, tool responses, and specialist output state deltas.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from superextra_agent.firestore_events import (
    _get,
    _iter_parts,
    _state_delta,
    extract_sources_from_grounding,
    extract_sources_from_search_tool,
)
from superextra_agent.specialist_catalog import AUTHOR_TO_OUTPUT_KEY, SPECIALIST_RESULT_KEYS
from superextra_agent.web_tools import _canonical_source_url


SPECIALIST_NAMES = set(AUTHOR_TO_OUTPUT_KEY)
SPECIALIST_LABEL_BY_AUTHOR = {
    author: SPECIALIST_RESULT_KEYS[output_key]
    for author, output_key in AUTHOR_TO_OUTPUT_KEY.items()
}


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _normal_source_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = urlparse(text)
    except Exception:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    return (
        parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            fragment="",
        )
        .geturl()
        .rstrip("/")
    )


def _source_dedupe_key(entry: dict[str, Any]) -> str | None:
    url = entry.get("url")
    if not url:
        return None
    place_id = entry.get("place_id") or ""
    if place_id:
        provider = entry.get("provider") or ""
        return f"{provider}\0{place_id}\0{url}"
    return str(url)


def _append_drawer_source(
    drawer_sources: list[dict],
    drawer_seen: set[str],
    entry: dict,
    *,
    kind: str,
) -> None:
    key = _source_dedupe_key(entry)
    if not key or key in drawer_seen:
        return
    drawer_seen.add(key)
    drawer_entry = dict(entry)
    drawer_entry["kind"] = kind
    url = drawer_entry.get("url")
    if isinstance(url, str) and not drawer_entry.get("domain"):
        drawer_entry["domain"] = _domain_of(url)
    drawer_sources.append(drawer_entry)


def _reader_failure_bucket(value: Any) -> str:
    text = str(value or "").lower()
    if "timeout" in text:
        return "timeout"
    if "jina reader account balance" in text or "insufficientbalance" in text:
        return "jina_billing"
    if "http 402" in text:
        return "jina_billing"
    if "upstream http 403" in text or "http 403" in text:
        return "http_403"
    if "http 429" in text or "ratelimit" in text or "rate limit" in text:
        return "rate_limited"
    if "upstream http" in text:
        return "upstream_http"
    if "too thin" in text or "thin content" in text:
        return "thin_content"
    if "domain root" in text:
        return "domain_root"
    if "not-found" in text or "not found" in text or "404" in text:
        return "not_found"
    if "adblock" in text or "ad blocker" in text:
        return "adblock"
    if "paywall" in text:
        return "paywall"
    if "captcha" in text:
        return "captcha"
    if "cloudflare" in text:
        return "cloudflare"
    if "login" in text:
        return "login_required"
    return "other"


def _canonical_urls(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        url = _canonical_source_url(value)
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _count(response: dict[str, Any], key: str, fallback: int = 0) -> int:
    value = response.get(key)
    return value if isinstance(value, int) else fallback


def _read_call_from_response(
    *,
    author: str,
    response: dict[str, Any],
    requested_urls: list[str],
) -> dict[str, Any]:
    attempted_urls: list[str] = []
    successful_urls: list[str] = []
    returned_source_urls: list[str] = []
    failed_sources: list[dict[str, str]] = []

    for result in response.get("results") or []:
        if not isinstance(result, dict):
            continue
        actual_url = _canonical_source_url(result.get("url"))
        requested_url = _canonical_source_url(result.get("requested_url"))
        attempted_url = requested_url or actual_url
        if attempted_url:
            attempted_urls.append(attempted_url)
        if result.get("status") == "success":
            if actual_url:
                successful_urls.append(actual_url)
            continue
        failed_url = attempted_url or actual_url
        if not failed_url:
            continue
        reason = str(
            result.get("error_message")
            or result.get("reason")
            or result.get("error")
            or result.get("status")
            or "read failed"
        )
        failed_sources.append(
            {
                "url": failed_url,
                "reason": reason,
                "reason_bucket": _reader_failure_bucket(
                    result.get("_error_reason") or reason
                ),
            }
        )

    for source in response.get("sources") or []:
        if not isinstance(source, dict):
            continue
        url = _normal_source_url(source.get("url"))
        if url:
            returned_source_urls.append(url)

    attempted_unique = sorted(set(attempted_urls))
    successful_unique = sorted(set(successful_urls))
    failed_unique = []
    failed_seen: set[str] = set()
    for item in failed_sources:
        key = f"{item['url']}\0{item['reason']}"
        if key in failed_seen:
            continue
        failed_seen.add(key)
        failed_unique.append(item)

    return {
        "agent": author,
        "requested_urls": requested_urls,
        "requested_count": _count(response, "requested_count", len(requested_urls)),
        "valid_url_count": _count(response, "valid_url_count", 0),
        "available_count": _count(response, "available_count", 0),
        "attempted_urls": attempted_unique,
        "attempted_count": _count(response, "attempted_count", len(attempted_unique)),
        "successful_urls": successful_unique,
        "successful_count": _count(response, "success_count", len(successful_unique)),
        "failed_sources": failed_unique,
        "failed_count": _count(response, "failed_count", len(failed_unique)),
        "skipped_urls": _canonical_urls(response.get("skipped_urls")),
        "skipped_count": _count(response, "skipped_count", 0),
        "auto_appended_urls": _canonical_urls(response.get("auto_appended_urls")),
        "auto_appended_count": _count(response, "auto_appended_count", 0),
        "rejected_urls": _canonical_urls(response.get("rejected_urls")),
        "rejected_count": _count(response, "rejected_count", 0),
        "invalid_urls": [
            str(value)
            for value in response.get("invalid_urls") or []
            if isinstance(value, str) and value.strip()
        ],
        "invalid_count": _count(response, "invalid_count", 0),
        "omitted_urls": _canonical_urls(response.get("omitted_urls")),
        "omitted_count": _count(response, "omitted_count", 0),
        "returned_source_urls": sorted(set(returned_source_urls)),
        "status": str(response.get("status") or ""),
    }


def _merge_counts(rows: list[dict[str, Any]], key: str) -> int:
    return sum(int(row.get(key) or 0) for row in rows)


def _is_noop_read_call(row: dict[str, Any]) -> bool:
    metric_keys = (
        "requested_count",
        "valid_url_count",
        "attempted_count",
        "successful_count",
        "failed_count",
        "skipped_count",
        "auto_appended_count",
        "rejected_count",
        "invalid_count",
        "omitted_count",
    )
    return all(int(row.get(key) or 0) == 0 for key in metric_keys)


def _is_effective_read_call(row: dict[str, Any]) -> bool:
    return int(row.get("attempted_count") or 0) > 0


def _source_funnel(
    *,
    specialist_outputs: dict[str, str],
    grounding_entry_urls: set[str],
    captured_source_urls: set[str],
    read_calls: list[dict[str, Any]],
    grounding_urls_by_author: dict[str, set[str]],
) -> dict[str, Any]:
    requested_urls = {
        url for row in read_calls for url in row.get("requested_urls", [])
    }
    attempted_urls = {
        url for row in read_calls for url in row.get("attempted_urls", [])
    }
    successful_urls = {
        url for row in read_calls for url in row.get("successful_urls", [])
    }
    returned_source_urls = {
        url for row in read_calls for url in row.get("returned_source_urls", [])
    }
    read_urls = attempted_urls | successful_urls | returned_source_urls
    auto_appended_urls = {
        url for row in read_calls for url in row.get("auto_appended_urls", [])
    }
    failed_sources = [
        item
        for row in read_calls
        for item in row.get("failed_sources", [])
        if isinstance(item, dict)
    ]
    failure_reason_counts: dict[str, int] = {}
    for item in failed_sources:
        bucket = str(item.get("reason_bucket") or "other")
        failure_reason_counts[bucket] = failure_reason_counts.get(bucket, 0) + 1

    specialist_rows: list[dict[str, Any]] = []
    for agent in sorted(SPECIALIST_NAMES):
        output_key = AUTHOR_TO_OUTPUT_KEY[agent]
        agent_calls = [row for row in read_calls if row.get("agent") == agent]
        agent_noop_calls = [row for row in agent_calls if _is_noop_read_call(row)]
        agent_effective_calls = [
            row for row in agent_calls if _is_effective_read_call(row)
        ]
        agent_grounding = grounding_urls_by_author.get(agent, set())
        agent_attempted = {
            url for row in agent_calls for url in row.get("attempted_urls", [])
        }
        agent_successful = {
            url for row in agent_calls for url in row.get("successful_urls", [])
        }
        if not agent_calls and not agent_grounding and output_key not in specialist_outputs:
            continue
        specialist_rows.append(
            {
                "key": agent,
                "label": SPECIALIST_LABEL_BY_AUTHOR[agent],
                "grounding_url_count": len(agent_grounding),
                "read_tool_call_count": len(agent_calls),
                "read_call_count": len(agent_effective_calls),
                "noop_read_call_count": len(agent_noop_calls),
                "requested_url_count": _merge_counts(agent_calls, "requested_count"),
                "attempted_url_count": _merge_counts(agent_calls, "attempted_count"),
                "attempted_unique_url_count": len(agent_attempted),
                "successful_url_count": _merge_counts(agent_calls, "successful_count"),
                "successful_unique_url_count": len(agent_successful),
                "failed_url_count": _merge_counts(agent_calls, "failed_count"),
                "skipped_url_count": _merge_counts(agent_calls, "skipped_count"),
                "auto_appended_url_count": _merge_counts(
                    agent_calls, "auto_appended_count"
                ),
                "rejected_url_count": _merge_counts(agent_calls, "rejected_count"),
                "invalid_url_count": _merge_counts(agent_calls, "invalid_count"),
                "omitted_url_count": _merge_counts(agent_calls, "omitted_count"),
                "grounding_urls_attempted_count": len(agent_grounding & agent_attempted),
                "grounding_urls_not_attempted": sorted(agent_grounding - agent_attempted),
                "successful_urls": sorted(agent_successful),
                "failed_sources": [
                    item
                    for row in agent_calls
                    for item in row.get("failed_sources", [])
                    if isinstance(item, dict)
                ],
            }
        )

    noop_read_calls = [row for row in read_calls if _is_noop_read_call(row)]
    effective_read_calls = [row for row in read_calls if _is_effective_read_call(row)]

    return {
        "specialist_output_count": len(specialist_outputs),
        "grounding_entry_url_count": len(grounding_entry_urls),
        "captured_source_url_count": len(captured_source_urls),
        "specialist_read_tool_call_count": len(read_calls),
        "specialist_read_call_count": len(effective_read_calls),
        "specialist_read_effective_call_count": len(effective_read_calls),
        "specialist_read_noop_call_count": len(noop_read_calls),
        "specialist_read_requested_url_count": _merge_counts(
            read_calls, "requested_count"
        ),
        "specialist_read_requested_unique_url_count": len(requested_urls),
        "specialist_read_attempted_url_count": _merge_counts(
            read_calls, "attempted_count"
        ),
        "specialist_read_attempted_unique_url_count": len(attempted_urls),
        "specialist_read_successful_url_count": _merge_counts(
            read_calls, "successful_count"
        ),
        "specialist_read_successful_unique_url_count": len(successful_urls),
        "specialist_read_failed_url_count": _merge_counts(read_calls, "failed_count"),
        "specialist_read_skipped_url_count": _merge_counts(read_calls, "skipped_count"),
        "specialist_read_auto_appended_url_count": _merge_counts(
            read_calls, "auto_appended_count"
        ),
        "specialist_read_rejected_url_count": _merge_counts(
            read_calls, "rejected_count"
        ),
        "specialist_read_invalid_url_count": _merge_counts(
            read_calls, "invalid_count"
        ),
        "specialist_read_omitted_url_count": _merge_counts(
            read_calls, "omitted_count"
        ),
        "specialist_read_returned_source_url_count": len(returned_source_urls),
        "grounding_urls_requested_by_specialists_count": len(
            grounding_entry_urls & requested_urls
        ),
        "grounding_urls_attempted_by_specialists_count": len(
            grounding_entry_urls & attempted_urls
        ),
        "grounding_urls_not_attempted": sorted(grounding_entry_urls - attempted_urls),
        "captured_urls_requested_by_specialists_count": len(
            captured_source_urls & requested_urls
        ),
        "captured_urls_attempted_by_specialists_count": len(
            captured_source_urls & read_urls
        ),
        "captured_urls_not_attempted": sorted(captured_source_urls - read_urls),
        "specialist_read_attempted_urls_not_captured": sorted(
            attempted_urls - captured_source_urls
        ),
        "specialist_read_successful_urls": sorted(successful_urls),
        "specialist_read_failed_sources": failed_sources,
        "specialist_read_failure_reason_counts": failure_reason_counts,
        "specialist_read_auto_appended_urls": sorted(auto_appended_urls),
        "specialist_read_returned_source_urls": sorted(returned_source_urls),
        "specialists": specialist_rows,
    }


def parse_run(events: list[Any]) -> dict[str, Any]:
    """Consume captured ADK events and return a flat run record."""
    grounding_entries_by_url: dict[str, dict[str, Any]] = {}
    grounding_urls_by_author: dict[str, set[str]] = {}
    fetched_urls: set[str] = set()
    provider_pills: list[dict[str, Any]] = []
    specialists_dispatched: list[str] = []
    final_report = ""
    specialist_outputs: dict[str, str] = {}
    tool_call_counts: dict[str, int] = {}
    authors_seen: dict[str, int] = {}
    token_totals = {"prompt": 0, "candidates": 0, "total": 0}
    pending_read_requests_by_author: dict[str, list[list[str]]] = {}
    specialist_read_calls: list[dict[str, Any]] = []

    for event in events:
        author = _get(event, "author") or "?"
        authors_seen[author] = authors_seen.get(author, 0) + 1

        event_sources = extract_sources_from_grounding(event) + extract_sources_from_search_tool(
            event
        )
        for src in event_sources:
            url = src.get("url")
            if not isinstance(url, str) or not url:
                continue
            grounding_urls_by_author.setdefault(author, set()).add(url)
            if url not in grounding_entries_by_url:
                grounding_entries_by_url[url] = {
                    "url": url,
                    "domain": src.get("domain") or _domain_of(url),
                    "title": src.get("title"),
                    "provider": src.get("provider") or "grounding",
                }

        for part in _iter_parts(event):
            fc = _get(part, "function_call")
            name = _get(fc, "name") if fc else None
            if name:
                tool_call_counts[name] = tool_call_counts.get(name, 0) + 1
                args = _get(fc, "args") or {}
                if name == "fetch_web_content":
                    url = args.get("url") if isinstance(args, dict) else None
                    if isinstance(url, str) and url:
                        fetched_urls.add(url)
                elif name in ("fetch_web_content_batch", "read_public_pages"):
                    urls = args.get("urls") if isinstance(args, dict) else None
                    for url in urls or []:
                        if isinstance(url, str) and url:
                            fetched_urls.add(url)
                elif name == "read_discovered_sources":
                    urls = args.get("urls") if isinstance(args, dict) else None
                    requested_urls = _canonical_urls(urls)
                    pending_read_requests_by_author.setdefault(author, []).append(
                        requested_urls
                    )
                    fetched_urls.update(requested_urls)

            fr = _get(part, "function_response")
            response = _get(fr, "response") if fr else None
            response_name = _get(fr, "name") if fr else None
            if not isinstance(response, dict):
                continue

            if response_name in (
                "search_and_read_public_pages",
                "read_web_pages",
                "read_public_page",
                "read_public_pages",
                "read_discovered_sources",
            ):
                for source in response.get("sources") or []:
                    if isinstance(source, dict):
                        url = _normal_source_url(source.get("url"))
                        if url:
                            fetched_urls.add(url)

            if response_name == "read_discovered_sources":
                pending = pending_read_requests_by_author.get(author) or []
                requested_urls = pending.pop(0) if pending else []
                read_call = _read_call_from_response(
                    author=author,
                    response=response,
                    requested_urls=requested_urls,
                )
                specialist_read_calls.append(read_call)
                fetched_urls.update(read_call["attempted_urls"])
                fetched_urls.update(read_call["successful_urls"])
                fetched_urls.update(read_call["returned_source_urls"])
            elif (
                response_name == "fetch_web_content"
                and response.get("status") == "success"
            ):
                url = _normal_source_url(response.get("url"))
                if url:
                    fetched_urls.add(url)
            elif response_name == "fetch_web_content_batch":
                for item in response.get("results") or []:
                    if not isinstance(item, dict) or item.get("status") != "success":
                        continue
                    url = _normal_source_url(item.get("url"))
                    if url:
                        fetched_urls.add(url)

        sd = _state_delta(event)
        for key, value in sd.items():
            if key.startswith("_tool_src_") and isinstance(value, dict):
                provider_pills.append(value)
            elif key == "final_report" and isinstance(value, str):
                final_report = value
            elif key in SPECIALIST_RESULT_KEYS and isinstance(value, str):
                specialist_outputs[key] = value

        usage = _get(event, "usage_metadata")
        if usage:
            for field, bucket in (
                ("prompt_token_count", "prompt"),
                ("candidates_token_count", "candidates"),
                ("total_token_count", "total"),
            ):
                value = _get(usage, field)
                if isinstance(value, int):
                    token_totals[bucket] += value

    if not specialists_dispatched:
        specialists_dispatched = sorted(
            name for name in tool_call_counts if name in SPECIALIST_NAMES
        )

    drawer_sources: list[dict[str, Any]] = []
    drawer_seen: set[str] = set()
    grounding_entries = list(grounding_entries_by_url.values())
    specialist_grounding_urls_by_author = {
        author: urls
        for author, urls in grounding_urls_by_author.items()
        if author in SPECIALIST_NAMES
    }
    specialist_grounding_urls = {
        url
        for urls in specialist_grounding_urls_by_author.values()
        for url in urls
    }
    captured_source_urls = specialist_grounding_urls

    for entry in grounding_entries:
        _append_drawer_source(
            drawer_sources,
            drawer_seen,
            entry,
            kind="grounding",
        )
    for pill in provider_pills:
        _append_drawer_source(drawer_sources, drawer_seen, pill, kind="provider")

    return {
        "grounding_entries": grounding_entries,
        "fetched_urls": sorted(fetched_urls),
        "provider_pills": provider_pills,
        "drawer_sources": drawer_sources,
        "specialists_dispatched": specialists_dispatched,
        "final_outcome": "ok" if final_report else "unknown",
        "final_report": final_report,
        "specialist_outputs": specialist_outputs,
        "source_funnel": _source_funnel(
            specialist_outputs=specialist_outputs,
            grounding_entry_urls=specialist_grounding_urls,
            captured_source_urls=captured_source_urls,
            read_calls=specialist_read_calls,
            grounding_urls_by_author=specialist_grounding_urls_by_author,
        ),
        "tool_call_counts": tool_call_counts,
        "authors_seen": authors_seen,
        "token_totals": token_totals,
    }
