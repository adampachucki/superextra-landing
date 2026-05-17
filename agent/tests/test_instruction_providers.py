"""Tests for instruction provider functions in agent.py."""

import json

import pytest
from google.genai import types

from superextra_agent.agent import (
    _CONTINUATION_NOTES_KEY,
    _continue_research_instruction,
    _evidence_adjudicator_instruction,
    _format_specialist_reports,
    _record_continuation_notes,
    _record_evidence_adjudicator_fallback,
    _report_writer_instruction,
    _research_lead_instruction,
    _router_instruction,
)
from superextra_agent.specialists import _make_instruction
from superextra_agent.web_tools import ADJUDICATOR_READ_RESULT_STATE_KEY


class MockCtx:
    def __init__(self, state=None):
        self.state = state or {}


class MockCallbackCtx:
    def __init__(self, state=None, user_text=""):
        self.state = state or {}
        self.user_content = types.Content(
            role="user",
            parts=[types.Part(text=user_text)],
        )


class TestResearchLeadInstruction:
    def test_injects_places_context(self):
        ctx = MockCtx(state={"places_context": "Restaurant XYZ data here"})

        result = _research_lead_instruction(ctx)

        assert "Restaurant XYZ data here" in result
        assert "## Market Source Profiles" in result

    def test_default_when_missing(self):
        ctx = MockCtx(state={})

        result = _research_lead_instruction(ctx)

        assert "No Google Places data available." in result

    def test_appends_existing_results_on_follow_up(self):
        ctx = MockCtx(state={
            "places_context": "Restaurant data",
            "market_result": "Market findings here",
            "pricing_result": "Pricing findings here",
        })

        result = _research_lead_instruction(ctx)

        assert "Existing research from prior turn" in result
        assert "Market Landscape" in result
        assert "Menu & Pricing" in result
        assert "Prior research plan" not in result

    def test_no_follow_up_note_when_no_results(self):
        ctx = MockCtx(state={"places_context": "Restaurant data"})

        result = _research_lead_instruction(ctx)

        assert "Existing research from prior turn" not in result

    def test_ignores_default_specialist_output(self):
        ctx = MockCtx(state={
            "places_context": "Data",
            "market_result": "Agent did not produce output.",
        })

        result = _research_lead_instruction(ctx)

        assert "Existing research from prior turn" not in result

    def test_does_not_include_final_report_chart_contract(self):
        ctx = MockCtx(state={"places_context": "Restaurant data"})

        result = _research_lead_instruction(ctx)

        assert "```chart" not in result

    def test_research_coverage_is_internal_not_report_guidance(self):
        ctx = MockCtx(state={"places_context": "Restaurant data"})

        result = _research_lead_instruction(ctx)

        assert "internal research coverage note" in result
        assert "The note is for audit" in result
        assert "The report writer\ndoes not read it" in result
        assert "Do not list discovered entities" in result
        assert "Do not decide which specialist findings matter most" in result

    def test_dynamic_researcher_guidance_is_deep_dive_or_connector(self):
        ctx = MockCtx(state={"places_context": "Restaurant data"})

        result = _research_lead_instruction(ctx)

        assert "Use at least two non-dynamic specialists for every research report" in result
        assert "flexible deep dive, verification, or cross-signal connection" in result
        assert "`dynamic_researcher_1`, then `dynamic_researcher_2`, then `dynamic_researcher_3`" in result
        assert "causes, mechanisms, relationships between findings" in result
        assert "named-entity checks" in result
        assert "Use the dynamic researcher as an added deepening pass" in result
        assert "Do not ask the dynamic researcher to repeat another specialist's evidence search" in result
        assert "Did at least two non-dynamic specialists cover distinct evidence surfaces" in result
        assert "If no dynamic researcher has been used, run one" in result


