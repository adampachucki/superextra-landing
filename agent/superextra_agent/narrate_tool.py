"""`narrate(text)` — a no-op tool that gives the model a typed slot for
inline progress narrative.

Models registered with this tool are instructed to call `narrate` as the
first tool call in any tool-using response, with one sentence describing
what is about to happen. The tool itself does nothing — it just returns
an acknowledgement so the model sees the call succeed and can continue.

The actual note emission happens in `firestore_events.map_event`, which
captures the function-call arguments at event-mapping time. This works
because ADK 1.28 yields the model-response event (containing all
function-call parts as siblings) before the function-call execution loop
starts (`base_llm_flow.py:914-918`), so the note lands in Firestore with
a `seqInAttempt` strictly earlier than any specialist's tool-response
events from the same model turn — even though tool execution itself is
parallel under `asyncio.gather` (`functions.py:387-404`).

See `docs/inline-narrative-via-narrate-tool-2026-04-30.md` for full
context.
"""

from __future__ import annotations

import logging

from google.adk.tools.tool_context import ToolContext

log = logging.getLogger(__name__)


async def narrate(text: str, tool_context: ToolContext) -> dict[str, bool]:
    """Surface a one-sentence narrative to the user before the next batch of work.

    Args:
        text: One sentence (≤25 words) in the user's language describing
            what the agent is about to investigate. Reference concrete
            entities (venue names, neighborhoods, timeframes) when known.

    Returns:
        ``{"acknowledged": True}`` so the model sees the call succeed.
    """
    log.debug("narrate: %r", text)
    return {"acknowledged": True}
