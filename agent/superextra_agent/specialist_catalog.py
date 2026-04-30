"""Single source of truth for the specialist roster.

The same name/key/label/description/thinking-level facts used to live in
five separate data structures across three files (agent.py, specialists.py,
firestore_events.py). Adding or renaming a specialist required touching
every one, and drift was tracked as a known risk in
`instructions/AUTHORING.md`. This module collapses them into one flat
table; every consumer derives its view.

The catalog is intentionally **data-only** — no helper classes, no
registries, no indirection. A future add-specialist step is: append one
line here and add its instruction/body template.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Specialist:
    """One specialist agent's durable facts.

    Fields:
        name: Agent name — also the key used by the orchestrator in
            AgentTool dispatch. Equal to `author` on emitted events.
        output_key: State key the specialist writes its final report into.
        label: Human-readable title used in UI activity rows and prompts.
        description: One-sentence summary used by the orchestrator prompt
            and as the `LlmAgent.description`.
        role_title: Used by `specialist_base.md`'s `{role_title}`
            placeholder ("Market Landscape research agent", etc.).
        thinking: Which thinking-config bucket this specialist falls into
            — `"high"` for quantitative-inference / strategic work,
            `"medium"` for pattern-matching / aggregation.
        instruction_name: Optional override for which `.md` template to
            load. Defaults to `name`. `dynamic_researcher_1` reuses the
            generic `dynamic_researcher` template.
    """
    name: str
    output_key: str
    label: str
    description: str
    role_title: str
    thinking: str  # "high" | "medium"
    instruction_name: str | None = None


# ResearchLead-callable specialists. Order is the canonical top-to-bottom
# structure used by prompts and UI labels.
SPECIALISTS: tuple[Specialist, ...] = (
    Specialist(
        name="market_landscape",
        output_key="market_result",
        label="Market Landscape",
        description=(
            "Restaurant openings, closings, competitor mapping, cuisine trends, "
            "saturation, and white space — sourced from press, forums "
            "(Trojmiasto.pl, Reddit), local food blogs, and government "
            "registries. Best for 'who's new, who's gone, what's missing' "
            "questions and trade-area scans."
        ),
        role_title="Market Landscape research agent",
        thinking="high",
    ),
    Specialist(
        name="menu_pricing",
        output_key="pricing_result",
        label="Menu & Pricing",
        description=(
            "Competitive menu and price analysis for the target restaurant and "
            "competitive set. Pulls live data from delivery platforms "
            "(Pyszne.pl, Wolt, Glovo, Uber Eats, Bolt Food), making this also "
            "the strongest live signal of who is currently operating and on "
            "which platforms. Compares delivery markup vs dine-in pricing, "
            "surfaces promotions, lunch deals, trending dishes, "
            "dietary-trend adoption, and currently-operating signals from "
            "delivery-platform availability. Does NOT cover review sentiment "
            "about price, marketing positioning, or revenue."
        ),
        role_title="Menu & Pricing research agent",
        thinking="high",
    ),
    Specialist(
        name="revenue_sales",
        output_key="revenue_result",
        label="Revenue & Sales",
        description=(
            "Revenue estimates, check-size ranges, seasonality, channel splits "
            "between dine-in/takeaway/delivery, and platform market share. "
            "Pulls from industry reports, Eurostat, NielsenIQ-style "
            "aggregators, and triangulates with platform listing density."
        ),
        role_title="Revenue & Sales research agent",
        thinking="high",
    ),
    Specialist(
        name="guest_intelligence",
        output_key="guest_result",
        label="Guest Intelligence",
        description=(
            "Cross-platform qualitative review sentiment via web search — "
            "TheFork, delivery-platform reviews (Wolt/Pyszne/Glovo), food "
            "blogs, Reddit, local forums, press coverage. Distinct from "
            "review_analyst's structured-API analysis: this is the 'what are "
            "people actually saying' lens. Does NOT touch Google Reviews or "
            "TripAdvisor structured API (review_analyst's domain)."
        ),
        role_title="Guest Intelligence research agent",
        thinking="medium",
    ),
    Specialist(
        name="location_traffic",
        output_key="location_result",
        label="Location & Traffic",
        description=(
            "Foot traffic, demographic catchment, purchasing power index, rent "
            "as a market signal (vs operations which treats rent as a cost "
            "ratio), and trade-area shape. Pulls from Eurostat, OpenStreetMap "
            "density, mobility data, real-estate listings."
        ),
        role_title="Location & Traffic research agent",
        thinking="medium",
    ),
    Specialist(
        name="operations",
        output_key="ops_result",
        label="Operations",
        description=(
            "Cost-side benchmarks for running a restaurant: salary ranges by "
            "role from job boards, hiring difficulty signals, supplier and "
            "ingredient pricing trends, and rent as a cost ratio (vs "
            "location_traffic which treats rent as a market signal). Use for "
            "any wage/labor question, hiring feasibility, or unit-economics "
            "framing."
        ),
        role_title="Operations research agent",
        thinking="high",
    ),
    Specialist(
        name="marketing_digital",
        output_key="marketing_result",
        label="Marketing & Digital",
        description=(
            "Live Instagram, TikTok, Facebook activity (follower count, "
            "posting cadence, engagement, Reels) and Meta Ad Library data "
            "(active ads, creative, launch dates) for the target restaurant "
            "and competitive set. Canonical signal for new venues launching "
            "(announced on social before press), brand momentum, and "
            "competitor advertising spend. Also covers price-positioning "
            "signals such as promo frequency, value-proposition messaging, "
            "discount framing, delivery-platform positioning (rankings, "
            "photo quality, menu completeness), and Google SERP/Business "
            "Profile presence. Does NOT analyze menu line-item prices, "
            "review sentiment, or revenue."
        ),
        role_title="Marketing & Digital research agent",
        thinking="medium",
    ),
    Specialist(
        name="review_analyst",
        output_key="review_result",
        label="Review Analysis",
        description=(
            "Quantitative review analysis from structured API sources: Google "
            "Reviews + TripAdvisor (tourist/local breakdown, rating trends, "
            "owner-engagement, ranking position). Apify-backed, includes "
            "demographics. Best for hard numbers on review patterns, price/value "
            "complaints, closure-risk signals such as review-velocity flatlines, "
            "and defensive owner-response patterns; pair with guest_intelligence "
            "for cross-platform qualitative."
        ),
        role_title="Review Analyst",
        thinking="high",
    ),
    Specialist(
        name="dynamic_researcher_1",
        output_key="dynamic_result_1",
        label="Dynamic Research",
        description=(
            "Flexible research agent for angles outside the 8 specialist "
            "domains. Use for niche regulatory questions, one-off competitor "
            "news, sector-specific events, job-board-specific labor checks, "
            "salary benchmarks beyond operations' standard sources, or any "
            "topic where no other specialist's data sources apply. For "
            "wage/labor questions, pair with operations when the answer needs "
            "current job postings or external benchmark validation. Brief "
            "should name the exact question and where to search."
        ),
        role_title="flexible research agent",
        thinking="high",
        instruction_name="dynamic_researcher",
    ),
)


# ── Derived views (never edit by hand) ──────────────────────────────────────


#: Specialist author -> state output_key. Used by `firestore_events`.
AUTHOR_TO_OUTPUT_KEY: dict[str, str] = {s.name: s.output_key for s in SPECIALISTS}

#: state output_key → UI label.
OUTPUT_KEY_TO_LABEL: dict[str, str] = {s.output_key: s.label for s in SPECIALISTS}

#: Specialist name → output_key.
SPECIALIST_OUTPUT_KEYS: dict[str, str] = {s.name: s.output_key for s in SPECIALISTS}

#: Specialist instruction name → role_title for `specialist_base.md`.
ROLE_TITLES: dict[str, str] = {
    (s.instruction_name or s.name): s.role_title for s in SPECIALISTS
}

#: Orchestrator-prompt lookup: output_key → label for "prior results" detection.
#: Includes every ResearchLead-callable specialist.
SPECIALIST_RESULT_KEYS: dict[str, str] = {s.output_key: s.label for s in SPECIALISTS}
