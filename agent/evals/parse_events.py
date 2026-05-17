"""Parse a captured ADK event stream into a structured run record.

Reuses the low-level event introspection helpers from firestore_events.py
(the grounding/function-call extractors are stable and battle-tested).
Everything the eval harness needs is computed from the raw event list;
no access to Firestore or the worker's log stream is required.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from superextra_agent.firestore_events import (
    _get,
    _iter_parts,
    _state_delta,
    build_fetched_source,
    extract_sources_from_grounding,
)
from superextra_agent.specialist_catalog import SPECIALIST_RESULT_KEYS, SPECIALISTS
from superextra_agent.web_tools import (
    _canonical_adjudicator_candidate_url,
    _iter_validation_packet_objects,
)

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


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


def _json_object_from_text(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    match = _FENCED_JSON_RE.search(candidate)
    if match:
        candidate = match.group(1).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


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
    if "too thin" in text:
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


def _evidence_memo_drawer_sources(evidence_memo: str) -> list[dict[str, Any]]:
    memo = _json_object_from_text(evidence_memo) if evidence_memo else None
    if memo is None:
        return []

    sources: list[dict[str, Any]] = []
    for claim in memo.get("confirmed_claims") or []:
        if isinstance(claim, dict):
            sources.extend(
                source
                for source in claim.get("evidence") or []
                if isinstance(source, dict)
            )
    for claim in memo.get("contradicted_claims") or []:
        if isinstance(claim, dict):
            sources.extend(
                source
                for source in claim.get("contradicting_evidence") or []
                if isinstance(source, dict)
            )
    for source in memo.get("verified_sources") or []:
        if isinstance(source, dict) and source.get("supports_claim_ids"):
            sources.append(source)
    return sources


def _read_verified_evidence_sources(
    evidence_memo: str, reader_returned_source_urls: set[str]
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for source in _evidence_memo_drawer_sources(evidence_memo):
        url = _normal_source_url(source.get("url"))
        if not url or url not in reader_returned_source_urls:
            continue
        entry = dict(source)
        entry["url"] = url
        sources.append(entry)
    return sources


def _source_funnel(
    *,
    specialist_outputs: dict[str, str],
    reader_requested_urls: set[str],
    reader_attempted_urls: set[str],
    reader_successful_urls: set[str],
    reader_failed_sources: list[dict[str, str]],
    reader_returned_source_urls: set[str],
    grounding_entry_urls: set[str],
    captured_source_urls: set[str],
    reader_auto_appended_urls: set[str],
    reader_auto_appended_count: int,
    evidence_memo: str,
    read_counts: dict[str, int],
) -> dict[str, Any]:
    packet_urls: set[str] = set()
    candidate_urls: set[str] = set()
    claim_source_urls: set[str] = set()
    provider_refs: set[str] = set()
    specialist_rows: list[dict[str, Any]] = []
    packet_count = 0
    claim_count = 0

    for key, report in specialist_outputs.items():
        packets = _iter_validation_packet_objects(report)
        specialist_candidate_urls: set[str] = set()
        specialist_claim_urls: set[str] = set()
        specialist_provider_refs: set[str] = set()
        specialist_claim_count = 0

        for packet in packets:
            packet_count += 1
            for source in packet.get("candidate_sources") or []:
                if not isinstance(source, dict):
                    continue
                url = _canonical_adjudicator_candidate_url(source.get("url"))
                if url:
                    candidate_urls.add(url)
                    packet_urls.add(url)
                    specialist_candidate_urls.add(url)
                ref = str(source.get("provider_ref") or "").strip()
                if ref:
                    provider_refs.add(ref)
                    specialist_provider_refs.add(ref)

            for claim in packet.get("claims_for_validation") or []:
                if not isinstance(claim, dict):
                    continue
                claim_count += 1
                specialist_claim_count += 1
                for raw_url in claim.get("source_urls") or []:
                    url = _canonical_adjudicator_candidate_url(raw_url)
                    if url:
                        claim_source_urls.add(url)
                        packet_urls.add(url)
                        specialist_claim_urls.add(url)
                for raw_ref in claim.get("provider_refs") or []:
                    ref = str(raw_ref).strip()
                    if ref:
                        provider_refs.add(ref)
                        specialist_provider_refs.add(ref)

        specialist_rows.append(
            {
                "key": key,
                "label": SPECIALIST_RESULT_KEYS.get(key, key),
                "validation_packet_count": len(packets),
                "claim_count": specialist_claim_count,
                "candidate_url_count": len(specialist_candidate_urls),
                "claim_source_url_count": len(specialist_claim_urls),
                "url_count": len(specialist_candidate_urls | specialist_claim_urls),
                "provider_ref_count": len(specialist_provider_refs),
            }
        )

    verified_supporting_urls: set[str] = set()
    memo = _json_object_from_text(evidence_memo) if evidence_memo else None
    if memo is not None:
        for source in memo.get("verified_sources") or []:
            if not isinstance(source, dict) or not source.get("supports_claim_ids"):
                continue
            url = _canonical_adjudicator_candidate_url(source.get("url"))
            url = _normal_source_url(url)
            if url:
                verified_supporting_urls.add(url)
        for claim in memo.get("confirmed_claims") or []:
            if not isinstance(claim, dict):
                continue
            for source in claim.get("evidence") or []:
                if not isinstance(source, dict):
                    continue
                url = _canonical_adjudicator_candidate_url(source.get("url"))
                url = _normal_source_url(url)
                if url:
                    verified_supporting_urls.add(url)

    read_verified_supporting_urls = verified_supporting_urls & reader_returned_source_urls
    failure_reason_counts: dict[str, int] = {}
    for item in reader_failed_sources:
        bucket = item.get("reason_bucket") or "other"
        failure_reason_counts[bucket] = failure_reason_counts.get(bucket, 0) + 1

    return {
        "specialist_output_count": len(specialist_outputs),
        "validation_packet_count": packet_count,
        "claim_count": claim_count,
        "packet_candidate_url_count": len(candidate_urls),
        "packet_claim_source_url_count": len(claim_source_urls),
        "packet_url_count": len(packet_urls),
        "packet_provider_ref_count": len(provider_refs),
        "reader_requested_url_count": len(reader_requested_urls),
        "packet_urls_passed_to_reader_count": len(packet_urls & reader_requested_urls),
        "reader_urls_not_in_packets": sorted(reader_requested_urls - packet_urls),
        "packet_urls_not_passed": sorted(packet_urls - reader_requested_urls),
        "packet_urls_attempted_by_reader_count": len(packet_urls & reader_attempted_urls),
        "reader_attempted_urls_not_in_packets": sorted(
            reader_attempted_urls - packet_urls
        ),
        "packet_urls_not_attempted": sorted(packet_urls - reader_attempted_urls),
        "grounding_entry_url_count": len(grounding_entry_urls),
        "grounding_urls_passed_to_reader_count": len(
            grounding_entry_urls & reader_requested_urls
        ),
        "grounding_urls_attempted_by_reader_count": len(
            grounding_entry_urls & reader_attempted_urls
        ),
        "grounding_urls_not_attempted": sorted(
            grounding_entry_urls - reader_attempted_urls
        ),
        "captured_source_url_count": len(captured_source_urls),
        "captured_urls_passed_to_reader_count": len(
            captured_source_urls & reader_requested_urls
        ),
        "captured_urls_attempted_by_reader_count": len(
            captured_source_urls & reader_attempted_urls
        ),
        "captured_urls_not_attempted": sorted(
            captured_source_urls - reader_attempted_urls
        ),
        "reader_attempted_urls_not_in_packets_or_captured": sorted(
            reader_attempted_urls - packet_urls - captured_source_urls
        ),
        "reader_auto_appended_url_count": reader_auto_appended_count,
        "reader_attempted_url_count": read_counts["attempted"],
        "reader_attempted_unique_url_count": len(reader_attempted_urls),
        "reader_successful_url_count": read_counts["successful"],
        "reader_failed_url_count": read_counts["failed"],
        "reader_skipped_url_count": read_counts["skipped"],
        "reader_rejected_url_count": read_counts["rejected"],
        "reader_invalid_url_count": read_counts["invalid"],
        "reader_returned_source_url_count": len(reader_returned_source_urls),
        "verified_supporting_url_count": len(verified_supporting_urls),
        "read_verified_supporting_url_count": len(read_verified_supporting_urls),
        "reader_successful_urls": sorted(reader_successful_urls),
        "reader_failed_sources": reader_failed_sources,
        "reader_failure_reason_counts": failure_reason_counts,
        "reader_auto_appended_urls": sorted(reader_auto_appended_urls),
        "reader_returned_source_urls": sorted(reader_returned_source_urls),
        "verified_supporting_urls": sorted(verified_supporting_urls),
        "read_verified_supporting_urls": sorted(read_verified_supporting_urls),
        "specialists": specialist_rows,
    }


def parse_run(events: list[Any]) -> dict[str, Any]:
    """Consume a list of captured ADK events and return a flat run record.

    Output shape (all fields always present):
        grounding_entries: list[dict]        # {url, domain, title} from grounding metadata
        fetched_urls: list[str]              # unique URLs passed to concrete page readers
        provider_pills: list[dict]           # _tool_src_* state_delta entries
        drawer_sources: list[dict]           # what sources[] would contain
        specialists_dispatched: list[str]    # specialist tool calls observed
        final_outcome: "ok" | "unknown"
        final_report: str                    # report_writer final text
        evidence_memo: str                   # evidence_adjudicator output
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
    adjudicator_requested_urls: set[str] = set()
    adjudicator_attempted_urls: set[str] = set()
    adjudicator_successful_urls: set[str] = set()
    adjudicator_failed_sources: list[dict[str, str]] = []
    adjudicator_returned_source_urls: set[str] = set()
    adjudicator_auto_appended_urls: set[str] = set()
    adjudicator_auto_appended_count = 0
    provider_pills: list[dict] = []
    fetched_source_pills: list[dict] = []
    specialists_dispatched: list[str] = []
    final_report: str = ""
    evidence_memo: str = ""
    specialist_outputs: dict[str, str] = {}
    tool_call_counts: dict[str, int] = {}
    authors_seen: dict[str, int] = {}
    token_totals = {"prompt": 0, "candidates": 0, "total": 0}
    adjudicator_read_counts = {
        "attempted": 0,
        "successful": 0,
        "failed": 0,
        "skipped": 0,
        "rejected": 0,
        "invalid": 0,
    }

    for event in events:
        author = _get(event, "author") or "?"
        authors_seen[author] = authors_seen.get(author, 0) + 1

        # Grounding entries from grounding_metadata.grounding_chunks[].web.
        for src in extract_sources_from_grounding(event):
            url = src.get("url")
            if url and url not in grounding_entries_by_url:
                grounding_entries_by_url[url] = {
                    "url": url,
                    "domain": src.get("domain") or _domain_of(url),
                    "title": src.get("title"),
                }

        # Tool calls — count and capture URLs for concrete page readers
        for part in _iter_parts(event):
            fc = _get(part, "function_call")
            name = _get(fc, "name") if fc else None
            if name:
                tool_call_counts[name] = tool_call_counts.get(name, 0) + 1
                if name == "fetch_web_content":
                    args = _get(fc, "args") or {}
                    url = args.get("url") if isinstance(args, dict) else None
                    if isinstance(url, str) and url:
                        fetched_urls.add(url)
                elif name in (
                    "fetch_web_content_batch",
                    "read_public_pages",
                    "read_adjudicator_sources",
                ):
                    args = _get(fc, "args") or {}
                    urls = args.get("urls") if isinstance(args, dict) else None
                    if isinstance(urls, list):
                        for url in urls:
                            if not isinstance(url, str) or not url:
                                continue
                            if name == "read_adjudicator_sources":
                                canonical_url = _canonical_adjudicator_candidate_url(url)
                                if canonical_url:
                                    adjudicator_requested_urls.add(canonical_url)
                                continue
                            fetched_urls.add(url)

            fr = _get(part, "function_response")
            response = _get(fr, "response") if fr else None
            response_name = _get(fr, "name") if fr else None
            if isinstance(response, dict):
                if response_name in (
                    "search_and_read_public_pages",
                    "read_web_pages",
                    "read_public_page",
                    "read_public_pages",
                    "read_adjudicator_sources",
                ):
                    for source in response.get("sources") or []:
                        if isinstance(source, dict):
                            if response_name == "read_adjudicator_sources":
                                url = source.get("url")
                                if isinstance(url, str) and url:
                                    canonical_url = _normal_source_url(url) or url
                                    adjudicator_returned_source_urls.add(canonical_url)
                                    fetched_urls.add(canonical_url)
                                continue
                            fetched_source_pills.append(source)
                    if response_name == "read_adjudicator_sources":
                        for result in response.get("results") or []:
                            if not isinstance(result, dict):
                                continue
                            url = result.get("url")
                            requested_url = result.get("requested_url")
                            attempted_url = (
                                requested_url if isinstance(requested_url, str) else url
                            )
                            attempted_canonical_url = (
                                _canonical_adjudicator_candidate_url(attempted_url)
                                if isinstance(attempted_url, str)
                                else None
                            )
                            actual_canonical_url = (
                                _canonical_adjudicator_candidate_url(url)
                                if isinstance(url, str)
                                else None
                            )
                            if attempted_canonical_url:
                                adjudicator_attempted_urls.add(attempted_canonical_url)
                            if actual_canonical_url:
                                fetched_urls.add(actual_canonical_url)
                                if result.get("status") == "success":
                                    adjudicator_successful_urls.add(actual_canonical_url)
                                else:
                                    reason = str(
                                        result.get("error_message")
                                        or result.get("reason")
                                        or result.get("error")
                                        or result.get("status")
                                        or "read failed"
                                    )
                                    adjudicator_failed_sources.append(
                                        {
                                            "url": actual_canonical_url
                                            or attempted_canonical_url,
                                            "reason": reason,
                                            "reason_bucket": _reader_failure_bucket(
                                                result.get("_error_reason") or reason
                                            ),
                                        }
                                    )
                        for source, dest in (
                            ("attempted_count", "attempted"),
                            ("success_count", "successful"),
                            ("failed_count", "failed"),
                            ("skipped_count", "skipped"),
                            ("rejected_count", "rejected"),
                            ("invalid_count", "invalid"),
                        ):
                            value = response.get(source)
                            if isinstance(value, int):
                                adjudicator_read_counts[dest] += value
                        for url in response.get("auto_appended_urls") or []:
                            canonical_url = _canonical_adjudicator_candidate_url(url)
                            if canonical_url:
                                adjudicator_auto_appended_urls.add(canonical_url)
                        auto_appended_count = response.get("auto_appended_count")
                        if isinstance(auto_appended_count, int):
                            adjudicator_auto_appended_count += auto_appended_count
                        else:
                            adjudicator_auto_appended_count += len(
                                response.get("auto_appended_urls") or []
                            )
                elif (
                    response_name == "fetch_web_content"
                    and response.get("status") == "success"
                ):
                    source = build_fetched_source(
                        response.get("url"), response.get("content")
                    )
                    if source:
                        fetched_source_pills.append(source)
                elif response_name == "fetch_web_content_batch":
                    for item in response.get("results") or []:
                        if (
                            not isinstance(item, dict)
                            or item.get("status") != "success"
                        ):
                            continue
                        source = build_fetched_source(item.get("url"), item.get("content"))
                        if source:
                            fetched_source_pills.append(source)

        # state_delta inspection: provider pills and specialist/final outputs.
        sd = _state_delta(event)
        for key, value in sd.items():
            if key.startswith("_tool_src_") and isinstance(value, dict):
                provider_pills.append(value)
            elif key == "final_report" and isinstance(value, str):
                final_report = value
            elif key == "evidence_memo" and isinstance(value, str):
                evidence_memo = value
            elif key in SPECIALIST_RESULT_KEYS and isinstance(value, str):
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
    # grounding/search sources + fetched/verified source pills + provider pills.
    drawer_sources: list[dict] = []
    drawer_seen: set[str] = set()
    grounding_entries = list(grounding_entries_by_url.values())
    fetched_source_urls = {
        url
        for url in (
            _canonical_adjudicator_candidate_url(entry.get("url"))
            for entry in fetched_source_pills
            if isinstance(entry, dict)
        )
        if url
    }
    captured_source_urls = set(grounding_entries_by_url) | fetched_source_urls
    for entry in grounding_entries:
        _append_drawer_source(
            drawer_sources,
            drawer_seen,
            {**entry, "provider": "grounding"},
            kind="grounding",
        )
    for entry in [
        *fetched_source_pills,
        *_read_verified_evidence_sources(
            evidence_memo, adjudicator_returned_source_urls
        ),
    ]:
        _append_drawer_source(drawer_sources, drawer_seen, entry, kind="fetched")
    for pill in provider_pills:
        _append_drawer_source(drawer_sources, drawer_seen, pill, kind="provider")

    source_funnel = _source_funnel(
        specialist_outputs=specialist_outputs,
        reader_requested_urls=adjudicator_requested_urls,
        reader_attempted_urls=adjudicator_attempted_urls,
        reader_successful_urls=adjudicator_successful_urls,
        reader_failed_sources=adjudicator_failed_sources,
        reader_returned_source_urls=adjudicator_returned_source_urls,
        grounding_entry_urls=set(grounding_entries_by_url),
        captured_source_urls=captured_source_urls,
        reader_auto_appended_urls=adjudicator_auto_appended_urls,
        reader_auto_appended_count=adjudicator_auto_appended_count,
        evidence_memo=evidence_memo,
        read_counts=adjudicator_read_counts,
    )

    return {
        "grounding_entries": grounding_entries,
        "fetched_urls": sorted(fetched_urls),
        "provider_pills": provider_pills,
        "drawer_sources": drawer_sources,
        "specialists_dispatched": specialists_dispatched,
        "final_outcome": final_outcome,
        "final_report": final_report,
        "evidence_memo": evidence_memo,
        "specialist_outputs": specialist_outputs,
        "source_funnel": source_funnel,
        "tool_call_counts": tool_call_counts,
        "authors_seen": authors_seen,
        "token_totals": token_totals,
    }
