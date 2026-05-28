"""Tests for the configurable {scope, period, limit} usage gates.

Covers: period-key buckets (incl. ISO week + unknown fallback), spec
resolution with validation/override/research-forced-account, the single
reserve transaction (account doc + session subdoc, rollover, lazy provision),
and both gates end-to-end (block messages, quotaUid, fail-open, scope
routing, missing-sid fallback).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from superextra_agent import quota_gate
from superextra_agent.quota_gate import (
    QUOTA_BLOCK_REPLY_KEY,
    _period_key,
    _reserve,
    _reset_phrase,
    _resolve_spec,
    continue_quota_gate,
    research_quota_gate,
)


@pytest.fixture(autouse=True)
def _reset_client():
    quota_gate._fs = None
    yield
    quota_gate._fs = None


def _now(y=2026, m=5, d=28):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


def _config(**overrides):
    """Daily-equivalent default config; override per-plan/quota with dotted dicts."""
    base = {
        "free": {
            "research": {"scope": "account", "period": "day", "limit": 1},
            "continue": {"scope": "account", "period": "day", "limit": 5},
        },
        "paid": {
            "research": {"scope": "account", "period": "day", "limit": 50},
            "continue": {"scope": "account", "period": "day", "limit": 100},
        },
    }
    for k, v in overrides.items():
        plan, quota = k.split("__")
        base[plan][quota] = v
    return base


def _callback_context(user_id="", *, state=None):
    deltas: dict = {}
    initial = dict(state or {})

    class _State:
        def __setitem__(self, key, value):
            deltas[key] = value

        def get(self, key, default=None):
            return deltas[key] if key in deltas else initial.get(key, default)

    return SimpleNamespace(user_id=user_id, state=_State(), _deltas=deltas)


def _snap(data):
    s = MagicMock()
    s.exists = data is not None
    s.to_dict.return_value = data
    return s


# ── period keys ──────────────────────────────────────────────────────────────


def test_period_key_day():
    assert _period_key("day", _now(2026, 5, 28)) == "2026-05-28"


def test_period_key_month_year():
    assert _period_key("month", _now(2026, 5, 28)) == "2026-05"
    assert _period_key("year", _now(2026, 5, 28)) == "2026"


def test_period_key_ever_is_constant():
    assert _period_key("ever", _now(2026, 5, 28)) == "ever"
    assert _period_key("ever", _now(2030, 1, 1)) == "ever"


def test_period_key_iso_week_resets_monday():
    # 2026-05-24 is a Sunday (ISO week 21), 2026-05-25 is Monday (ISO week 22).
    sunday = _period_key("week", _now(2026, 5, 24))
    monday = _period_key("week", _now(2026, 5, 25))
    assert sunday == "2026-W21"
    assert monday == "2026-W22"
    assert sunday != monday


def test_period_key_unknown_falls_back_to_day():
    assert _period_key("fortnight", _now(2026, 5, 28)) == "2026-05-28"


def test_reset_phrase():
    assert _reset_phrase("day") == "tomorrow"
    assert _reset_phrase("week") == "next week"
    assert _reset_phrase("ever") == ""


# ── spec resolution ──────────────────────────────────────────────────────────


def test_resolve_spec_defaults():
    spec = _resolve_spec(_config(), "free", "research", None)
    assert spec == {"scope": "account", "period": "day", "limit": 1}


def test_resolve_spec_lifetime_continue_per_research():
    cfg = _config(free__continue={"scope": "research", "period": "ever", "limit": 5})
    spec = _resolve_spec(cfg, "free", "continue", None)
    assert spec == {"scope": "research", "period": "ever", "limit": 5}


def test_resolve_spec_research_scope_forced_account():
    # Even if config sets scope=research for research, it's ignored.
    cfg = _config(free__research={"scope": "research", "period": "ever", "limit": 3})
    spec = _resolve_spec(cfg, "free", "research", None)
    assert spec["scope"] == "account"
    assert spec["period"] == "ever"
    assert spec["limit"] == 3


def test_resolve_spec_bad_period_falls_back():
    cfg = _config(free__research={"period": "everr", "limit": 3})
    spec = _resolve_spec(cfg, "free", "research", None)
    assert spec["period"] == "day"  # default
    assert spec["limit"] == 3  # valid limit preserved


def test_resolve_spec_bad_scope_falls_back():
    cfg = _config(free__continue={"scope": "galaxy", "period": "day", "limit": 5})
    spec = _resolve_spec(cfg, "free", "continue", None)
    assert spec["scope"] == "account"


def test_resolve_spec_override_wins():
    spec = _resolve_spec(_config(), "free", "research", {"limitOverrides": {"research": 10}})
    assert spec["limit"] == 10


def test_resolve_spec_bad_override_ignored():
    spec = _resolve_spec(_config(), "free", "research", {"limitOverrides": {"research": -2}})
    assert spec["limit"] == 1


def test_resolve_spec_missing_plan_uses_defaults():
    spec = _resolve_spec({}, "free", "continue", None)
    assert spec == {"scope": "account", "period": "day", "limit": 5}


def test_resolve_spec_malformed_config_nodes_use_defaults():
    spec = _resolve_spec({"free": "oops"}, "free", "continue", None)
    assert spec == {"scope": "account", "period": "day", "limit": 5}

    spec = _resolve_spec({"free": {"continue": ["oops"]}}, "free", "continue", None)
    assert spec == {"scope": "account", "period": "day", "limit": 5}


def test_resolve_spec_malformed_overrides_are_ignored():
    spec = _resolve_spec(_config(), "free", "research", {"limitOverrides": "oops"})
    assert spec["limit"] == 1


# ── reserve transaction ──────────────────────────────────────────────────────


def _reserve_call(user_data, *, quota, count_field, period_field, config=None, session_data=None, has_session=False):
    txn = MagicMock()
    user_ref = MagicMock()
    user_ref.get.return_value = _snap(user_data)
    session_ref = None
    if has_session:
        session_ref = MagicMock()
        session_ref.get.return_value = _snap(session_data)
    reserved, plan, period, scope = _reserve(
        txn, user_ref, session_ref, config or _config(), quota, count_field, period_field, _now()
    )
    return reserved, plan, period, txn, user_ref, session_ref


def test_reserve_research_under_limit_increments_user_doc():
    reserved, _, _, txn, user_ref, _ = _reserve_call(
        {"plan": "free", "researchCount": 0, "researchPeriodKey": "2026-05-28"},
        quota="research", count_field="researchCount", period_field="researchPeriodKey",
    )
    assert reserved is True
    txn.update.assert_called_once()
    ref, payload = txn.update.call_args.args
    assert ref is user_ref
    assert payload["researchCount"] == 1
    assert payload["researchPeriodKey"] == "2026-05-28"


def test_reserve_research_at_limit_blocks():
    reserved, _, _, txn, _, _ = _reserve_call(
        {"plan": "free", "researchCount": 1, "researchPeriodKey": "2026-05-28"},
        quota="research", count_field="researchCount", period_field="researchPeriodKey",
    )
    assert reserved is False
    txn.update.assert_not_called()


def test_reserve_period_rollover_resets():
    reserved, _, _, txn, _, _ = _reserve_call(
        {"plan": "free", "researchCount": 1, "researchPeriodKey": "2026-05-27"},  # yesterday
        quota="research", count_field="researchCount", period_field="researchPeriodKey",
    )
    assert reserved is True
    assert txn.update.call_args.args[1]["researchCount"] == 1  # reset → +1


def test_reserve_continue_account_scope_uses_user_doc():
    reserved, _, _, txn, user_ref, _ = _reserve_call(
        {"plan": "free", "continueCount": 4, "continuePeriodKey": "2026-05-28"},
        quota="continue", count_field="continueCount", period_field="continuePeriodKey",
        has_session=True, session_data=None,
    )
    assert reserved is True  # 5th of 5
    assert txn.update.call_args.args[0] is user_ref  # NOT the session ref


def test_reserve_continue_research_scope_uses_session_subdoc():
    cfg = _config(free__continue={"scope": "research", "period": "ever", "limit": 5})
    reserved, _, period, txn, user_ref, session_ref = _reserve_call(
        {"plan": "free"},  # user doc has no continue counter
        quota="continue", count_field="continueCount", period_field="continuePeriodKey",
        config=cfg, has_session=True, session_data={"continueCount": 2, "continuePeriodKey": "ever"},
    )
    assert reserved is True
    assert period == "ever"
    ref, payload = txn.set.call_args.args if txn.set.called else txn.update.call_args.args
    assert ref is session_ref  # counter lives on the session subdoc
    assert payload["continueCount"] == 3


def test_reserve_continue_research_scope_blocks_at_session_limit():
    cfg = _config(free__continue={"scope": "research", "period": "ever", "limit": 5})
    reserved, _, _, txn, _, _ = _reserve_call(
        {"plan": "free"},
        quota="continue", count_field="continueCount", period_field="continuePeriodKey",
        config=cfg, has_session=True, session_data={"continueCount": 5, "continuePeriodKey": "ever"},
    )
    assert reserved is False


def test_reserve_lazy_provisions_user_doc():
    reserved, _, _, txn, user_ref, _ = _reserve_call(
        None,
        quota="research", count_field="researchCount", period_field="researchPeriodKey",
    )
    assert reserved is True
    ref, payload = txn.set.call_args.args
    assert ref is user_ref
    assert payload["plan"] == "free"
    assert payload["researchCount"] == 1


# ── gates end-to-end ─────────────────────────────────────────────────────────


def _gate_fs(*, config_doc, user_doc, session_doc=None, capture=None):
    fs = MagicMock()
    config_snap = _snap(config_doc)
    user_snap = _snap(user_doc)
    session_snap = _snap(session_doc)

    def collection_router(name):
        col = MagicMock()
        if name == "config":
            col.document.return_value.get.return_value = config_snap
        elif name == "users":
            def doc(uid):
                if capture is not None:
                    capture.append(("user", uid))
                ref = MagicMock()
                ref.get.return_value = user_snap
                return ref
            col.document.side_effect = doc
        elif name == "sessions":
            def sdoc(sid):
                sref = MagicMock()
                quota_col = MagicMock()
                def qdoc(name2):
                    if capture is not None:
                        capture.append(("session", sid))
                    qref = MagicMock()
                    qref.get.return_value = session_snap
                    return qref
                quota_col.document.side_effect = qdoc
                sref.collection.return_value = quota_col
                return sref
            col.document.side_effect = sdoc
        return col

    fs.collection.side_effect = collection_router
    fs.transaction.return_value = MagicMock()
    return fs


def _run(gate, ctx, fs):
    def passthrough(fn):
        def wrap(*a, **k):
            return fn(*a, **k)
        return wrap

    with patch.object(quota_gate, "_client", return_value=fs), patch(
        "google.cloud.firestore.transactional", passthrough
    ):
        # _reserve_txn was wrapped at import time; re-wrap with passthrough.
        with patch.object(quota_gate, "_reserve_txn", quota_gate._reserve):
            return asyncio.run(gate(callback_context=ctx))


def test_gate_anonymous_allowed():
    assert asyncio.run(research_quota_gate(callback_context=_callback_context(""))) is None


def test_research_gate_blocks_at_limit_free_day_message():
    ctx = _callback_context("u1")
    # The gate computes its own `now`, so seed the stored key with today's
    # real day key to guarantee we're in-period (at limit, not rolled over).
    today_key = _period_key("day", datetime.now(timezone.utc))
    fs = _gate_fs(
        config_doc=_config(),
        user_doc={"plan": "free", "researchCount": 1, "researchPeriodKey": today_key},
    )
    out = _run(research_quota_gate, ctx, fs)
    assert out is not None
    assert "research" in out.parts[0].text.lower()
    assert "free plan" in out.parts[0].text.lower()
    assert ctx._deltas[QUOTA_BLOCK_REPLY_KEY] == out.parts[0].text


def test_continue_gate_research_scope_block_message_lifetime():
    cfg = _config(free__continue={"scope": "research", "period": "ever", "limit": 5})
    ctx = _callback_context("u1", state={"firestoreSid": "sid-1"})
    fs = _gate_fs(
        config_doc=cfg,
        user_doc={"plan": "free"},
        session_doc={"continueCount": 5, "continuePeriodKey": "ever"},
    )
    out = _run(continue_quota_gate, ctx, fs)
    assert out is not None
    text = out.parts[0].text.lower()
    assert "follow-up" in text
    assert "for this chat" in text  # research scope → per-chat wording
    assert "tomorrow" not in text  # ever → no reset phrase


def test_continue_gate_account_scope_message_has_no_per_chat_wording():
    # Account-scoped follow-ups (paid) must NOT say "for this chat".
    ctx = _callback_context("u-paid")
    fs = _gate_fs(
        config_doc=_config(),  # paid continue = account/day/100
        user_doc={"plan": "paid", "continueCount": 100, "continuePeriodKey": _period_key("day", datetime.now(timezone.utc))},
    )
    out = _run(continue_quota_gate, ctx, fs)
    assert out is not None
    text = out.parts[0].text.lower()
    assert "for this chat" not in text
    assert "free plan" not in text  # paid


def test_continue_gate_research_scope_targets_session_subdoc():
    cfg = _config(free__continue={"scope": "research", "period": "ever", "limit": 5})
    ctx = _callback_context("u1", state={"firestoreSid": "sid-1"})
    capture: list = []
    fs = _gate_fs(
        config_doc=cfg,
        user_doc={"plan": "free"},
        session_doc={"continueCount": 0, "continuePeriodKey": "ever"},
        capture=capture,
    )
    assert _run(continue_quota_gate, ctx, fs) is None  # under limit
    assert ("session", "sid-1") in capture


def test_continue_gate_missing_sid_falls_back_to_account():
    cfg = _config(free__continue={"scope": "research", "period": "ever", "limit": 5})
    ctx = _callback_context("u1")  # no firestoreSid
    fs = _gate_fs(config_doc=cfg, user_doc={"plan": "free"})
    # scope=research but no sid → session_quota_ref is None → account fallback,
    # uses user-doc counter (0 < 5) → allowed.
    assert _run(continue_quota_gate, ctx, fs) is None


def test_gate_prefers_quotaUid_over_user_id():
    ctx = _callback_context("creator", state={"quotaUid": "submitter"})
    capture: list = []
    fs = _gate_fs(config_doc=_config(), user_doc={"plan": "free"}, capture=capture)
    _run(research_quota_gate, ctx, fs)
    assert ("user", "submitter") in capture
    assert ("user", "creator") not in capture


def test_gate_fails_open_on_error():
    ctx = _callback_context("u-err")
    fs = MagicMock()
    fs.collection.side_effect = RuntimeError("boom")
    with patch.object(quota_gate, "_client", return_value=fs):
        assert asyncio.run(continue_quota_gate(callback_context=ctx)) is None
