"""Tests for instruction provider functions in agent.py."""

from pathlib import Path

from google.genai import types

from superextra_agent.agent import (
    _CONTINUATION_NOTES_KEY,
    _continue_research_instruction,
    _record_continuation_notes,
    _report_writer_instruction,
    _research_lead_instruction,
    _router_instruction,
)
from superextra_agent.specialists import _make_instruction

INSTRUCTIONS_DIR = Path(__file__).resolve().parent.parent / "superextra_agent" / "instructions"


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
        result = _research_lead_instruction(
            MockCtx(state={"places_context": "Restaurant XYZ data here"})
        )

        assert "Restaurant XYZ data here" in result
        assert "## Market Source Profiles" in result

    def test_appends_existing_results_on_follow_up(self):
        result = _research_lead_instruction(
            MockCtx(
                state={
                    "places_context": "Restaurant data",
                    "market_result": "Market findings here",
                    "pricing_result": "Pricing findings here",
                }
            )
        )

        assert "Existing research from prior turn" in result
        assert "Market Landscape" in result
        assert "Menu & Pricing" in result
        assert "Prior research plan" not in result

    def test_sufficiency_check_requires_read_or_qualified_evidence(self):
        result = _research_lead_instruction(
            MockCtx(state={"places_context": "Restaurant data"})
        )

        assert "Did specialists read material public pages" in result
        assert "Use at least two specialists for every research report" in result
        assert "A dynamic researcher can count when its brief owns a distinct deeper angle" in result
        assert "Did at least two specialists cover distinct evidence surfaces or deeper angles" in result
        assert "read page content, structured provider data, or clearly labeled search/grounding-only signals" in result
        assert "Would one focused dynamic researcher materially improve" in result
        assert "Run one when it would materially improve the answer" in result
        assert "Use at least two non-dynamic specialists" not in result
        assert "If no dynamic researcher has been used, run one" not in result

    def test_prompt_focus_and_benchmark_framing_render(self):
        result = _research_lead_instruction(
            MockCtx(state={"places_context": "Area focus: Williamsburg"})
        )

        assert "target venue, a site or area focus, or a broader market question" in result
        assert "separate nearby competitors from destination-level or category-leading comparables" in result
        assert "Do not force review or social analysis for an area/site prompt" in result

    def test_comparison_tables_and_brand_group_briefing_render(self):
        result = _research_lead_instruction(
            MockCtx(state={"places_context": "Target venue: Umami"})
        )

        assert "ask specialists for table-ready comparable dimensions" in result
        assert "used/not used" in result
        assert "multi-location brand or group" in result
        assert "separate location-level facts from brand-level activity" in result


class TestReportWriterInstruction:
    def test_injects_places_context_and_specialist_reports_only(self):
        result = _report_writer_instruction(
            MockCtx(
                state={
                    "places_context": "Restaurant XYZ data",
                    "writer_brief": "Focus on demand and pricing links.",
                    "research_coverage": "Lead thinks demand is most important.",
                    "unused_internal_memo": "Old memo should not be injected.",
                    "market_result": "Market demand is weekday-heavy.",
                    "pricing_result": "Average entree price is 21 USD.",
                }
            )
        )

        assert "Restaurant XYZ data" in result
        assert "Focus on demand and pricing links." not in result
        assert "Lead thinks demand is most important." not in result
        assert "Old memo should not be injected." not in result
        assert "Market demand is weekday-heavy." in result
        assert "Average entree price is 21 USD." in result
        assert "### Market Landscape" in result
        assert "### Menu & Pricing" in result
        assert "Treat the specialist reports as the research material" in result
        assert "Do not cite unread pages as evidence" in result

    def test_drops_legacy_validation_packets_from_specialist_reports(self):
        result = _report_writer_instruction(
            MockCtx(
                state={
                    "market_result": (
                        "Market finding to preserve.\n\n"
                        "### Validation Packet\n"
                        '{"claims_for_validation": ["old internal artifact"]}'
                    ),
                }
            )
        )

        assert "Market finding to preserve." in result
        assert "Validation Packet" not in result
        assert "claims_for_validation" not in result

    def test_defaults_when_state_empty(self):
        result = _report_writer_instruction(MockCtx(state={}))

        assert "No Google Places data available." in result
        assert "No specialist reports available." in result

    def test_handles_curly_braces_in_injected_material(self):
        result = _report_writer_instruction(
            MockCtx(
                state={
                    "places_context": "Context with {braces}",
                    "market_result": "Source note: `{city: 'Warsaw'}`",
                }
            )
        )

        assert "{braces}" in result
        assert "{city: 'Warsaw'}" in result

    def test_chart_json_braces_are_escaped_for_format(self):
        result = _report_writer_instruction(MockCtx(state={"market_result": "Report"}))

        assert '```chart\n{"type":"bar"' in result

    def test_report_shape_prefers_markdown_tables_for_comparisons(self):
        result = _report_writer_instruction(MockCtx(state={"market_result": "Report"}))

        assert "Prefer markdown tables for multi-entity, multi-metric comparisons" in result
        assert "Do not use custom HTML tables" in result

    def test_preserves_absence_caveats_and_source_quality_notes(self):
        result = _report_writer_instruction(MockCtx(state={"market_result": "Report"}))

        assert "Do not convert a checked absence into confirmed non-use" in result
        assert "not visible in checked public surfaces" in result
        assert "include a concise `Evidence Notes` section" in result
        assert "read`, `provider`, and `signal`" in result

    def test_retention_contract_preserves_all_findings(self):
        result = _report_writer_instruction(
            MockCtx(
                state={
                    "market_result": "Zolza closed. Matcha Ma opened.",
                    "dynamic_result_1": "Nam-Viet remains operational nearby.",
                    "dynamic_result_2": "Filmor has a visible launch signal.",
                    "dynamic_result_3": "Brassica has weak closure evidence.",
                }
            )
        )

        assert "The customer expects deep research, not a compressed summary" in result
        assert "Err on the side of a long, detailed report" in result
        assert "especially its `Writer Material` section, as must-carry research material" in result
        assert "Search or grounding-only signals are weaker context" in result
        assert "Do not reproduce raw internal evidence-note scaffolding" in result
        assert "Do not collapse several concrete findings" in result
        assert "2-4 suggested follow-up research prompts" in result
        assert "Zolza closed" in result
        assert "Nam-Viet remains operational nearby" in result
        assert "Filmor has a visible launch signal" in result
        assert "Brassica has weak closure evidence" in result

