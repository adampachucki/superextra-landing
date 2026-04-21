"""Request-scoped log context for attaching worker-level keys to logs emitted
inside ADK callbacks.

ADK's CallbackContext doesn't expose the worker's Firestore session id (the
`session.id` it offers is the Agent Engine session, a different identifier).
The worker sets `worker_sid` at the top of its /run handler; log calls inside
agent callbacks read it and attach as `extra={"sid": ...}` so structured logs
from both code paths carry the same correlation key.

ContextVar is the right primitive here — it's per-asyncio-task and propagates
to child tasks (including ADK's ParallelAgent fan-out) without sharing state
across concurrent requests.
"""

from contextvars import ContextVar

worker_sid: ContextVar[str | None] = ContextVar("worker_sid", default=None)
