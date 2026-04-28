"""Title + timeline-note generation for `FirestoreProgressPlugin`.

  1. Generate a short Gemini-Flash title for the first turn of a session.
  2. Generate one short Gemini-Flash progress note per timeline milestone.

Both are **best-effort** — every path through has a deterministic
fallback. The shared call-site is ``_emit_note_task``, which the plugin
spawns from ``on_event_callback`` as an ``asyncio.Task`` so the LLM
call can overlap with the next event.

``_genai_client`` is constructed lazily on first use; the lazy init is
process-local.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Optional

from google.genai import Client as GenaiClient
from google.genai import types

from .timeline import TimelineWriter, TurnSummaryBuilder

log = logging.getLogger(__name__)

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
TITLE_MODEL = os.environ.get("TITLE_MODEL", "gemini-2.5-flash")
NOTE_MODEL = os.environ.get("NOTE_MODEL", "gemini-2.5-flash")

TITLE_TIMEOUT_S = 5.0
NOTE_TIMEOUT_S = 8.0

_QUERY_CONTEXT_PREFIXES = ("[Date:", "[Context:")

_genai_client: Optional[GenaiClient] = None


def _get_genai_client() -> GenaiClient:
    """Lazy-init the global-endpoint Vertex AI client used for title +
    note generation. Flash 2.5 is only served from `location='global'`."""
    global _genai_client
    if _genai_client is None:
        _genai_client = GenaiClient(vertexai=True, project=PROJECT, location="global")
    return _genai_client


# ── Query-prefix stripping (shared by title + note paths) ────────────────────


def _strip_query_prefixes(text: str) -> str:
    """Remove agentStream-added [Date: ...] and [Context: ...] prefixes so the
    fallback title isn't just "[Date: 2026-04-20]"."""
    cleaned = text
    while True:
        cleaned = cleaned.lstrip()
        if not any(cleaned.startswith(p) for p in _QUERY_CONTEXT_PREFIXES):
            break
        end = cleaned.find("]")
        if end == -1:
            break
        cleaned = cleaned[end + 1 :]
    return cleaned.strip()


# ── Title ────────────────────────────────────────────────────────────────────


def _fallback_title(query_text: str) -> str:
    cleaned = _strip_query_prefixes(query_text)
    if not cleaned:
        return "Untitled"
    return cleaned[:40] if len(cleaned) <= 40 else cleaned[:40].rsplit(" ", 1)[0]


async def _generate_title(query_text: str) -> str:
    """≤ TITLE_TIMEOUT_S call to Gemini Flash. Returns a short title or the
    deterministic fallback on any error / timeout."""
    cleaned_query = _strip_query_prefixes(query_text)
    prompt = (
        "Summarize this message into a short title, max 4 words.\n"
        "Rules:\n"
        "- Use the SAME LANGUAGE as the message\n"
        "- No markdown, no quotes, no punctuation, no numbering\n"
        "- Do not answer the question — just label the topic\n"
        "- Reply with ONLY the title, nothing else\n\n"
        f'Message: "{cleaned_query}"'
    )
    try:

        async def _call() -> str | None:
            resp = await _get_genai_client().aio.models.generate_content(
                model=TITLE_MODEL,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            )
            text = getattr(resp, "text", None)
            if not text:
                return None
            # Strip common noise: quotes, markdown, leading numbering.
            raw = text.strip()
            raw = re.sub(r"^[\"'`]+|[\"'`]+$", "", raw)
            raw = re.sub(r"[*#_`~>\-]", "", raw)
            raw = re.sub(r"^\d+\.\s*", "", raw).strip()
            words = raw.split()
            if not words or len(words) > 8:
                return None
            return " ".join(words[:4])

        result = await asyncio.wait_for(_call(), timeout=TITLE_TIMEOUT_S)
        return result or _fallback_title(query_text)
    except Exception:  # noqa: BLE001
        log.warning("title generation failed, using deterministic fallback", exc_info=True)
        return _fallback_title(query_text)


# ── Timeline notes ───────────────────────────────────────────────────────────


def _notes_llm_disabled() -> bool:
    return os.environ.get("DISABLE_NOTE_LLM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _deterministic_note(milestone: str) -> str:
    return {
        "context_start": "I'm checking the venue and likely peer set before drafting the answer.",
        "plan_ready": "I'm narrowing the research path before validating the strongest signals.",
        "research_placeholder": "I'm validating the strongest signals across source and review coverage.",
        "research_result": "I'm comparing the strongest evidence across sources before drafting the answer.",
    }[milestone]


def _clean_note_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = " ".join(text.strip().split())
    cleaned = re.sub(r"^[\"'`]+|[\"'`]+$", "", cleaned)
    cleaned = re.sub(r"^\d+\.\s*", "", cleaned).strip()
    if not cleaned:
        return None
    if len(cleaned.split()) > 28:
        return None
    if "\n" in cleaned:
        return None
    return cleaned


async def _generate_timeline_note(
    *, milestone: str, query_text: str, input_text: str
) -> str:
    if _notes_llm_disabled():
        return _deterministic_note(milestone)
    prompt = (
        "Write one short first-person research-progress update for a timeline.\n"
        "Rules:\n"
        "- One sentence only\n"
        "- Maximum 28 words\n"
        "- Use the SAME LANGUAGE as the user message\n"
        "- No markdown, no bullets, no quotes\n"
        "- No raw tool names or internal agent names\n"
        "- Do not promise work that has not started\n"
        "- Sound calm and concrete\n\n"
        f"User message:\n{_strip_query_prefixes(query_text)}\n\n"
        f"Milestone: {milestone}\n\n"
        f"Material to summarize:\n{input_text}"
    )
    try:

        async def _call() -> str:
            resp = await _get_genai_client().aio.models.generate_content(
                model=NOTE_MODEL,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(
                    temperature=0,
                    candidate_count=1,
                ),
            )
            return _clean_note_text(getattr(resp, "text", None)) or _deterministic_note(
                milestone
            )

        return await asyncio.wait_for(_call(), timeout=NOTE_TIMEOUT_S)
    except Exception:  # noqa: BLE001
        log.warning(
            "timeline note generation failed; using deterministic fallback", exc_info=True
        )
        return _deterministic_note(milestone)


async def _emit_note_task(
    *,
    writer: TimelineWriter,
    builder: TurnSummaryBuilder,
    milestone: str,
    query_text: str,
    input_text: str,
    counts_snapshot: dict[str, int],
    live_only: bool = False,
) -> None:
    if writer.closed:
        return
    text = await _generate_timeline_note(
        milestone=milestone,
        query_text=query_text,
        input_text=input_text,
    )
    note = builder.add_note(
        milestone=milestone,
        text=text,
        note_source="llm"
        if not _notes_llm_disabled() and text != _deterministic_note(milestone)
        else "deterministic",
        counts=counts_snapshot,
        live_only=live_only,
    )
    if note is not None:
        await writer.write_timeline(note)
