"""Builds Variant A (current setup replica) and Variant B (AgentTool) for
the spike.

Both variants share the same:
- model + thinking config (from `superextra_agent.specialists`)
- specialist instructions (`menu_pricing.md`, `marketing_digital.md`)
- google_search + fetch_web_content tool pair on each specialist
- hand-crafted places_context (no enricher in either)

They differ in exactly one dimension: how the orchestrator dispatches
work.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `superextra_agent.*` importable when this file is invoked as a script
AGENT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AGENT_DIR))

# Cloud env must be set before any import that touches Vertex
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "superextra-site")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(AGENT_DIR / ".env")

from google.adk.agents import LlmAgent
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from superextra_agent.specialists import (  # type: ignore
    MODEL_GEMINI,
    SPECIALIST_GEMINI,
    THINKING_CONFIG,
    MEDIUM_THINKING_CONFIG,
    set_specialist_briefs,
)
from superextra_agent.web_tools import fetch_web_content  # type: ignore

SPIKE_DIR = Path(__file__).resolve().parent
ORCH_A_TEMPLATE = (SPIKE_DIR / "orchestrator_a.md").read_text()
ORCH_B_TEMPLATE = (SPIKE_DIR / "orchestrator_b.md").read_text()
SPECIALIST_BRIEF_TEMPLATE = (SPIKE_DIR / "specialist_brief.md").read_text()
SPECIALIST_INSTRUCTIONS_DIR = AGENT_DIR / "superextra_agent" / "instructions"


# ── Specialist instruction loaders (no specialist_base wrapper, no brief
# injection from state — we want the variant-specific brief plumbing to be
# explicit) ─────────────────────────────────────────────────────────────


def _load_specialist_body(name: str) -> str:
    return (SPECIALIST_INSTRUCTIONS_DIR / f"{name}.md").read_text()


def _instruction_for_a(name: str):
    """Variant A: brief lives in state[`specialist_briefs`][name]."""
    body = _load_specialist_body(name)

    def provider(ctx):
        places_context = ctx.state.get(
            "places_context", "No Google Places data available."
        )
        prefix = SPECIALIST_BRIEF_TEMPLATE.format(places_context=places_context)
        instruction = prefix + "\n\n" + body
        briefs = ctx.state.get("specialist_briefs", {})
        brief = briefs.get(name, "")
        if brief:
            instruction += f"\n\n## Your research brief\n\n{brief}"
        return instruction

    return provider


def _instruction_for_b(name: str):
    """Variant B: brief comes via the user message (the AgentTool's
    `request` arg). The instruction itself only carries places_context."""
    body = _load_specialist_body(name)

    def provider(ctx):
        places_context = ctx.state.get(
            "places_context", "No Google Places data available."
        )
        prefix = SPECIALIST_BRIEF_TEMPLATE.format(places_context=places_context)
        # The user message (the brief) flows in via include_contents='default'.
        return prefix + "\n\n" + body

    return provider


# ── Skip-callback used by Variant A (matches production behaviour) ─────


def _make_skip_callback(name: str):
    def callback(*, callback_context):
        briefs = callback_context.state.get("specialist_briefs", {})
        if name not in briefs:
            return types.Content(
                role="model", parts=[types.Part(text="NOT_RELEVANT")]
            )
        return None

    return callback


# ── Specialist factories ───────────────────────────────────────────────

# Descriptions are the *new* rich descriptions from the catalog redesign,
# pasted verbatim so both variants see identical capability metadata.
RICH_DESCRIPTIONS = {
    "menu_pricing": (
        "Competitive menu and price analysis for the target restaurant and its competitive "
        "set. Pulls live data from delivery platforms (Pyszne.pl, Wolt, Glovo, Uber Eats, "
        "Bolt Food), which makes this also the strongest live signal of who is currently "
        "operating and on which platforms. Compares delivery markup vs dine-in pricing, "
        "surfaces promotions, lunch deals, trending dishes, and dietary-trend adoption. "
        "Does NOT cover review sentiment about price, marketing positioning, or revenue."
    ),
    "marketing_digital": (
        "Live Instagram, TikTok, Facebook activity (follower count, posting cadence, "
        "engagement, Reels) and Meta Ad Library data (active ads, creative, launch dates) "
        "for the target restaurant and competitive set. Canonical signal for new venues "
        "launching (announced on social before press), brand momentum, and competitor "
        "advertising spend. Also covers delivery-platform positioning (rankings, photo "
        "quality, menu completeness as differentiators) and Google SERP/Business Profile "
        "presence. Does NOT analyze menus or prices, review sentiment, or revenue."
    ),
}


def _make_specialist_a(name: str, output_key: str) -> LlmAgent:
    return LlmAgent(
        name=name,
        model=SPECIALIST_GEMINI,
        description=RICH_DESCRIPTIONS[name],
        instruction=_instruction_for_a(name),
        tools=[google_search, fetch_web_content],
        output_key=output_key,
        include_contents="none",
        generate_content_config=THINKING_CONFIG,
        before_agent_callback=_make_skip_callback(name),
    )


def _make_specialist_b(name: str, output_key: str) -> LlmAgent:
    return LlmAgent(
        name=name,
        model=SPECIALIST_GEMINI,
        description=RICH_DESCRIPTIONS[name],
        instruction=_instruction_for_b(name),
        tools=[google_search, fetch_web_content],
        output_key=output_key,
        # IMPORTANT: 'default' so the brief (passed as user message via the
        # AgentTool's `request` arg) is visible to the model.
        include_contents="default",
        generate_content_config=THINKING_CONFIG,
    )


# ── Variant A: orchestrator + ParallelAgent ────────────────────────────


def _orchestrator_a_instruction(ctx):
    places_context = ctx.state.get(
        "places_context", "No Google Places data available."
    )
    return ORCH_A_TEMPLATE.format(places_context=places_context)


def build_variant_a() -> SequentialAgent:
    menu_pricing = _make_specialist_a("menu_pricing", "pricing_result")
    marketing_digital = _make_specialist_a(
        "marketing_digital", "marketing_result"
    )

    orchestrator = LlmAgent(
        name="research_orchestrator_a",
        model=MODEL_GEMINI,
        instruction=_orchestrator_a_instruction,
        description="Plans research and assigns specialist briefs (variant A).",
        # No google_search in this minimal spike — orchestrator dispatches
        # directly from places_context.
        tools=[set_specialist_briefs],
        output_key="research_plan",
        generate_content_config=MEDIUM_THINKING_CONFIG,
    )

    pool = ParallelAgent(
        name="specialist_pool_a",
        sub_agents=[menu_pricing, marketing_digital],
        description="Runs assigned specialists in parallel (variant A).",
    )

    return SequentialAgent(
        name="variant_a_pipeline",
        sub_agents=[orchestrator, pool],
        description="Variant A — current setup replica (set_specialist_briefs + ParallelAgent).",
    )


# ── Variant B: orchestrator with AgentTool-wrapped specialists ────────


def _orchestrator_b_instruction(ctx):
    places_context = ctx.state.get(
        "places_context", "No Google Places data available."
    )
    return ORCH_B_TEMPLATE.format(places_context=places_context)


def build_variant_b() -> LlmAgent:
    menu_pricing = _make_specialist_b("menu_pricing", "pricing_result")
    marketing_digital = _make_specialist_b(
        "marketing_digital", "marketing_result"
    )

    return LlmAgent(
        name="research_orchestrator_b",
        model=MODEL_GEMINI,
        instruction=_orchestrator_b_instruction,
        description="Plans research and dispatches specialists as tools (variant B).",
        tools=[
            AgentTool(agent=menu_pricing),
            AgentTool(agent=marketing_digital),
        ],
        output_key="research_plan",
        generate_content_config=MEDIUM_THINKING_CONFIG,
    )