class TestReportWriterInstruction:
    def test_injects_places_context_specialist_reports_and_evidence_memo(self):
        ctx = MockCtx(state={
            "places_context": "Restaurant XYZ data",
            "writer_brief": "Focus on demand and pricing links.",
            "research_coverage": "Lead thinks demand is most important.",
            "evidence_memo": "Confirmed weekday demand; pricing claim unresolved.",
            "market_result": "Market demand is weekday-heavy.",
            "pricing_result": "Average entree price is 21 USD.",
        })

        result = _report_writer_instruction(ctx)

        assert "Restaurant XYZ data" in result
        assert "Focus on demand and pricing links." not in result
        assert "Lead thinks demand is most important." not in result
        assert "Confirmed weekday demand; pricing claim unresolved." in result
        assert "Market demand is weekday-heavy." in result
        assert "Average entree price is 21 USD." in result
        assert "### Market Landscape" in result
        assert "### Menu & Pricing" in result
        assert "Evidence Memo as claim-status and source-quality metadata" in result
        assert "Do not cite unread pages as evidence" in result

    def test_defaults_when_state_empty(self):
        ctx = MockCtx(state={})

        result = _report_writer_instruction(ctx)

        assert "No restaurant data available." in result
        assert "No specialist reports available." in result
        assert "No adjudicated evidence memo available." in result

    def test_failed_closed_memo_keeps_specialist_reports_with_source_limits(self):
        ctx = MockCtx(
            state={
                "places_context": "Google Places rating: 4.5",
                "evidence_memo": json.dumps(
                    {
                        "adjudication_status": "failed_closed",
                        "confirmed_claims": [],
                        "contradicted_claims": [],
                        "unsupported_claims": [],
                        "unresolved_claims": [
                            {
                                "id": "claim-1",
                                "claim": "Unverified noodle trend claim",
                                "reason": "not adjudicated",
                            }
                        ],
                        "verified_sources": [],
                        "unread_sources": [],
                        "read_summary": {"attempted_url_count": 3},
                    }
                ),
                "market_result": "Raw specialist says Unverified noodle trend claim.",
            }
        )

        result = _report_writer_instruction(ctx)

        assert "Google Places rating: 4.5" in result
        assert "Raw specialist says Unverified noodle trend claim." in result
        assert "withheld_unresolved_claim_count" in result
        assert "Phrase public-web material that was not confirmed" in result

    def test_handles_curly_braces_in_injected_material(self):
        ctx = MockCtx(state={
            "places_context": "Context with {braces}",
            "market_result": "Source note: `{city: 'Warsaw'}`",
        })

        result = _report_writer_instruction(ctx)

        assert "{braces}" in result
        assert "{city: 'Warsaw'}" in result

    def test_chart_json_braces_are_escaped_for_format(self):
        ctx = MockCtx(state={"market_result": "Report"})

        result = _report_writer_instruction(ctx)

        assert '```chart\n{"type":"bar"' in result

    def test_retention_contract_preserves_all_findings(self):
        ctx = MockCtx(state={
            "market_result": "Zołza closed. Matcha Ma opened.",
            "dynamic_result_1": "Nam-Viet remains operational nearby.",
            "dynamic_result_2": "Filmor has a visible launch signal.",
            "dynamic_result_3": "Brassica has weak closure evidence.",
        })

        result = _report_writer_instruction(ctx)

        assert "The customer expects deep research, not a compressed summary" in result
        assert "Do not rely on any lead-authored summary" in result
        assert "Err on the side of a long, detailed report" in result
        assert "especially its `Writer Material` section, as must-carry research material" in result
        assert "Do not reproduce packet JSON" in result
        assert "memo JSON" in result
        assert "Do not compress findings to fit an assumed length" in result
        assert "Do not show raw access failures" in result
        assert "Translate material access limits into plain research caveats" in result
        assert "Use the format that preserves detail most clearly" in result
        assert "what the evidence means for that venue" in result
        assert "Weave this into the synthesis or group it separately" in result
        assert "Do not collapse several concrete findings" in result
        assert "Do not compress several insights into one broad takeaway" in result
        assert "every specialist report has visible representation" in result
        assert "do not let synthesis merge away concrete findings" in result
        assert "2-4 suggested follow-up research prompts" in result
        assert "short, ready-to-send user prompt" in result
        assert 'Do not write "Ask the researcher to", "Request a deep dive"' in result
        assert "owner-facing questions" in result
        assert "center each follow-up prompt on that venue" in result
        assert "concrete operator decision, risk, opportunity, or unresolved check" in result
        assert "only when framed through what they could change for the target venue" in result
        assert "general market questions" in result
        assert "Do not omit evidence to make room for them" in result
        assert "Zołza closed" in result
        assert "Nam-Viet remains operational nearby" in result
        assert "Filmor has a visible launch signal" in result
        assert "Brassica has weak closure evidence" in result

    def test_strips_specialist_validation_packets_from_writer_input(self):
        ctx = MockCtx(state={
            "market_result": (
                "Market finding.\n\n"
                "## Writer Material\n\n"
                "- Preserve this caveat.\n\n"
                "### Validation Packet:\n\n"
                "```json\n"
                '{"claims_for_validation":[],"candidate_sources":[]}\n'
                "```"
            )
        })

        result = _report_writer_instruction(ctx)

        assert "Market finding" in result
        assert "Preserve this caveat" in result
        assert "claims_for_validation" not in result
        assert "candidate_sources" not in result

    def test_specialist_formatter_can_preserve_validation_packets_for_adjudicator(self):
        state = {
            "market_result": (
                "Market finding.\n\n"
                "### **Validation Packet:**\n\n"
                "```json\n"
                '{"claims_for_validation":[]}\n'
                "```"
            )
        }

        result = _format_specialist_reports(state, include_validation_packets=True)

        assert "Market finding" in result
        assert "claims_for_validation" in result


