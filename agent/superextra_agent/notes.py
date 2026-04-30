"""Best-effort Gemini-Flash session title generation.

Falls back to the user query (prefix-stripped) on timeout or error.
``_genai_client`` is lazy and process-local.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Optional

from google.genai import Client as GenaiClient
from google.genai import types

log = logging.getLogger(__name__)

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
TITLE_MODEL = os.environ.get("TITLE_MODEL", "gemini-2.5-flash")

TITLE_TIMEOUT_S = 5.0

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
