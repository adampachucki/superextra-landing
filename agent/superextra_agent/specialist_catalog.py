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
            "Competitive structure, openings, closures, saturation, white "
            "space, and competitor mapping. Best for market dynamics and "
            "trade-area scans."
        ),
        role_title="Market Landscape research agent",
        thinking="high",
    ),
    Specialist(
        name="menu_pricing",
        output_key="pricing_result",
        label="Menu & Pricing",
        description=(
            "Menu items, category structure, price ladders, dine-in versus "
            "delivery pricing, promotions, and competitor price positioning. "
            "Does not cover review sentiment, digital positioning, or revenue."
        ),
        role_title="Menu & Pricing research agent",
        thinking="high",
    ),
    Specialist(
        name="revenue_sales",
        output_key="revenue_result",
        label="Revenue & Sales",
        description=(
            "Revenue estimates, average check, seasonality, covers, channel "
            "mix, and market-level demand economics. Uses ranges and stated "
            "assumptions."
        ),
        role_title="Revenue & Sales research agent",
        thinking="high",
    ),
    Specialist(
        name="guest_intelligence",
        output_key="guest_result",
        label="Guest Intelligence",
        description=(
            "Qualitative customer voice from local press, food writers, "
            "forums, Reddit, social posts, delivery, booking, and niche "
            "platforms. Does not analyze structured Google Reviews or "
            "TripAdvisor API data."
        ),
        role_title="Guest Intelligence research agent",
        thinking="medium",
    ),
    Specialist(
        name="location_traffic",
        output_key="location_result",
        label="Location & Traffic",
        description=(
            "Trade-area quality, public busyness signals, demographics, "
            "anchors, access, rent as a market signal, and local demand "
            "density."
        ),
        role_title="Location & Traffic research agent",
        thinking="medium",
    ),
    Specialist(
        name="operations",
        output_key="ops_result",
        label="Operations",
        description=(
            "Labor, wage, hiring, supplier, rent-cost, and operating cost "
            "benchmarks. Use for wage questions, hiring feasibility, and "
            "unit-economics framing."
        ),
        role_title="Operations research agent",
        thinking="high",
    ),
    Specialist(
        name="marketing_brand",
        output_key="marketing_result",
        label="Marketing & Brand",
        description=(
            "Marketing strategy, brand positioning, campaigns, PR, public "
            "ads, social, web, search, and platform presence. Does not "
            "analyze line-item menu prices, review sentiment, or revenue."
        ),
        role_title="Marketing & Brand research agent",
        thinking="medium",
    ),
    Specialist(
        name="review_analyst",
        output_key="review_result",
        label="Review Analysis",
        description=(
            "Quantitative review analysis from structured Google Reviews and "
            "TripAdvisor tools: samples, rating trends, owner response, "
            "visitor mix, language, and review velocity."
        ),
        role_title="Review Analyst",
        thinking="high",
    ),
    Specialist(
        name="dynamic_researcher_1",
        output_key="dynamic_result_1",
        label="Dynamic Research",
        description=(
            "Flexible research for angles outside the standard domains, such "
            "as broad culinary trends, regulation, food safety, one-off news, "
            "infrastructure, events, or unusual benchmarks. Brief must name "
            "the exact gap."
        ),
        role_title="flexible research agent",
        thinking="high",
        instruction_name="dynamic_researcher",
    ),
)


# ── Derived views (never edit by hand) ──────────────────────────────────────


#: Specialist author -> state output_key. Used by `firestore_events`.
AUTHOR_TO_OUTPUT_KEY: dict[str, str] = {s.name: s.output_key for s in SPECIALISTS}

#: Specialist instruction name → role_title for `specialist_base.md`.
ROLE_TITLES: dict[str, str] = {
    (s.instruction_name or s.name): s.role_title for s in SPECIALISTS
}

#: Orchestrator-prompt lookup: output_key → label for "prior results" detection.
#: Includes every ResearchLead-callable specialist.
SPECIALIST_RESULT_KEYS: dict[str, str] = {s.output_key: s.label for s in SPECIALISTS}
