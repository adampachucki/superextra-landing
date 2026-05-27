"""Daily-research-runs quota gate, attached as `before_agent_callback` on the
`research_pipeline` SequentialAgent.

The gate is the single enforcement point. Cloud Functions no longer pre-check.
Returning `types.Content` halts `research_pipeline` before any sub-agent runs
(per `google/adk/agents/base_agent.py:471-480`, which sets
`ctx.end_invocation = True` when the callback yields content). The reply tag
`turnKind="agent_reply"` is preserved by writing into a dedicated state key
`quota_block_reply` that `firestore_events._map_complete` recognizes.

Failed and cancelled research runs DO burn the quota — the counter ticks
*before* the pipeline runs, and we never refund. Concurrent runs are
serialized by the Firestore transaction on the single `users/{uid}` doc.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.cloud import firestore
from google.genai import types

log = logging.getLogger(__name__)

QUOTA_BLOCK_REPLY_KEY = "quota_block_reply"

_DEFAULT_LIMITS = {"free": 1, "paid": 50}
_CONFIG_TTL_SECONDS = 60

_fs: firestore.Client | None = None
_config_cache: dict[str, int] | None = None
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


def _research_limits(fs: firestore.Client) -> dict[str, int]:
    """Read `config/limits.{plan}.researchPerDay` with a 60s cache. Missing
    config doc falls back to defaults; the doc is editable from Firebase
    Console so bad values are clamped per-plan."""
    global _config_cache, _config_cached_at
    if _config_cache is not None and time.time() - _config_cached_at < _CONFIG_TTL_SECONDS:
        return _config_cache
    snap = fs.collection("config").document("limits").get()
    raw = snap.to_dict() or {} if snap.exists else {}
    free = _sanitize_limit((raw.get("free") or {}).get("researchPerDay"), _DEFAULT_LIMITS["free"])
    paid = _sanitize_limit((raw.get("paid") or {}).get("researchPerDay"), _DEFAULT_LIMITS["paid"])
    _config_cache = {"free": free, "paid": paid}
    _config_cached_at = time.time()
    return _config_cache


def _resolve_limit(user_doc: dict | None, limits: dict[str, int]) -> int:
    plan = "paid" if (user_doc or {}).get("plan") == "paid" else "free"
    base = limits.get(plan, _DEFAULT_LIMITS[plan])
    overrides = ((user_doc or {}).get("limitOverrides") or {})
    return _sanitize_limit(overrides.get("researchPerDay"), base)


def _check_and_reserve(
    txn: firestore.Transaction,
    user_ref: firestore.DocumentReference,
    today: str,
    limits: dict[str, int],
) -> tuple[bool, int]:
    """Single Firestore transaction: read counter, roll on UTC date change,
    increment if under limit. Returns ``(allowed, limit)``."""
    snap = user_ref.get(transaction=txn)
    data = snap.to_dict() or {} if snap.exists else None
    limit = _resolve_limit(data, limits)
    last_date = (data or {}).get("lastResearchDateUtc")
    used = (data or {}).get("researchRunsToday", 0) if last_date == today else 0
    if used >= limit:
        return (False, limit)
    update = {
        "lastResearchDateUtc": today,
        "researchRunsToday": used + 1,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if snap.exists:
        txn.update(user_ref, update)
    else:
        # Lazy provision — preserves identity + plan defaults. Cloud Function
        # still writes identity fields on session create; this branch only
        # fires if the gate runs before any identity write (unlikely but
        # tolerable).
        txn.set(user_ref, {"plan": "free", "createdAt": firestore.SERVER_TIMESTAMP, **update})
    return (True, limit)


def _block_message(user_doc: dict | None) -> str:
    plan = "paid" if (user_doc or {}).get("plan") == "paid" else "free"
    if plan == "paid":
        return "Daily research limit reached. Try again tomorrow."
    return "Daily research limit reached on the free plan. Try again tomorrow."


async def research_quota_gate(*, callback_context: CallbackContext):
    """`before_agent_callback` on `research_pipeline`.

    Returns ``None`` to let the pipeline run, or ``types.Content`` to halt it
    with a friendly limit-reached reply. Also writes
    ``state[QUOTA_BLOCK_REPLY_KEY]`` on block so the reply is tagged
    ``turnKind="agent_reply"`` via firestore_events recognition.
    """
    # Prefer `quotaUid` from session state (set per-turn by the Cloud Function
    # to the SUBMITTER's uid). Fall back to engine `user_id`, which equals the
    # session creator's uid — only relevant for the original creator's own
    # turns or local dev.
    quota_uid = callback_context.state.get("quotaUid") or callback_context.user_id
    if not quota_uid:
        # Anonymous / no-auth path — let the pipeline run. The Cloud Function
        # gates anonymous tokens upstream; reaching the gate without a UID
        # means something already vouched for the caller (e.g. local dev).
        return None

    user_doc: dict | None = None
    try:
        fs = _client()
        today = _today_utc()
        user_ref = fs.collection("users").document(quota_uid)
        limits = await asyncio.to_thread(_research_limits, fs)
        txn_fn = firestore.transactional(_check_and_reserve)
        allowed, _limit = await asyncio.to_thread(
            txn_fn, fs.transaction(), user_ref, today, limits
        )
    except Exception:  # noqa: BLE001
        # Fail open — a Firestore outage shouldn't block a paying user. The
        # rate cap is a product fairness control, not a security boundary.
        log.exception("quota gate Firestore failure; allowing uid=%s", quota_uid)
        return None

    if allowed:
        return None

    # On block, read the user doc once more (outside the txn) just for plan,
    # so the message can match. Fail-soft to the default free message.
    try:
        snap = await asyncio.to_thread(user_ref.get)
        if snap.exists:
            user_doc = snap.to_dict() or {}
    except Exception:  # noqa: BLE001
        pass
    reply = _block_message(user_doc)
    callback_context.state[QUOTA_BLOCK_REPLY_KEY] = reply
    return types.Content(role="model", parts=[types.Part(text=reply)])
