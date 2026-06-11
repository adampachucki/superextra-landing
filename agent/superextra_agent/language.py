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
    if lang == "English":
        return (
            "## Language\n\n"
            "The whole conversation is in English. Write everything in English — "
            "the report, every reply and status line, specialist briefs, and your "
            "thoughts (including the short **bold title** that opens each thinking "
            "step). Keep proper nouns — venue and brand names, URLs — unchanged.\n\n"
        )
    # Non-English: the model leaks specific procedural thinking titles into
    # English ("Searching for…", "Gathering data") even when told to use {lang},
    # so name those patterns explicitly.
    return (
        "## Language\n\n"
        f"The whole conversation is in {lang}. Write 100% of your output in {lang} — "
        f"the report, every reply and status line, specialist briefs, and your "
        f"thoughts. Each thinking step opens with a short **bold title**; write that "
        f"title in {lang}, not English. Concretely, never produce English thinking "
        f"titles like '**Searching for…**', '**Gathering data**', '**Analyzing the "
        f"market**', '**Investigating…**' — write them in {lang}. Tools, place data, "
        f"and sources are often in English; narrate your thinking in {lang} anyway. "
        "Keep proper nouns — venue and brand names, URLs — unchanged.\n\n"
    )
