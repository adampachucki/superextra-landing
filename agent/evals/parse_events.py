"""Parse a captured ADK event stream into a structured run record.

The eval harness consumes raw ADK events, not Firestore state. This parser
reconstructs the source drawer from grounding metadata, provider pills, and
specialist output state deltas, plus per-run token and tool-call totals.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from superextra_agent.firestore_events import (
    _get,
    _iter_parts,
    _state_delta,
    extract_sources_from_grounding,
)
from superextra_agent.specialist_catalog import AUTHOR_TO_OUTPUT_KEY, SPECIALIST_RESULT_KEYS


SPECIALIST_NAMES = set(AUTHOR_TO_OUTPUT_KEY)


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


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


def parse_run(events: list[Any]) -> dict[str, Any]:
    """Consume captured ADK events and return a flat run record."""
    grounding_entries_by_url: dict[str, dict[str, Any]] = {}
    provider_pills: list[dict[str, Any]] = []
    final_report = ""
    specialist_outputs: dict[str, str] = {}
    tool_call_counts: dict[str, int] = {}
    authors_seen: dict[str, int] = {}
    token_totals = {"prompt": 0, "candidates": 0, "total": 0}

    for event in events:
        author = _get(event, "author") or "?"
        authors_seen[author] = authors_seen.get(author, 0) + 1

        for src in extract_sources_from_grounding(event):
            url = src.get("url")
            if not isinstance(url, str) or not url:
                continue
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

    specialists_dispatched = sorted(
        name for name in tool_call_counts if name in SPECIALIST_NAMES
    )

    drawer_sources: list[dict[str, Any]] = []
    drawer_seen: set[str] = set()
    grounding_entries = list(grounding_entries_by_url.values())
    for entry in grounding_entries:
        _append_drawer_source(drawer_sources, drawer_seen, entry, kind="grounding")
    for pill in provider_pills:
        _append_drawer_source(drawer_sources, drawer_seen, pill, kind="provider")

    return {
        "grounding_entries": grounding_entries,
        "provider_pills": provider_pills,
        "drawer_sources": drawer_sources,
        "specialists_dispatched": specialists_dispatched,
        "final_outcome": "ok" if final_report else "unknown",
        "final_report": final_report,
        "specialist_outputs": specialist_outputs,
        "tool_call_counts": tool_call_counts,
        "authors_seen": authors_seen,
        "token_totals": token_totals,
    }