class TestMakeInstruction:
    def test_returns_provider_that_injects_places_context(self):
        provider = _make_instruction("market_landscape")

        result = provider(MockCtx(state={"places_context": "Competitor data for area"}))

        assert "Competitor data for area" in result
        assert "## Market Source Profiles" not in result

    def test_social_analyst_renders_with_platform_scope_markers(self):
        provider = _make_instruction("social_analyst")
        result = provider(MockCtx(state={"places_context": "Target data"}))
        # Specialist body's platform markers must survive instruction injection.
        for marker in ("TripAdvisor", "Facebook", "Instagram"):
            assert marker in result, f"missing {marker!r} in rendered social_analyst prompt"
        assert "fetch_tripadvisor_page" in result
        assert "fetch_facebook_page" in result
        assert "fetch_instagram_profile" in result
        assert "review_analyst" in result  # boundary clause references review_analyst
        assert "Target data" in result      # places_context injection
        # Discovery goes through search_serpapi (unified backend across all
        # platforms — Gemini google_search is unreliable for TripAdvisor).
        assert "search_serpapi" in result
        # URL-discipline: model can only fetch URLs obtained from search_serpapi.
        assert "did not first obtain from a `search_serpapi` result" in result
        # TikTok was dropped from v1 — neither discovery backend reliably
        # surfaces per-video URLs that fetch_tiktok_video can consume.
        assert "TikTok" not in result
        assert "fetch_tiktok_video" not in result

    def test_review_analyst_unifies_tripadvisor_on_serpapi(self):
        """review_analyst's TA discovery uses search_serpapi (URL-based),
        not the deleted find_tripadvisor_restaurant resolver. The model
        judges candidate fit from snippets — no prescribed verification."""
        provider = _make_instruction("review_analyst")

        result = provider(
            MockCtx(
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
        )

        # New unified flow
        assert "search_serpapi" in result
        assert "get_tripadvisor_reviews(url" in result
        assert "get_google_place_signals(place_id" in result
        assert "Restaurant_Review page URL" in result
        assert "clearly identifies the same venue" in result
        assert "treat absence as a finding" in result
        assert 'mode="deep"' in result
        assert "specific review count" in result
        assert "Do not fetch review samples for people-also-search" in result
        # Snippet usage: TA-rendered profile facts (rating/rank/total) are OK;
        # not as review evidence.
        assert "Do not treat search snippets as review evidence" in result
        # Deleted resolver must not leak back into the prompt
        assert "find_tripadvisor_restaurant" not in result
        # Surface contracts preserved
        assert "ChIJtarget" in result
        assert "Do not invent URLs" in result
        assert "Do not guess" in result

    def test_market_and_location_prompts_describe_google_place_signals(self):
        market = _make_instruction("market_landscape")(MockCtx(state={"places_context": "Target data"}))
        location = _make_instruction("location_traffic")(MockCtx(state={"places_context": "Target data"}))

        assert "get_google_place_signals(place_id, max_reviews=0)" in market
        assert "people-also-search competitors" in market
        assert "get_google_place_signals(place_id, max_reviews=0)" in location
        assert "popular-times histogram" in location

    def test_specialists_have_source_reading_workflow(self):
        provider = _make_instruction("market_landscape")

        result = provider(MockCtx(state={"places_context": "Target data"}))

        assert "## Search And Source Reading" in result
        assert "Search snippets and search-result source pills are not the same as reading a page" in result
        assert "Inspect the strongest few pages, not every result" in result
        assert "Search grounding will populate source pills when available" in result
        assert "do not create or guess URLs from titles" in result
        assert "For broad reconnaissance, search snippets first" in result
        assert "Completion gate: if your report uses public web/search evidence" in result
        assert "Treat URLs supplied in the brief as source metadata" in result
        assert "Treat page reads as evidence" in result
        assert "Do not say \"Sources read\"" in result
        assert "Continue searching only when the next query tests a new lead" in result
        assert "Search and grounding sources may still appear as source pills" in result
        assert "proof that a page was read" in result
        assert "search_public_web" not in result
        assert "### Evidence Notes" in result

    def test_specialists_surface_writer_material_and_evidence_notes(self):
        provider = _make_instruction("market_landscape")

        result = provider(MockCtx(state={"places_context": "Target data"}))

        assert "Surface all useful material you find" in result
        assert "meaningful evidence limits" in result
        assert "`Writer Material` section" in result
        assert "Include an `Evidence Notes` section" in result
        assert "implications for the target venue" in result

    def test_marketing_brand_visibility_inventory_renders(self):
        provider = _make_instruction("marketing_brand")

        result = provider(MockCtx(state={"places_context": "Target data"}))

        assert "wider brand or group" in result
        assert "separate brand-level marketing assets from location-specific evidence" in result
        assert "visible owned, discovery, reservation, delivery, PR, and social surfaces" in result
        assert "not definitive private channel usage" in result
        assert "Label search-only findings as `signal` in Evidence Notes" in result
        assert "visible owned-funnel features" in result
        assert "not visible in checked public surfaces" in result
        assert "guide listings, awards, critic recognition, platform badges, and local press honors" in result


class TestContinueResearchInstruction:
    def test_injects_prior_report(self):
        result = _continue_research_instruction(
            MockCtx(
                state={
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
                }
            )
        )

        assert "## Market Report" in result
        assert "Restaurant XYZ data" in result
        assert "Market specialist notes" in result
        assert "Coverage notes and source gaps" in result
        assert "competitor A started brunch" in result
        assert "Market Landscape" in result
        assert "Competitor A" in result
        assert "Google Place ID: ChIJcomp" in result

    def test_defaults_when_state_empty(self):
        result = _continue_research_instruction(MockCtx(state={}))

        assert "No prior report available." in result
        assert "No specialist notes available." in result
        assert "No research coverage notes available." in result
        assert "No continuation notes yet." in result
        assert "No Google Places data available." in result

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


class TestRouterInstruction:
    def test_report_delivered_note(self):
        result = _router_instruction(MockCtx(state={"final_report": "Some report content"}))

        assert "report has already been delivered" in result
        assert "continue_research" in result

    def test_no_report_note(self):
        result = _router_instruction(MockCtx(state={}))

        assert "No research has been done yet" in result

    def test_prompt_focus_clarification_wording(self):
        result = _router_instruction(MockCtx(state={}))

        assert "`[Context: ...]` prefix with selected focus, Place ID, or address details" in result
        assert "broad restaurant-industry question that is answerable without local geography" in result
        assert "missing restaurant, street, neighborhood, city, area, or market" in result
        assert "Branch-proximity requests need branch-level scope" in result
        assert "chain or brand name plus only a broad city" in result
        assert "exact address, street name, or street-level location is enough branch-level scope" in result
        assert "Do not pick or infer one branch" in result
        assert "Apply the same scope test to the original question and clarified focus" in result
        assert "proposed restaurant or venue focus" in result
        assert "without branch-level scope, ask for clarification even when the focus includes a city" in result
        assert "choosing a restaurant first" not in result


class TestContextEnricherInstruction:
    def test_place_id_can_be_site_area_or_target_restaurant(self):
        result = (INSTRUCTIONS_DIR / "context_enricher.md").read_text()

        assert "target restaurant, proposed site, or area focus" in result
        assert "Do not call it the target restaurant" in result
        assert "Still build area or site context" in result
        assert "Keep nearby competitors separate from broader comparables" in result
        assert "multiple same-brand or same-chain candidates" in result
        assert "do not choose a target by prominence, rating, review count, or result order" in result
        assert "Use Google Places tools only" in result
