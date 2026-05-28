"""Configurable usage gates, attached as `before_agent_callback` on the two
research-capable agents.

Each quota is a `{scope, period, limit}` triple, read per turn from
`config/limits` (Console-editable; changes take effect immediately):

  - **scope**  — where the counter lives. `account` = one counter per user;
    `research` = one counter per chat (a chat ≈ one research, since the
    router runs `research_pipeline` at most once per chat). The `research`
    quota is always account-scoped; only `continue` scope is configurable.
  - **period** — reset cadence: `day | week | month | year | ever`,
    implemented as a period-key string. The counter resets when the stored
    key != the current key. `ever` is a constant key (never resets).
  - **limit**  — the number, optionally overridden per user via
    `users/{uid}.limitOverrides.{research,continue}`.

Enforcement is entirely inside the engine. Each gate runs one Firestore
transaction: read the user doc (plan + override), resolve the spec, read the
counter doc, check, and increment — or halt the agent with a `types.Content`
block reply. Returning Content sets `ctx.end_invocation` (per
`google/adk/agents/base_agent.py:471-480`), halting every sub-agent/tool.
The reply is written to `state["quota_block_reply"]` so
`firestore_events._map_complete` surfaces it and `_capture_final` tags it
`turnKind="quota_block"`.

A turn routes to exactly one of the two agents, so the counters never both
tick. Account-scoped continue lives on the user doc; research-scoped continue
lives in the `sessions/{sid}/quota/continue` subdoc (off the busy session doc
and out of the client's listener path). Failed/cancelled work still burns the
credit (reserve happens before the agent runs; no refund). Any error fails
open — these are fairness caps, not security boundaries.
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

_VALID_PERIODS = ("day", "week", "month", "year", "ever")
_VALID_SCOPES = ("account", "research")

# Code fallback when `config/limits` is missing or a field is malformed.
# Mirrors the daily model so a misconfig fails generous-but-bounded.
_DEFAULT_LIMITS: dict[str, dict[str, dict[str, Any]]] = {
    "free": {
        "research": {"scope": "account", "period": "day", "limit": 1},
        "continue": {"scope": "account", "period": "day", "limit": 5},
    },
    "paid": {
        "research": {"scope": "account", "period": "day", "limit": 50},
        "continue": {"scope": "account", "period": "day", "limit": 100},
    },
}

_fs: firestore.Client | None = None


def _client() -> firestore.Client:
    global _fs
    if _fs is None:
        _fs = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site"))
    return _fs


def _limits_config(fs: firestore.Client) -> dict[str, Any]:
    """Raw `config/limits` doc (or empty). Validation happens in `_resolve_spec`."""
    snap = fs.collection("config").document("limits").get()
    return (snap.to_dict() or {}) if snap.exists else {}


def _plan(user_doc: dict | None) -> str:
    return "paid" if (user_doc or {}).get("plan") == "paid" else "free"


def _sanitize_limit(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int) and value >= 0:
        return value
    return fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _period_key(period: str, now: datetime) -> str:
    """Current period bucket as a string. Counter resets when this changes."""
    if period == "week":
        return now.strftime("%G-W%V")  # ISO year + ISO week (resets Monday)
    if period == "month":
        return now.strftime("%Y-%m")
    if period == "year":
        return now.strftime("%Y")
    if period == "ever":
        return "ever"
    return now.strftime("%Y-%m-%d")  # day, and the safe fallback for unknown


def _reset_phrase(period: str) -> str:
    return {"day": "tomorrow", "week": "next week", "month": "next month", "year": "next year"}.get(
        period, ""
    )


def _resolve_spec(config: dict[str, Any], plan: str, quota: str, user_doc: dict | None) -> dict[str, Any]:
    """Resolve `{scope, period, limit}` for one quota. Invalid config fields
    fall back to the per-plan default and are logged loudly (fail-generous —
    a misconfig under-enforces rather than locking users out)."""
    defaults = _DEFAULT_LIMITS[plan][quota]
    raw = _dict(_dict(config.get(plan)).get(quota))

    period = raw.get("period")
    if period not in _VALID_PERIODS:
        if period is not None:
            log.warning("quota config: invalid period %r for %s/%s; using %r", period, plan, quota, defaults["period"])
        period = defaults["period"]

    if quota == "research":
        scope = "account"  # a per-research research limit is meaningless
    else:
        scope = raw.get("scope")
        if scope not in _VALID_SCOPES:
            if scope is not None:
                log.warning("quota config: invalid scope %r for %s/%s; using %r", scope, plan, quota, defaults["scope"])
            scope = defaults["scope"]

    base = _sanitize_limit(raw.get("limit"), defaults["limit"])
    overrides = _dict(_dict(user_doc).get("limitOverrides"))
    limit = _sanitize_limit(overrides.get(quota), base)

    return {"scope": scope, "period": period, "limit": limit}


def _reserve(
    txn: firestore.Transaction,
    user_ref: firestore.DocumentReference,
    session_quota_ref: firestore.DocumentReference | None,
    config: dict[str, Any],
    quota: str,
    count_field: str,
    period_field: str,
    now: datetime,
) -> tuple[bool, str, str]:
    """One transaction: read user (plan + override) → resolve spec → read the
    counter doc → check + increment. All reads precede the single write.
    Returns ``(reserved, plan, period)``."""
    user_snap = user_ref.get(transaction=txn)
    user_data = (user_snap.to_dict() or {}) if user_snap.exists else None
    plan = _plan(user_data)
    spec = _resolve_spec(config, plan, quota, user_data)

    if spec["scope"] == "research" and session_quota_ref is not None:
        counter_ref = session_quota_ref
        counter_snap = counter_ref.get(transaction=txn)
        counter_data = (counter_snap.to_dict() or {}) if counter_snap.exists else None
        counter_exists = counter_snap.exists
    else:
        counter_ref, counter_data, counter_exists = user_ref, user_data, user_snap.exists

    key = _period_key(spec["period"], now)
    used = (counter_data or {}).get(count_field, 0) if (counter_data or {}).get(period_field) == key else 0
    if used >= spec["limit"]:
        return (False, plan, spec["period"], spec["scope"])

    update = {period_field: key, count_field: used + 1, "updatedAt": firestore.SERVER_TIMESTAMP}
    if counter_exists:
        txn.update(counter_ref, update)
    elif counter_ref is user_ref:
        txn.set(counter_ref, {"plan": "free", "createdAt": firestore.SERVER_TIMESTAMP, **update})
    else:
        txn.set(counter_ref, {"createdAt": firestore.SERVER_TIMESTAMP, **update})
    return (True, plan, spec["period"], spec["scope"])


_reserve_txn = firestore.transactional(_reserve)


def _research_block_message(plan: str, period: str, scope: str) -> str:
    suffix = "" if plan == "paid" else " on the free plan"  # research is always account-scoped
    phrase = _reset_phrase(period)
    if phrase:
        return f"Research limit reached{suffix}. Try again {phrase}."
    return f"You've used your research allowance{suffix}."


def _continue_block_message(plan: str, period: str, scope: str) -> str:
    suffix = "" if plan == "paid" else " on the free plan"
    where = " for this chat" if scope == "research" else ""
    phrase = _reset_phrase(period)
    if phrase:
        return f"Follow-up limit reached{where}{suffix}. Try again {phrase}."
    if scope == "research":
        return f"You've used the follow-ups for this chat{suffix}."
    return f"You've used your follow-up allowance{suffix}."


def _make_gate(
    *,
    quota: str,
    count_field: str,
    period_field: str,
    block_message: Callable[[str, str, str], str],
):
    """Build a `before_agent_callback` that reserves one credit of `quota` in
    a single transaction, or halts the agent with a friendly block reply."""

    async def gate(*, callback_context: CallbackContext):
        # `quotaUid` (submitter) is set per-turn by the Cloud Function; fall
        # back to engine `user_id` (session creator) for the creator's own
        # turns / local dev.
        quota_uid = callback_context.state.get("quotaUid") or callback_context.user_id
        if not quota_uid:
            return None
        sid = callback_context.state.get("firestoreSid")

        try:
            fs = _client()
            now = datetime.now(timezone.utc)
            config = await asyncio.to_thread(_limits_config, fs)
            user_ref = fs.collection("users").document(quota_uid)
            session_quota_ref = (
                fs.collection("sessions").document(sid).collection("quota").document("continue")
                if (quota == "continue" and sid)
                else None
            )
            reserved, plan, period, scope = await asyncio.to_thread(
                _reserve_txn, fs.transaction(), user_ref, session_quota_ref, config, quota, count_field, period_field, now
            )
        except Exception:  # noqa: BLE001
            # Fail open on ANY error — a fairness cap must never hard-block a
            # paying user mid-run. Errors are logged loudly instead.
            log.exception("quota gate (%s) failed; allowing uid=%s", quota, quota_uid)
            return None

        if reserved:
            return None

        reply = block_message(plan, period, scope)
        callback_context.state[QUOTA_BLOCK_REPLY_KEY] = reply
        return types.Content(role="model", parts=[types.Part(text=reply)])

    return gate


research_quota_gate = _make_gate(
    quota="research",
    count_field="researchCount",
    period_field="researchPeriodKey",
    block_message=_research_block_message,
)

continue_quota_gate = _make_gate(
    quota="continue",
    count_field="continueCount",
    period_field="continuePeriodKey",
    block_message=_continue_block_message,
)