class TestEvidenceAdjudicatorInstruction:
    def test_injects_full_specialist_packets(self):
        ctx = MockCtx(state={
            "places_context": "Restaurant XYZ data",
            "places_by_id": {
                "ChIJtarget": {
                    "google_place_id": "ChIJtarget",
                    "name": "Target",
                    "lat": 54.0,
                    "lng": 18.0,
                }
            },
            "market_result": (
                "Market finding.\n\n"
                "### Validation Packet\n\n"
                "```json\n"
                "{"
                '"claims_for_validation":[{"id":"market-1","claim":"Target opened in 2025"}],'
                '"candidate_sources":[{"url":"https://example.com/opening","priority":"high"}]'
                "}\n"
                "```"
            ),
        })

        result = _evidence_adjudicator_instruction(ctx)

        assert "Restaurant XYZ data" in result
        assert "Google Place ID: ChIJtarget" in result
        assert "Same-Run Captured Web Sources" in result
        assert "claims_for_validation" in result
        assert "candidate_sources" in result
        assert "https://example.com/opening" in result
        assert "Use only the bounded source reader" in result
        assert "Do not use search" in result
        assert "read_summary" in result
        assert '```json\n{' in result

    def test_defaults_when_state_empty(self):
        result = _evidence_adjudicator_instruction(MockCtx(state={}))

        assert "No restaurant data available." in result
        assert "No structured place registry available." in result
        assert "No same-run grounding or fetched web sources captured." in result
        assert "No specialist reports available." in result

    def test_preserves_braces_in_specialist_material(self):
        result = _evidence_adjudicator_instruction(
            MockCtx(state={"market_result": "Source note: `{city: 'Warsaw'}`"})
        )

        assert "{city: 'Warsaw'}" in result


