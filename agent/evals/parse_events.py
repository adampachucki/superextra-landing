"""Parse a captured ADK event stream into a structured run record.

Reuses the low-level event introspection helpers from firestore_events.py
(the grounding/function-call extractors are stable and battle-tested).
Everything the eval harness needs is computed from the raw event list;
no access to Firestore or the worker's log stream is required.
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
from superextra_agent.specialist_catalog import SPECIALISTS


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def parse_run(events: list[Any]) -> dict[str, Any]:
    """Consume a list of captured ADK events and return a flat run record.

    Output shape (all fields always present):
        grounding_entries: list[dict]        # {url, domain, title} from grounding metadata
        fetched_urls: list[str]              # unique URLs passed to fetch_web_content
        provider_pills: list[dict]           # _tool_src_* state_delta entries
        drawer_sources: list[dict]           # what sources[] would contain
        specialists_dispatched: list[str]    # specialist tool calls observed
        final_outcome: "ok" | "unknown"
        final_report: str                    # research_lead/follow_up final text
        specialist_outputs: dict[str, str]   # output_key → text
        tool_call_counts: dict[str, int]     # per-tool call counts
        authors_seen: dict[str, int]         # author → event count
        token_totals: dict[str, int]         # prompt, candidates, total — summed across all llm calls if captured

    NOTE: Grounding URLs from Vertex AI come as redirect URLs under
    `vertexaisearch.cloud.google.com/grounding-api-redirect/...`. The REAL
    source domain (e.g. `trojmiasto.pl`) is only available as the
    `web.domain` field on the grounding chunk. We capture both the redirect
    URL and the real domain; diversity metrics should read `domain`, not
    parse the URL.
    """
    grounding_entries_by_url: dict[str, dict] = {}
    fetched_urls: set[str] = set()
    provider_pills: list[dict] = []
    specialists_dispatched: list[str] = []
    final_report: str = ""
    specialist_outputs: dict[str, str] = {}
    tool_call_counts: dict[str, int] = {}
    authors_seen: dict[str, int] = {}
    token_totals = {"prompt": 0, "candidates": 0, "total": 0}

    for event in events:
        author = _get(event, "author") or "?"
        authors_seen[author] = authors_seen.get(author, 0) + 1

        # Grounding entries — from grounding_metadata.grounding_chunks[].web.{uri,domain,title}
        for src in extract_sources_from_grounding(event):
            url = src.get("url")
            if url and url not in grounding_entries_by_url:
                grounding_entries_by_url[url] = {
                    "url": url,
                    "domain": src.get("domain") or _domain_of(url),
                    "title": src.get("title"),
                }

        # Tool calls — count and capture URLs for fetch_web_content
        for part in _iter_parts(event):
            fc = _get(part, "function_call")
            name = _get(fc, "name") if fc else None
            if not name:
                continue
            tool_call_counts[name] = tool_call_counts.get(name, 0) + 1
            if name == "fetch_web_content":
                args = _get(fc, "args") or {}
                url = args.get("url") if isinstance(args, dict) else None
                if isinstance(url, str) and url:
                    fetched_urls.add(url)

        # state_delta inspection: provider pills and specialist/final outputs.
        sd = _state_delta(event)
        for key, value in sd.items():
            if key.startswith("_tool_src_") and isinstance(value, dict):
                provider_pills.append(value)
            elif key == "final_report" and isinstance(value, str):
                final_report = value
            elif key.endswith("_result") and isinstance(value, str):
                specialist_outputs[key] = value

        # Token accounting from LlmResponse usage_metadata.
        # Not every event carries usage_metadata — only model-response events do.
        usage = _get(event, "usage_metadata")
        if usage:
            for field, bucket in (
                ("prompt_token_count", "prompt"),
                ("candidates_token_count", "candidates"),
                ("total_token_count", "total"),
            ):
                v = _get(usage, field)
                if isinstance(v, int):
                    token_totals[bucket] += v

    # Derive dispatch from specialist tool calls.
    if not specialists_dispatched:
        specialist_names = {s.name for s in SPECIALISTS}
        specialists_dispatched = sorted(
            name for name in tool_call_counts.keys() if name in specialist_names
        )

    final_outcome = "ok" if final_report else "unknown"

    # Drawer sources: what GearRunState._merge_source would have produced —
    # grounding URLs (deduped) + provider pills (deduped by URL).
    # Prefer real domain from grounding chunk's web.domain over parsed
    # redirect URL — see docstring note above.
    drawer_sources: list[dict] = []
    drawer_seen: set[str] = set()
    for entry in grounding_entries_by_url.values():
        url = entry["url"]
        if url in drawer_seen:
            continue
        drawer_seen.add(url)
        drawer_sources.append({
            "url": url,
            "domain": entry.get("domain") or _domain_of(url),
            "title": entry.get("title"),
            "kind": "grounding",
        })
    for pill in provider_pills:
        url = pill.get("url")
        if not url or url in drawer_seen:
            continue
        drawer_seen.add(url)
        pill_entry = dict(pill)
        pill_entry["kind"] = "provider"
        if not pill_entry.get("domain"):
            pill_entry["domain"] = _domain_of(url)
        drawer_sources.append(pill_entry)

    grounding_entries = list(grounding_entries_by_url.values())

    return {
        "grounding_entries": grounding_entries,
        "fetched_urls": sorted(fetched_urls),
        "provider_pills": provider_pills,
        "drawer_sources": drawer_sources,
        "specialists_dispatched": specialists_dispatched,
        "final_outcome": final_outcome,
        "final_report": final_report,
        "specialist_outputs": specialist_outputs,
        "tool_call_counts": tool_call_counts,
        "authors_seen": authors_seen,
        "token_totals": token_totals,
    }
