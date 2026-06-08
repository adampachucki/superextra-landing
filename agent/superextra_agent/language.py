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


def language_directive(state) -> str:
    """The directive every agent prepends. `state` is the ADK session state
    dict (`ctx.state` / `callback_context.state`)."""
    getter = getattr(state, "get", None)
    code = getter(PROMPT_LANGUAGE_KEY) if callable(getter) else None
    lang = language_clause(code)
    return (
        "## Language\n\n"
        f"The user's language for this request is {lang}. Write EVERYTHING in {lang}: "
        "internal reasoning and thoughts, every status update, any specialist briefs "
        "you write, and the final report. Do not switch to English (or any other "
        "language) for any part, even when source material, tools, place data, or "
        "context appear in English. Keep proper nouns — venue and brand names, URLs — "
        "in their original form.\n\n"
    )