class TestEvidenceAdjudicatorFallback:
    def test_does_not_overwrite_existing_memo(self):
        existing = {
            "confirmed_claims": [],
            "contradicted_claims": [],
            "unsupported_claims": [],
            "unresolved_claims": [],
            "read_summary": {},
        }
        ctx = MockCallbackCtx(state={"evidence_memo": json.dumps(existing)})

        _record_evidence_adjudicator_fallback(callback_context=ctx)

        assert json.loads(ctx.state["evidence_memo"]) == existing

    def test_overwrites_memo_missing_packet_claims(self):
        incomplete = {
            "confirmed_claims": [],
            "contradicted_claims": [],
            "unsupported_claims": [],
            "unresolved_claims": [],
            "read_summary": {},
        }
        ctx = MockCallbackCtx(
            state={
                "evidence_memo": json.dumps(incomplete),
                "market_result": (
                    "Finding.\n\n"
                    "### Validation Packet\n\n"
                    "```json\n"
                    "{"
                    '"claims_for_validation":['
                    '{"id":"claim-1","claim":"Target opened in May 2026",'
                    '"source_urls":["https://example.com/open"]}'
                    "],"
                    '"candidate_sources":[{"url":"https://example.com/open"}]'
                    "}\n"
                    "```"
                ),
            }
        )

        _record_evidence_adjudicator_fallback(callback_context=ctx)

        memo = json.loads(ctx.state["evidence_memo"])
        assert memo["adjudication_status"] == "failed_closed"
        assert memo["unresolved_claims"][0]["id"] == "claim-1"

    def test_duplicate_packet_claim_ids_still_require_each_claim_text(self):
        incomplete = {
            "confirmed_claims": [{"id": "claim-1", "claim": "Claim A"}],
            "contradicted_claims": [],
            "unsupported_claims": [],
            "unresolved_claims": [],
            "read_summary": {},
        }
        ctx = MockCallbackCtx(
            state={
                "evidence_memo": json.dumps(incomplete),
                "market_result": (
                    "Finding.\n\n"
                    "### Validation Packet\n\n"
                    "```json\n"
                    "{"
                    '"claims_for_validation":['
                    '{"id":"claim-1","claim":"Claim A",'
                    '"source_urls":["https://example.com/a"]},'
                    '{"id":"claim-1","claim":"Claim B",'
                    '"source_urls":["https://example.com/b"]}'
                    "],"
                    '"candidate_sources":['
                    '{"url":"https://example.com/a"},'
                    '{"url":"https://example.com/b"}'
                    "]}"
                    "\n```"
                ),
            }
        )

        _record_evidence_adjudicator_fallback(callback_context=ctx)

        memo = json.loads(ctx.state["evidence_memo"])
        assert memo["adjudication_status"] == "failed_closed"
        assert [claim["claim"] for claim in memo["unresolved_claims"]] == [
            "Claim A",
            "Claim B",
        ]

    def test_overwrites_non_structured_memo(self):
        ctx = MockCallbackCtx(
            state={
                "evidence_memo": "Research unavailable: ValueError",
                "market_result": (
                    "Finding.\n\n"
                    "### Validation Packet\n\n"
                    "```json\n"
                    "{"
                    '"claims_for_validation":['
                    '{"id":"claim-1","claim":"Target opened in May 2026",'
                    '"source_urls":["https://example.com/open"]}'
                    "],"
                    '"candidate_sources":[{"url":"https://example.com/open"}]'
                    "}\n"
                    "```"
                ),
            }
        )

        _record_evidence_adjudicator_fallback(callback_context=ctx)

        memo = json.loads(ctx.state["evidence_memo"])
        assert memo["adjudication_status"] == "failed_closed"
        assert memo["unresolved_claims"][0]["claim"] == "Target opened in May 2026"

    def test_records_fail_closed_memo_from_packets_and_read_result(self):
        ctx = MockCallbackCtx(
            state={
                "market_result": (
                    "Finding.\n\n"
                    "### Validation Packet\n\n"
                    "```json\n"
                    "{"
                    '"claims_for_validation":['
                    '{"id":"claim-1","claim":"Target opened in May 2026",'
                    '"source_urls":["https://example.com/open"],'
                    '"provider_refs":["Google Places: target"]}'
                    "],"
                    '"candidate_sources":[{"url":"https://example.com/open"}]'
                    "}\n"
                    "```"
                ),
                ADJUDICATOR_READ_RESULT_STATE_KEY: {
                    "requested_count": 2,
                    "attempted_count": 2,
                    "successful_count": 1,
                    "failed_count": 1,
                    "sources": [
                        {
                            "url": "https://example.com/open",
                            "title": "Opening",
                            "domain": "example.com",
                            "provider": "fetched_page",
                        }
                    ],
                    "failed_sources": [
                        {"url": "https://example.com/closed", "reason": "HTTP 404"}
                    ],
                    "skipped_urls": ["https://example.com/skipped"],
                    "invalid_urls": [],
                },
            }
        )

        _record_evidence_adjudicator_fallback(callback_context=ctx)

        memo = json.loads(ctx.state["evidence_memo"])
        assert memo["adjudication_status"] == "failed_closed"
        assert memo["confirmed_claims"] == []
        assert memo["unresolved_claims"] == [
            {
                "id": "claim-1",
                "claim": "Target opened in May 2026",
                "reason": (
                    "The evidence adjudicator did not produce a claim-status "
                    "memo, so this specialist claim must be treated as "
                    "unresolved. Packet source URLs are not read authority; no "
                    "captured-source read produced adjudicated support for this claim. Provider "
                    "references were present, but no adjudicated provider "
                    "confirmation was recorded for this claim."
                ),
            }
        ]
        assert memo["verified_sources"] == [
            {
                "url": "https://example.com/open",
                "title": "Opening",
                "domain": "example.com",
                "supports_claim_ids": [],
                "limits": (
                    "Fetched by the bounded reader, but no adjudicated claim "
                    "support was recorded."
                ),
            }
        ]
        assert memo["unread_sources"] == [
            {"url": "https://example.com/closed", "reason": "HTTP 404"},
            {
                "url": "https://example.com/skipped",
                "reason": "duplicate or already read in this adjudication run",
            },
        ]
        assert memo["read_summary"] == {
            "requested_url_count": 2,
            "attempted_url_count": 2,
            "successful_url_count": 1,
            "failed_url_count": 1,
            "notes": (
                "The adjudicator failed closed because no claim-status memo "
                "was persisted."
            ),
        }


