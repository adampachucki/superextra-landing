"""On-the-fly thought translation for the activity feed.

Gemini writes its generic procedural thought-summaries ("Gathering reviews…",
"Fetching TripAdvisor reviews") in English regardless of the language directive
— a model behaviour that prompt-steering can't fix. When the prompt language is
not English we translate each streamed thought into it just before it reaches
Firestore, so the live "thinking" matches the report.

Best-effort: returns the original text on any error or timeout, so the activity
feed never stalls on a translation call. ``_genai_client`` is lazy and
process-local (mirrors ``notes.py``).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from google.genai import Client as GenaiClient
from google.genai import types

from .language import language_clause

log = logging.getLogger(__name__)

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
TRANSLATE_MODEL = os.environ.get("THOUGHT_TRANSLATE_MODEL", "gemini-2.5-flash-lite")
TRANSLATE_TIMEOUT_S = 6.0

_genai_client: Optional[GenaiClient] = None


def _client() -> GenaiClient:
    global _genai_client
    if _genai_client is None:
        _genai_client = GenaiClient(vertexai=True, project=PROJECT, location="global")
    return _genai_client


def _target(code: str | None) -> str | None:
    """Normalize to a translatable target, or None to skip. English is a skip:
    English thoughts are already correct, and skipping avoids a call per thought
    on the common English-prompt path."""
    c = code.strip().lower()[:2] if isinstance(code, str) else ""
    if not c or c == "en":
        return None
    return c


async def localize_thought(text: str, target_code: str | None) -> str:
    """Return ``text`` in the target language, or the original unchanged for an
    empty text, a missing/English target, or any error/timeout."""
    target = _target(target_code)
    if not text or not text.strip() or target is None:
        return text
    lang = language_clause(target)
    prompt = (
        f"You localize a product's activity-feed text into {lang}.\n"
        f"If the text below is already written entirely in {lang}, return it "
        f"verbatim. Otherwise translate it into {lang}.\n"
        "Rules:\n"
        "- Preserve Markdown exactly, including the leading **bold title**.\n"
        "- Keep proper nouns (venue and brand names, URLs) unchanged.\n"
        "- Return ONLY the resulting text, with no preamble or quotes.\n\n"
        f"Text:\n{text}"
    )

    async def _call() -> str | None:
        resp = await _client().aio.models.generate_content(
            model=TRANSLATE_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        )
        return getattr(resp, "text", None)

    try:
        result = await asyncio.wait_for(_call(), timeout=TRANSLATE_TIMEOUT_S)
        cleaned = (result or "").strip()
        return cleaned or text
    except Exception:  # noqa: BLE001
        log.warning("thought translation failed; using original text", exc_info=True)
        return text
