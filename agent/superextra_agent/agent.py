import json
import os
import re
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.apps import App
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from .chat_logger import ChatLoggerPlugin
from .firestore_progress import FirestoreProgressPlugin
from .places_tools import (
    find_nearby_restaurants,
    get_batch_restaurant_details,
    get_restaurant_details,
    search_restaurants,
)
from .place_state import format_known_places_context
from .specialist_catalog import SPECIALIST_RESULT_KEYS
from .specialists import (
    ALL_SPECIALISTS,
    CONTINUATION_SPECIALISTS,
    MEDIUM_THINKING_CONFIG,
    MODEL_GEMINI,
    ORCHESTRATOR_THINKING_CONFIG,
    SPECIALIST_GEMINI,
    _inject_geo_bias,
    _make_gemini,
    _on_model_error,
    _on_tool_error,
)
from .web_tools import (
    ADJUDICATOR_READ_RESULT_STATE_KEY,
    collect_adjudicator_packet_claims,
    fetch_web_content,
    fetch_web_content_batch,
    read_adjudicator_sources,
    read_web_pages,
)

# Fast model for routing — no thinking needed.
# Routed via the global Vertex AI endpoint because 2.5 Flash isn't served
# from us-central1 (same constraint as the 3.1 models _make_gemini already
# handles for specialists).
_FAST_MODEL = _make_gemini("gemini-2.5-flash", force_global=True)

_dir_override = os.environ.get("SUPEREXTRA_INSTRUCTIONS_DIR")
INSTRUCTIONS_DIR = Path(_dir_override) if _dir_override else Path(__file__).parent / "instructions"

# --- Instruction providers (inject session state into templates) ---

_RESEARCH_LEAD_TEMPLATE = (INSTRUCTIONS_DIR / "research_lead.md").read_text()
_MARKET_SOURCE_PROFILES = (INSTRUCTIONS_DIR / "market_source_profiles.md").read_text()
_EVIDENCE_ADJUDICATOR_TEMPLATE = (
    INSTRUCTIONS_DIR / "evidence_adjudicator.md"
).read_text()
_REPORT_WRITER_TEMPLATE = (INSTRUCTIONS_DIR / "report_writer.md").read_text()


def _research_lead_instruction(ctx):
    """Inject places_context and existing results into the research lead instructions."""
    places_context = ctx.state.get("places_context", "No Google Places data available.")
    existing = [
        label
        for key, label in SPECIALIST_RESULT_KEYS.items()
        if ctx.state.get(key) and ctx.state.get(key) != "Agent did not produce output."
    ]
    follow_up_note = ""
    if existing:
        follow_up_note = (
            "\n\n## Existing research from prior turn\n\n"
            f"Specialists with existing results: {', '.join(existing)}.\n\n"
            "Reuse prior results where they still fit. Call specialists that "
            "update, deepen, or add a complementary angle for the latest question."
        )
    return _RESEARCH_LEAD_TEMPLATE.format(
        places_context=places_context,
        market_source_profiles=_MARKET_SOURCE_PROFILES,
    ) + follow_up_note


# --- Shared agent config ---

_ENRICHER_INSTRUCTION = (INSTRUCTIONS_DIR / "context_enricher.md").read_text()
_ENRICHER_TOOLS = [
    get_restaurant_details,
    get_batch_restaurant_details,
    find_nearby_restaurants,
    search_restaurants,
]


def _skip_enricher_if_cached(*, callback_context):
    """Skip context enricher if places_context already populated from a prior turn."""
    existing = callback_context.state.get("places_context")
    if existing:
        return types.Content(role="model", parts=[types.Part(text=existing)])
    return None


def _make_enricher(name="context_enricher"):
    """Create a context enricher instance."""
    return LlmAgent(
        name=name,
        model=SPECIALIST_GEMINI,
        instruction=_ENRICHER_INSTRUCTION,
        description=(
            "Fetches structured Google Places context for a target restaurant "
            "and competitive set when available."
        ),
        tools=_ENRICHER_TOOLS,
        output_key="places_context",
        generate_content_config=MEDIUM_THINKING_CONFIG,
        before_agent_callback=_skip_enricher_if_cached,
    )


# --- Continuation agent (answers from existing research, with focused deepening) ---

_CONTINUE_RESEARCH_TEMPLATE = (INSTRUCTIONS_DIR / "continue_research.md").read_text()
_CONTINUATION_NOTES_KEY = "continuation_notes"
_MAX_CONTINUATION_NOTES_CHARS = 6000
_MAX_CONTINUATION_NOTE_ANSWER_CHARS = 1600
_MAX_CONTINUATION_NOTE_QUESTION_CHARS = 500
_VALIDATION_PACKET_HEADING_RE = re.compile(
    r"(?im)^#{1,6}\s+(?:\*\*)?Validation Packet\s*:?(?:\*\*)?\s*:?\s*$"
)
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_EVIDENCE_MEMO_REQUIRED_KEYS = frozenset(
    {
        "confirmed_claims",
        "contradicted_claims",
        "unsupported_claims",
        "unresolved_claims",
        "read_summary",
    }
)