class TestMakeInstruction:
    def test_returns_provider_that_injects_places_context(self):
        provider = _make_instruction("market_landscape")

        ctx = MockCtx(state={"places_context": "Competitor data for area"})
        result = provider(ctx)

        assert "Competitor data for area" in result
        assert "## Market Source Profiles" not in result

    def test_provider_uses_default_when_missing(self):
        provider = _make_instruction("market_landscape")

        ctx = MockCtx(state={})
        result = provider(ctx)

        assert "No Google Places data available." in result

    def test_review_analyst_disclaims_web_fetch_tools(self):
        """review_analyst is structured-tools only (TripAdvisor + Google
        Reviews APIs). The body file explicitly disclaims web research tools
        to keep it inside the provider-only boundary."""
        provider = _make_instruction("review_analyst")

        ctx = MockCtx(
            state={
                "places_context": "Target data",
                "places_by_id": {
                    "ChIJtarget": {
                        "google_place_id": "ChIJtarget",
                        "name": "Target",
                    }
                },
            }
        )
        result = provider(ctx)

        assert "You do not have `google_search` or page-fetch tools" in result
        assert "## Market Source Profiles" not in result
        assert "Pyszne.pl" not in result
        assert "ChIJtarget" in result
        assert "Target Google Place ID" not in result
        assert "For each requested place" in result
        assert 'source_type: "provider_data"' in result
        assert "`provider_refs`" in result
        assert "Do not invent URLs" in result

    def test_specialists_surface_writer_material(self):
        provider = _make_instruction("market_landscape")

        result = provider(MockCtx(state={"places_context": "Target data"}))

        assert "Surface all useful material you find" in result
        assert "Do not compress it to top takeaways" in result
        assert "Do not include raw tool errors" in result
        assert "meaningful evidence limits" in result
        assert "`Writer Material` section" in result
        assert "`Validation Packet` section" in result
        assert "implications for the target venue" in result

    def test_specialists_have_source_reading_workflow(self):
        provider = _make_instruction("market_landscape")

        result = provider(MockCtx(state={"places_context": "Target data"}))

        assert "## Search And Source Reading" in result
        assert "Search and page reading have different jobs" in result
        assert "Search snippets and search-result source pills are not the same as reading a page" in result
        assert "Use `google_search` for source discovery" in result
        assert "Use `read_web_pages` to inspect concrete public URLs" in result
        assert "Treat search snippets and grounding snippets as discovery context" in result
        assert "Treat page reads as evidence" in result
        assert "search_and_read_public_pages" not in result
        assert "search_web" not in result
        assert "fetch_web_content" not in result
        assert "Jina Reader" not in result
        assert "article pages, official announcements, public reports, PDFs" in result
        assert "inspect those pages before broadening the search" in result
        assert "read the strongest 1-3 pages during your research" in result
        assert "Iterate from what the pages say" in result
        assert "Use `read_web_pages`" in result
        assert "After two or three searches" in result
        assert "Search and grounding sources may still appear as source pills" in result
        assert "proof that a page was read" in result
        assert "Do not reconstruct, shorten, normalize across subdomains" in result

    def test_specialists_require_validation_packet(self):
        provider = _make_instruction("market_landscape")

        result = provider(MockCtx(state={"places_context": "Target data"}))

        assert "### Validation Packet" in result
        assert "claims_for_validation" in result
        assert "candidate_sources" in result
        assert "provider_refs" in result
        assert "provider_ref" in result
        assert "supports_claim_ids" in result
        assert "do not invent URLs" in result
        assert '```json\n{' in result
        assert '"claim_type": "venue_fact | price | opening_closure | trend | review_signal | estimate | other"' in result


