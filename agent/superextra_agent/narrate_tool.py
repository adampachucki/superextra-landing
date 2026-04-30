"""`narrate(text)` — no-op affordance for inline progress narrative.

The actual note emission happens in `firestore_events.map_event` —
this tool just gives the model a typed slot to put the text into.
"""

from __future__ import annotations

import logging

from google.adk.tools.tool_context import ToolContext

log = logging.getLogger(__name__)


async def narrate(text: str, tool_context: ToolContext) -> dict[str, bool]:
    """Surface a one-sentence narrative to the user before the next batch of work."""
    log.debug("narrate: %r", text)
    return {"acknowledged": True}
