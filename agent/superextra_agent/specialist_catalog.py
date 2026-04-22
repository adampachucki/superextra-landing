"""Single source of truth for the specialist roster.

The same name/key/label/description/thinking-level facts used to live in
five separate data structures across three files (agent.py, specialists.py,
firestore_events.py). Adding or renaming a specialist required touching
every one, and drift was tracked as a known risk in
`instructions/AUTHORING.md`. This module collapses them into one flat
table; every consumer derives its view.

The catalog is intentionally **data-only** — no helper classes, no
registries, no indirection. A future add-specialist step is: append one
line here, update the orchestrator instruction's "Available specialists"
list, and you're done.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Specialist:
    """One specialist agent's durable facts.

    Fields:
        name: Agent name — also the key used by the orchestrator in
            `specialist_briefs` to dispatch work. Equal to `author` on
            emitted events.
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
        supports_brief: Whether the orchestrator can dispatch a brief to
            this specialist. The gap researcher is excluded — it runs as
            a distinct step, not part of the briefed pool.
    """
    name: str
    output_key: str
    label: str
    description: str
    role_title: str
    thinking: str  # "high" | "medium"
    instruction_name: str | None = None
    supports_brief: bool = True


# Orchestrator-assignable specialists + the gap researcher. Order matters
# for the fallback report stitch (see `_build_fallback_report` in agent.py)
# — it's the canonical top-to-bottom structure of a report.
SPECIALISTS: tuple[Specialist, ...] = (
    Specialist(
        name="market_landscape",
        output_key="market_result",
        label="Market Landscape",
        description="Analyzes restaurant market dynamics: openings, closings, competitor activity, cuisine trends, saturation, white space.",
        role_title="Market Landscape research agent",
        thinking="high",
    ),
    Specialist(
        name="menu_pricing",
        output_key="pricing_result",
        label="Menu & Pricing",
        description="Analyzes menus, pricing, delivery markups, promotions, trending dishes.",
        role_title="Menu & Pricing research agent",
        thinking="high",
    ),
    Specialist(
        name="revenue_sales",
        output_key="revenue_result",
        label="Revenue & Sales",
        description="Estimates revenue, check size, seasonality, channel splits, platform share.",
        role_title="Revenue & Sales research agent",
        thinking="high",
    ),
    Specialist(
        name="guest_intelligence",
        output_key="guest_result",
        label="Guest Intelligence",
        description="Analyzes review sentiment, complaint/praise patterns, rating trends.",
        role_title="Guest Intelligence research agent",
        thinking="medium",
    ),
    Specialist(
        name="location_traffic",
        output_key="location_result",
        label="Location & Traffic",
        description="Analyzes foot traffic, demographics, purchasing power, rent, trade areas.",
        role_title="Location & Traffic research agent",
        thinking="medium",
    ),
    Specialist(
        name="operations",
        output_key="ops_result",
        label="Operations",
        description="Analyzes labor market, salary benchmarks, rent, supplier pricing.",
        role_title="Operations research agent",
        thinking="high",
    ),
    Specialist(
        name="marketing_digital",
        output_key="marketing_result",
        label="Marketing & Digital",
        description="Analyzes social media, ads, delivery platform presence, web presence.",
        role_title="Marketing & Digital research agent",
        thinking="medium",
    ),
    Specialist(
        name="review_analyst",
        output_key="review_result",
        label="Review Analysis",
        description="Quantitative review analysis from structured API sources: tourist/local breakdown, rating trends, owner engagement, rankings.",
        role_title="Review Analyst",
        thinking="high",
    ),
    Specialist(
        name="dynamic_researcher_1",
        output_key="dynamic_result_1",
        label="Dynamic Research",
        description="Flexible research agent for investigating specific angles that don't fit the 7 specialist domains.",
        role_title="flexible research agent",
        thinking="high",
        instruction_name="dynamic_researcher",
    ),
    Specialist(
        name="gap_researcher",
        output_key="gap_research_result",
        label="Gap Research",
        description="Analyzes Phase 1 specialist outputs for gaps, contradictions, and underexplored angles.",
        role_title="Gap Researcher",
        thinking="medium",
        supports_brief=False,
    ),
)


# ── Derived views (never edit by hand) ──────────────────────────────────────


#: Specialists the orchestrator can dispatch a brief to (everything minus gap).
BRIEFABLE_SPECIALISTS: tuple[Specialist, ...] = tuple(
    s for s in SPECIALISTS if s.supports_brief
)

#: author → state output_key. Used by `firestore_events.AUTHOR_TO_OUTPUT_KEY`
#: (which also has a `follow_up → final_report` row the mapper adds).
AUTHOR_TO_OUTPUT_KEY: dict[str, str] = {s.name: s.output_key for s in SPECIALISTS}

#: state output_key → UI label.
OUTPUT_KEY_TO_LABEL: dict[str, str] = {s.output_key: s.label for s in SPECIALISTS}

#: Brief-assignable specialist name → output_key. Used by the gap-gate to
#: check which brief-assigned specialists succeeded or failed.
SPECIALIST_OUTPUT_KEYS: dict[str, str] = {
    s.name: s.output_key for s in BRIEFABLE_SPECIALISTS
}

#: Brief-assignable specialist name → role_title for `specialist_base.md`.
ROLE_TITLES: dict[str, str] = {
    (s.instruction_name or s.name): s.role_title for s in BRIEFABLE_SPECIALISTS
}

#: Orchestrator-prompt lookup: output_key → label for "prior results" detection.
#: Excludes gap research (it's a phase 2 output, not a phase 1 signal).
SPECIALIST_RESULT_KEYS: dict[str, str] = {
    s.output_key: s.label for s in BRIEFABLE_SPECIALISTS
}

#: Top-to-bottom structure of the fallback report stitched from specialist
#: state when the synth callback needs to substitute a report. Order is the
#: catalog order; includes the gap research section.
FALLBACK_SECTIONS: list[tuple[str, str]] = [(s.output_key, s.label) for s in SPECIALISTS]

#: Valid brief keys the orchestrator's `set_specialist_briefs` tool accepts.
VALID_BRIEF_KEYS: frozenset[str] = frozenset(s.name for s in BRIEFABLE_SPECIALISTS)