def _strip_validation_packet(report: str) -> str:
    """Remove internal specialist validation metadata from writer-facing text."""
    match = _VALIDATION_PACKET_HEADING_RE.search(report)
    if not match:
        return report
    return report[: match.start()].rstrip()


def _format_specialist_reports(
    state,
    default="No specialist notes available.",
    include_validation_packets=False,
):
    """Format specialist outputs stored in session state."""
    sections = []
    for key, label in SPECIALIST_RESULT_KEYS.items():
        value = state.get(key)
        if value and value != "Agent did not produce output.":
            value = str(value)
            if not include_validation_packets:
                value = _strip_validation_packet(value)
            if value.strip():
                sections.append(f"### {label}\n\n{value}")
    if not sections:
        return default
    return "\n\n".join(sections)


def _content_text(content) -> str:
    parts = getattr(content, "parts", None) or []
    return "\n".join(
        part.text for part in parts if isinstance(getattr(part, "text", None), str)
    ).strip()


def _compact_for_notes(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _append_continuation_note(existing: str, entry: str) -> str:
    chunks = [chunk.strip() for chunk in existing.split("\n\n") if chunk.strip()]
    chunks.append(entry.strip())
    while chunks and len("\n\n".join(chunks)) > _MAX_CONTINUATION_NOTES_CHARS:
        chunks.pop(0)
    return "\n\n".join(chunks)


def _record_continuation_notes(*, callback_context):
    """Persist compact same-session continuation memory through ADK state.

    This intentionally uses the documented delta-aware `callback_context.state`
    path rather than Firestore-side memory. The original report and specialist
    state remain immutable; continuation turns accumulate in a separate state
    key that future continuation prompts can read.
    """
    reply = callback_context.state.get("continue_research_reply")
    if not isinstance(reply, str) or not reply.strip():
        return None

    user_text = _content_text(getattr(callback_context, "user_content", None))
    existing = callback_context.state.get(_CONTINUATION_NOTES_KEY, "")
    if not isinstance(existing, str):
        existing = ""

    turn_idx = callback_context.state.get("turnIdx")
    label = f"Turn {turn_idx}" if isinstance(turn_idx, int) else "Continuation turn"
    entry = (
        f"### {label}\n"
        f"User asked: {_compact_for_notes(user_text, _MAX_CONTINUATION_NOTE_QUESTION_CHARS)}\n"
        f"Answer/follow-up findings: "
        f"{_compact_for_notes(reply, _MAX_CONTINUATION_NOTE_ANSWER_CHARS)}"
    )
    updated = _append_continuation_note(existing, entry)
    if updated != existing:
        callback_context.state[_CONTINUATION_NOTES_KEY] = updated
    return None


def _claim_identity(value) -> str | None:
    if not isinstance(value, dict):
        return None
    claim_id = str(value.get("id") or "").strip()
    claim_text = str(value.get("claim") or "").strip()
    if claim_id and claim_text:
        return f"id:{claim_id}\0claim:{claim_text}"
    if claim_id:
        return f"id:{claim_id}"
    return f"claim:{claim_text}" if claim_text else None


def _adjudicated_claim_identities(memo: dict) -> set[str]:
    identities: set[str] = set()
    for key in (
        "confirmed_claims",
        "contradicted_claims",
        "unsupported_claims",
        "unresolved_claims",
    ):
        for claim in memo.get(key) or []:
            identity = _claim_identity(claim)
            if identity:
                identities.add(identity)
    return identities


def _has_structured_evidence_memo(value, state=None) -> bool:
    parsed = _parse_evidence_memo(value)
    if not isinstance(parsed, dict) or not _EVIDENCE_MEMO_REQUIRED_KEYS.issubset(parsed):
        return False
    if state is None:
        return True
    required_claims = {
        identity
        for claim in collect_adjudicator_packet_claims(state)
        if (identity := _claim_identity(claim))
    }
    if not required_claims:
        return True
    return required_claims.issubset(_adjudicated_claim_identities(parsed))


def _parse_evidence_memo(value):
    if not isinstance(value, str) or not value.strip():
        return None
    match = _FENCED_JSON_RE.search(value)
    candidate = match.group(1) if match else value.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _is_failed_closed_evidence_memo(value) -> bool:
    parsed = _parse_evidence_memo(value)
    return isinstance(parsed, dict) and parsed.get("adjudication_status") == "failed_closed"


def _format_evidence_memo_for_writer(value):
    parsed = _parse_evidence_memo(value)
    if not isinstance(parsed, dict) or parsed.get("adjudication_status") != "failed_closed":
        return value

    redacted = {
        "adjudication_status": "failed_closed",
        "confirmed_claims": [],
        "contradicted_claims": [],
        "unsupported_claims": [],
        "unresolved_claims": [],
        "verified_sources": [],
        "unread_sources": parsed.get("unread_sources", []),
        "read_summary": parsed.get("read_summary", {}),
        "withheld_unresolved_claim_count": len(parsed.get("unresolved_claims") or []),
        "notes": (
            "Adjudication failed closed. Unresolved specialist claim text is "
            "withheld from the writer and must not be used as report evidence."
        ),
    }
    return json.dumps(redacted, ensure_ascii=False, indent=2)


def _record_evidence_adjudicator_fallback(*, callback_context):
    """Fail closed if the adjudicator reads sources but produces no memo."""
    existing = callback_context.state.get("evidence_memo")
    if _has_structured_evidence_memo(existing, callback_context.state):
        return None

    read_result = callback_context.state.get(ADJUDICATOR_READ_RESULT_STATE_KEY)
    if not isinstance(read_result, dict):
        read_result = {}

    unresolved_claims = []
    for claim in collect_adjudicator_packet_claims(callback_context.state):
        reason_parts = [
            "The evidence adjudicator did not produce a claim-status memo, "
            "so this specialist claim must be treated as unresolved."
        ]
        if claim.get("source_urls"):
            reason_parts.append(
                "Source reads may have been attempted, but no adjudicated "
                "support was recorded for this claim."
            )
        if claim.get("provider_refs"):
            reason_parts.append(
                "Provider references were present, but no adjudicated provider "
                "confirmation was recorded for this claim."
            )
        unresolved_claims.append(
            {
                "id": claim.get("id") or "",
                "claim": claim.get("claim") or "",
                "reason": " ".join(reason_parts),
            }
        )

    unread_sources = []
    for item in read_result.get("failed_sources") or []:
        if isinstance(item, dict) and item.get("url"):
            unread_sources.append(
                {
                    "url": item["url"],
                    "reason": str(item.get("reason") or "read failed"),
                }
            )
    for key, reason in (
        ("skipped_urls", "duplicate or already read in this adjudication run"),
        ("rejected_urls", "not present in specialist validation packets"),
        ("invalid_urls", "invalid URL"),
    ):
        for url in read_result.get(key) or []:
            if isinstance(url, str) and url:
                unread_sources.append({"url": url, "reason": reason})

    verified_sources = []
    for source in read_result.get("sources") or []:
        if not isinstance(source, dict) or not source.get("url"):
            continue
        verified_sources.append(
            {
                "url": source.get("url"),
                "title": source.get("title") or "",
                "domain": source.get("domain") or "",
                "supports_claim_ids": [],
                "limits": (
                    "Fetched by the bounded reader, but no adjudicated "
                    "claim support was recorded."
                ),
            }
        )

    fallback_memo = {
        "adjudication_status": "failed_closed",
        "confirmed_claims": [],
        "contradicted_claims": [],
        "unsupported_claims": [],
        "unresolved_claims": unresolved_claims,
        "verified_sources": verified_sources,
        "unread_sources": unread_sources,
        "read_summary": {
            "requested_url_count": read_result.get("requested_count", 0),
            "attempted_url_count": read_result.get("attempted_count", 0),
            "successful_url_count": read_result.get("successful_count", 0),
            "failed_url_count": read_result.get("failed_count", 0),
            "notes": (
                "The adjudicator failed closed because no claim-status memo "
                "was persisted."
            ),
        },
    }
    callback_context.state["evidence_memo"] = json.dumps(
        fallback_memo, ensure_ascii=False, indent=2
    )
    return None


def _continue_research_instruction(ctx):
    """Inject prior report, specialist notes, and context into continuation instructions.

    Uses `.format()` — inserted values are not scanned again, so chart-fence
    JSON in `final_report` flows through verbatim.
    """
    values = {
        "final_report": ctx.state.get("final_report", "No prior report available."),
        "specialist_reports": _format_specialist_reports(ctx.state),
        "research_coverage": ctx.state.get(
            "research_coverage", "No research coverage notes available."
        ),
        "continuation_notes": ctx.state.get(
            _CONTINUATION_NOTES_KEY, "No continuation notes yet."
        ),
        "places_context": ctx.state.get("places_context", "No restaurant data available."),
        "known_places_context": format_known_places_context(ctx.state),
    }
    return _CONTINUE_RESEARCH_TEMPLATE.format(**values)


def _report_writer_instruction(ctx):
    """Inject the full research material into the final report writer."""
    evidence_memo = ctx.state.get(
        "evidence_memo", "No adjudicated evidence memo available."
    )
    if _is_failed_closed_evidence_memo(evidence_memo):
        specialist_reports = (
            "Evidence adjudication failed closed. Specialist reports are withheld "
            "from writer context because their claims were not adjudicated. Use "
            "Restaurant Context, structured provider facts, and the redacted "
            "Evidence Memo limits only."
        )
    else:
        specialist_reports = _format_specialist_reports(
            ctx.state,
            default="No specialist reports available.",
        )

    values = {
        "places_context": ctx.state.get("places_context", "No restaurant data available."),
        "specialist_reports": specialist_reports,
        "evidence_memo": _format_evidence_memo_for_writer(evidence_memo),
    }
    return _REPORT_WRITER_TEMPLATE.format(**values)


def _evidence_adjudicator_instruction(ctx):
    """Inject specialist validation packets into the evidence adjudicator."""
    values = {
        "places_context": ctx.state.get("places_context", "No restaurant data available."),
        "known_places_context": format_known_places_context(ctx.state),
        "specialist_reports": _format_specialist_reports(
            ctx.state,
            default="No specialist reports available.",
            include_validation_packets=True,
        ),
    }
    return _EVIDENCE_ADJUDICATOR_TEMPLATE.format(**values)


continue_research = LlmAgent(
    name="continue_research",
    model=MODEL_GEMINI,
    instruction=_continue_research_instruction,
    description=(
        "Continues an existing research thread using prior research, venue "
        "context, observable focused helpers, and bounded specialist deepening."
    ),
    tools=[
        read_web_pages,
        fetch_web_content,
        fetch_web_content_batch,
        *_ENRICHER_TOOLS,
        *(
            AgentTool(agent=spec, include_plugins=True)
            for spec in CONTINUATION_SPECIALISTS
        ),
    ],
    generate_content_config=MEDIUM_THINKING_CONFIG,
    before_model_callback=_inject_geo_bias,
    on_model_error_callback=_on_model_error,
    on_tool_error_callback=_on_tool_error,
    after_agent_callback=_record_continuation_notes,
    # Distinct from `final_report` so a continuation reply doesn't overwrite
    # the original research report in session state. The next continuation
    # should still read the original full report as the durable base.
    output_key="continue_research_reply",
)

# --- Router instruction provider ---

_ROUTER_TEMPLATE = (INSTRUCTIONS_DIR / "router.md").read_text()


def _router_instruction(ctx):
    """Append session state info so the router knows whether a report exists."""
    has_report = bool(ctx.state.get("final_report"))
    if has_report:
        note = (
            "\n\n## Session state\n\n"
            "A research report has already been delivered in this conversation."
        )
    else:
        note = "\n\n## Session state\n\nNo research has been done yet in this conversation."
    return _ROUTER_TEMPLATE + note


# --- Agent definitions ---

research_lead = LlmAgent(
    name="research_lead",
    model=MODEL_GEMINI,
    instruction=_research_lead_instruction,
    description="Plans research, calls specialist agents as tools, and records research coverage.",
    tools=[
        google_search,
        *(AgentTool(agent=spec, include_plugins=True) for spec in ALL_SPECIALISTS),
    ],
    output_key="research_coverage",
    generate_content_config=ORCHESTRATOR_THINKING_CONFIG,
    before_model_callback=_inject_geo_bias,
)

evidence_adjudicator = LlmAgent(
    name="evidence_adjudicator",
    model=SPECIALIST_GEMINI,
    instruction=_evidence_adjudicator_instruction,
    description="Validates specialist claim/source packets with a bounded source reader.",
    tools=[read_adjudicator_sources],
    output_key="evidence_memo",
    generate_content_config=MEDIUM_THINKING_CONFIG,
    after_agent_callback=_record_evidence_adjudicator_fallback,
    on_model_error_callback=_on_model_error,
    on_tool_error_callback=_on_tool_error,
)

report_writer = LlmAgent(
    name="report_writer",
    model=MODEL_GEMINI,
    instruction=_report_writer_instruction,
    description="Writes the final user-facing research report from specialist evidence.",
    output_key="final_report",
    generate_content_config=ORCHESTRATOR_THINKING_CONFIG,
)

# --- Pipeline ---

research_pipeline = SequentialAgent(
    name="research_pipeline",
    sub_agents=[_make_enricher(), research_lead, evidence_adjudicator, report_writer],
    description="Enriches context, researches, validates evidence, then writes the report.",
)

# --- Router (root agent) ---

_router = LlmAgent(
    name="router",
    model=_FAST_MODEL,
    instruction=_router_instruction,
    description="Routes user questions to research, continuation, or asks for clarification.",
    sub_agents=[research_pipeline, continue_research],
    output_key="router_response",
)

app = App(
    name="superextra_agent",
    root_agent=_router,
    plugins=[
        ChatLoggerPlugin(),
        FirestoreProgressPlugin(
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
        ),
    ],
)
root_agent = _router