class TestContinueResearchInstruction:
    def test_injects_prior_report(self):
        ctx = MockCtx(state={
            "final_report": "## Market Report\nKey findings here.",
            "places_context": "Restaurant XYZ data",
            "places_by_id": {
                "ChIJcomp": {
                    "google_place_id": "ChIJcomp",
                    "name": "Competitor A",
                    "lat": 1.0,
                    "lng": 2.0,
                }
            },
            "market_result": "Market specialist notes",
            "research_coverage": "Coverage notes and source gaps",
            "continuation_notes": "Turn 2 found competitor A started brunch.",
        })

        result = _continue_research_instruction(ctx)

        assert "## Market Report" in result
        assert "Restaurant XYZ data" in result
        assert "Market specialist notes" in result
        assert "Coverage notes and source gaps" in result
        assert "competitor A started brunch" in result
        assert "Market Landscape" in result
        assert "Competitor A" in result
        assert "Google Place ID: ChIJcomp" in result

    def test_defaults_when_state_empty(self):
        ctx = MockCtx(state={})

        result = _continue_research_instruction(ctx)

        assert "No prior report available." in result
        assert "No specialist notes available." in result
        assert "No research coverage notes available." in result
        assert "No continuation notes yet." in result
        assert "No restaurant data available." in result
        assert "No structured place registry available." in result
        assert "No research plan available." not in result

    def test_handles_curly_braces_in_report(self):
        ctx = MockCtx(state={
            "final_report": "Code: `plt.bar(x, y, color={0: 'red'})`",
            "places_context": "Data with {braces}",
        })

        result = _continue_research_instruction(ctx)

        assert "color={0: 'red'}" in result
        assert "{braces}" in result

    def test_strips_specialist_validation_packets_from_continuation_input(self):
        ctx = MockCtx(state={
            "final_report": "Existing report",
            "market_result": (
                "Market finding.\n\n"
                "### Validation Packet\n\n"
                "```json\n"
                '{"claims_for_validation":[],"candidate_sources":[]}\n'
                "```"
            ),
        })

        result = _continue_research_instruction(ctx)

        assert "Market finding" in result
        assert "claims_for_validation" not in result
        assert "candidate_sources" not in result

    def test_broad_new_work_boundary_is_explicit(self):
        result = _continue_research_instruction(MockCtx(state={"final_report": "Existing report"}))

        assert "start a new research session" in result
        assert "Do not recreate a full market report" in result
        assert "broad new report" in result
        assert "different unrelated target" in result

    def test_source_discovery_goes_through_helpers(self):
        result = _continue_research_instruction(MockCtx(state={"final_report": "Existing report"}))

        assert "do focused research through one focused helper" in result
        assert "Use direct venue lookup tools only" in result
        assert "Structured provider lookups are allowed" in result
        assert "Google Reviews, TripAdvisor" in result
        assert "Use direct source fetches only when the URL is already known" in result
        assert "Do not do source-discovery searches directly in this agent" in result


class TestRecordContinuationNotes:
    def test_records_reply_in_session_state(self):
        ctx = MockCallbackCtx(
            state={
                "continue_research_reply": "Competitor A added brunch on weekends.",
                "turnIdx": 2,
            },
            user_text="Can you check competitor A brunch?",
        )

        _record_continuation_notes(callback_context=ctx)

        notes = ctx.state[_CONTINUATION_NOTES_KEY]
        assert "Turn 2" in notes
        assert "competitor A brunch" in notes
        assert "Competitor A added brunch" in notes

    def test_no_reply_means_no_state_delta(self):
        ctx = MockCallbackCtx(state={}, user_text="Question")

        _record_continuation_notes(callback_context=ctx)

        assert _CONTINUATION_NOTES_KEY not in ctx.state

    def test_keeps_notes_bounded(self):
        existing = "\n\n".join(
            f"### Turn {i}\nUser asked: old\nAnswer/follow-up findings: {'x' * 1200}"
            for i in range(10)
        )
        ctx = MockCallbackCtx(
            state={
                "continue_research_reply": "Latest useful finding.",
                _CONTINUATION_NOTES_KEY: existing,
            },
            user_text="Latest question",
        )

        _record_continuation_notes(callback_context=ctx)

        notes = ctx.state[_CONTINUATION_NOTES_KEY]
        assert len(notes) <= 6000
        assert "Latest useful finding" in notes
        assert "Turn 0" not in notes


class TestRouterInstruction:
    def test_report_delivered_note(self):
        ctx = MockCtx(state={"final_report": "Some report content"})

        result = _router_instruction(ctx)

        assert "report has already been delivered" in result
        assert "continue_research" in result

    def test_no_report_note(self):
        ctx = MockCtx(state={})

        result = _router_instruction(ctx)

        assert "No research has been done yet" in result
