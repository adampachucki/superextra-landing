"""Resolve the per-turn prompt language into one uniform instruction directive.

`promptLanguage` (an ISO-639-1 code) is seeded into session state by the Cloud
Function — agentStream detects it from the raw user message and gear-handoff
puts it on the per-turn `stateDelta`. Every agent prepends the directive below
so its thoughts AND output use a single language, instead of each agent
independently inferring it from English-prefixed context and briefs (which
drift toward English).
"""

PROMPT_LANGUAGE_KEY = "promptLanguage"

# ISO-639-1 → English name, for a natural directive ("write in Polish"). Misses
# fall back to an ISO-code clause, which the model still honours.
_LANGUAGE_NAMES = {
    "en": "English",
    "de": "German",
    "pl": "Polish",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "nl": "Dutch",
    "pt": "Portuguese",
    "uk": "Ukrainian",
    "ru": "Russian",
    "cs": "Czech",
    "sk": "Slovak",
    "ro": "Romanian",
    "hu": "Hungarian",
    "sv": "Swedish",
    "da": "Danish",
    "nb": "Norwegian",
    "no": "Norwegian",
    "fi": "Finnish",
    "tr": "Turkish",
    "el": "Greek",
    "bg": "Bulgarian",
    "hr": "Croatian",
    "sl": "Slovenian",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "et": "Estonian",
    "ca": "Catalan",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
    "he": "Hebrew",
}


def language_clause(code) -> str:
    """A readable name ("Polish") for a known code, an ISO-code clause for an
    unknown two-letter code, or "English" for anything unusable."""
    c = code.strip().lower()[:2] if isinstance(code, str) else ""
    name = _LANGUAGE_NAMES.get(c)
    if name:
        return name
    if len(c) == 2 and c.isalpha():
        return f"the language with ISO 639-1 code '{c}'"
    return "English"


def _state_language(state) -> str:
    getter = getattr(state, "get", None)
    code = getter(PROMPT_LANGUAGE_KEY) if callable(getter) else None
    return language_clause(code)


def language_directive(state) -> str:
    """The directive every agent prepends. `state` is the ADK session state
    dict (`ctx.state` / `callback_context.state`)."""
    lang = _state_language(state)
    return (
        "## Language — ABSOLUTE RULE\n\n"
        f"Write 100% of your output in {lang}, with no exceptions. This includes "
        "EVERY thinking step and thought summary — including the short **bold "
        f"title** that opens each thinking step — every status line, every "
        f"specialist brief you write, and the final report. Think in {lang}, not "
        f"in English. Even when the tools, place data, search results, briefs, or "
        f"context are in English, you still reason and write in {lang}. Never open "
        "a thought, title, or section in English. Keep proper nouns — venue and "
        "brand names, URLs — in their original form.\n\n"
    )


def language_reminder(state) -> str:
    """A short recency reinforcement appended to the END of every instruction —
    thought-summary language follows the most recent instruction more than the
    first, so the rule is stated at both ends."""
    lang = _state_language(state)
    return (
        f"\n\n## Reminder\n\nWrite everything — your thinking, every **bold "
        f"thinking-step title**, and the report — in {lang}. Do not start any "
        f"thought or title in English unless {lang} is English."
    )


def with_language(state, body: str) -> str:
    """Wrap an instruction body with the language directive (front, for
    prominence) and reminder (end, for recency)."""
    return language_directive(state) + body + language_reminder(state)
