"""Daily usage gates, attached as `before_agent_callback` on the two
research-capable agents.

Two independent daily counters per user, both enforced inside the engine
(Cloud Functions no longer pre-check):

  - `researchRunsToday`  — full `research_pipeline` runs (free: 1/day)
  - `continueRunsToday`  — `continue_research` turns      (free: 5/day)

Each gate is a `before_agent_callback`. Returning `types.Content` halts the
agent before any sub-agent / tool runs (per
`google/adk/agents/base_agent.py:471-480`, which sets
`ctx.end_invocation = True` when the callback yields content). The block
reply is written to `state["quota_block_reply"]` so
`firestore_events._map_complete` surfaces it and `_capture_final` tags it
`turnKind="agent_reply"` — a blocked turn never looks like research.

A turn is routed to exactly one of the two agents, so the two counters
never both tick on the same turn. Counters use separate date fields so the
gates stay fully independent. Failed/cancelled work still burns the credit
(the counter ticks before the agent runs; no refund).

Limits come from `config/limits.{plan}.{researchPerDay,continuePerDay}`,
with optional per-user `users/{uid}.limitOverrides.{key}`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

from google.adk.agents.callback_context import CallbackContext
from google.cloud import firestore
from google.genai import types

log = logging.getLogger(__name__)

QUOTA_BLOCK_REPLY_KEY = "quota_block_reply"

_DEFAULT_LIMITS: dict[str, dict[str, int]] = {
    "free": {"researchPerDay": 1, "continuePerDay": 5},
    "paid": {"researchPerDay": 50, "continuePerDay": 100},
}

_fs: firestore.Client | None = None


def _client() -> firestore.Client:
    global _fs
    if _fs is None:
        _fs = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site"))
    return _fs


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _sanitize_limit(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int) and value >= 0:
        return value
    return fallback


def _limits_config(fs: firestore.Client) -> dict[str, dict[str, int]]:
    """Read `config/limits`. Missing doc / bad values fall back to per-plan
    defaults (the doc is Console-editable)."""
    snap = fs.collection("config").document("limits").get()
    raw = (snap.to_dict() or {}) if snap.exists else {}
    return {
        plan: {key: _sanitize_limit((raw.get(plan) or {}).get(key), default) for key, default in defaults.items()}
        for plan, defaults in _DEFAULT_LIMITS.items()
    }


def _plan(user_doc: dict | None) -> str:
    return "paid" if (user_doc or {}).get("plan") == "paid" else "free"


def _resolve_limit(user_doc: dict | None, config: dict[str, dict[str, int]], key: str) -> int:
    plan = _plan(user_doc)
    base = config.get(plan, _DEFAULT_LIMITS[plan]).get(key, _DEFAULT_LIMITS[plan][key])
    overrides = (user_doc or {}).get("limitOverrides") or {}
    return _sanitize_limit(overrides.get(key), base)


def _check_and_reserve(
    txn: firestore.Transaction,
    user_ref: firestore.DocumentReference,
    today: str,
    config: dict[str, dict[str, int]],
    limit_key: str,
    counter_field: str,
    date_field: str,
) -> tuple[bool, str]:
    """Single Firestore transaction: read counter, roll on UTC date change,
    increment if under limit. Returns ``(reserved, plan)`` — plan is returned
    so the caller can word a block message without re-reading the doc."""
    snap = user_ref.get(transaction=txn)
    data = (snap.to_dict() or {}) if snap.exists else None
    plan = _plan(data)
    limit = _resolve_limit(data, config, limit_key)
    used = (data or {}).get(counter_field, 0) if (data or {}).get(date_field) == today else 0
    if used >= limit:
        return (False, plan)
    update = {
        date_field: today,
        counter_field: used + 1,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if snap.exists:
        txn.update(user_ref, update)
    else:
        # Lazy provision — the Cloud Function normally writes identity first;
        # this only fires if the gate somehow runs before any identity write.
        txn.set(user_ref, {"plan": "free", "createdAt": firestore.SERVER_TIMESTAMP, **update})
    return (True, plan)


_reserve_txn = firestore.transactional(_check_and_reserve)


def _research_block_message(plan: str) -> str:
    if plan == "paid":
        return "Daily research limit reached. Try again tomorrow."
    return "Daily research limit reached on the free plan. Try again tomorrow."


def _continue_block_message(plan: str) -> str:
    if plan == "paid":
        return "Daily follow-up limit reached. Try again tomorrow."
    return "Daily follow-up limit reached on the free plan. Try again tomorrow."


def _make_gate(
    *,
    limit_key: str,
    counter_field: str,
    date_field: str,
    block_message: Callable[[str], str],
):
    """Build a `before_agent_callback` that atomically reserves one daily
    credit of the given kind, or halts the agent with a friendly block reply."""

    async def gate(*, callback_context: CallbackContext):
        # `quotaUid` (submitter) is set per-turn by the Cloud Function; fall
        # back to engine `user_id` (the session creator) for the creator's own
        # turns / local dev.
        quota_uid = callback_context.state.get("quotaUid") or callback_context.user_id
        if not quota_uid:
            return None

        try:
            fs = _client()
            user_ref = fs.collection("users").document(quota_uid)
            config = await asyncio.to_thread(_limits_config, fs)
            reserved, plan = await asyncio.to_thread(
                _reserve_txn, fs.transaction(), user_ref, _today_utc(), config, limit_key, counter_field, date_field
            )
        except Exception:  # noqa: BLE001
            # Fail open on ANY error (not just Firestore). This is a fairness
            # cap, not a security boundary — a bug here must never hard-block a
            # paying user mid-research. Errors are logged loudly instead.
            log.exception("quota gate (%s) failed; allowing uid=%s", counter_field, quota_uid)
            return None

        if reserved:
            return None

        reply = block_message(plan)
        callback_context.state[QUOTA_BLOCK_REPLY_KEY] = reply
        return types.Content(role="model", parts=[types.Part(text=reply)])

    return gate


research_quota_gate = _make_gate(
    limit_key="researchPerDay",
    counter_field="researchRunsToday",
    date_field="lastResearchDateUtc",
    block_message=_research_block_message,
)

continue_quota_gate = _make_gate(
    limit_key="continuePerDay",
    counter_field="continueRunsToday",
    date_field="lastContinueDateUtc",
    block_message=_continue_block_message,
)
