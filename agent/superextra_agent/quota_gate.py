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
(the counter ticks before the agent runs; no refund). Any Firestore error
fails open — these are product fairness controls, not security boundaries.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
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
_CONFIG_TTL_SECONDS = 60

_fs: firestore.Client | None = None
_config_cache: dict[str, dict[str, int]] | None = None
_config_cached_at: float = 0.0


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
    """Read `config/limits` with a 60s cache. Missing doc / bad values fall
    back to per-plan defaults (the doc is Console-editable)."""
    global _config_cache, _config_cached_at
    if _config_cache is not None and time.time() - _config_cached_at < _CONFIG_TTL_SECONDS:
        return _config_cache
    snap = fs.collection("config").document("limits").get()
    raw = (snap.to_dict() or {}) if snap.exists else {}
    config: dict[str, dict[str, int]] = {}
    for plan, defaults in _DEFAULT_LIMITS.items():
        plan_raw = raw.get(plan) or {}
        config[plan] = {
            key: _sanitize_limit(plan_raw.get(key), default) for key, default in defaults.items()
        }
    _config_cache = config
    _config_cached_at = time.time()
    return config


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
) -> bool:
    """Single Firestore transaction: read counter, roll on UTC date change,
    increment if under limit. Returns True if the credit was reserved."""
    snap = user_ref.get(transaction=txn)
    data = (snap.to_dict() or {}) if snap.exists else None
    limit = _resolve_limit(data, config, limit_key)
    used = (data or {}).get(counter_field, 0) if (data or {}).get(date_field) == today else 0
    if used >= limit:
        return False
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
    return True


def _research_block_message(user_doc: dict | None) -> str:
    if _plan(user_doc) == "paid":
        return "Daily research limit reached. Try again tomorrow."
    return "Daily research limit reached on the free plan. Try again tomorrow."


def _continue_block_message(user_doc: dict | None) -> str:
    if _plan(user_doc) == "paid":
        return "Daily follow-up limit reached. Try again tomorrow."
    return "Daily follow-up limit reached on the free plan. Try again tomorrow."


def _make_gate(
    *,
    limit_key: str,
    counter_field: str,
    date_field: str,
    block_message: Callable[[dict | None], str],
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

        user_ref = None
        try:
            fs = _client()
            today = _today_utc()
            user_ref = fs.collection("users").document(quota_uid)
            config = await asyncio.to_thread(_limits_config, fs)
            txn_fn = firestore.transactional(_check_and_reserve)
            allowed = await asyncio.to_thread(
                txn_fn, fs.transaction(), user_ref, today, config, limit_key, counter_field, date_field
            )
        except Exception:  # noqa: BLE001
            log.exception("quota gate (%s) Firestore failure; allowing uid=%s", counter_field, quota_uid)
            return None

        if allowed:
            return None

        # Re-read the user doc just for plan, so the message matches. Fail-soft.
        user_doc: dict | None = None
        try:
            snap = await asyncio.to_thread(user_ref.get)
            if snap.exists:
                user_doc = snap.to_dict() or {}
        except Exception:  # noqa: BLE001
            pass
        reply = block_message(user_doc)
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
