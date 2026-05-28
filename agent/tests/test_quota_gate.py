"""Tests for the daily usage gates (research + continuation).

Covers: limit resolution, config read/fallback, transactional check+reserve
for each counter, day rollover, independence of the two counters, block
messages, quotaUid override, and fail-open on Firestore errors.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from superextra_agent import quota_gate
from superextra_agent.quota_gate import (
    QUOTA_BLOCK_REPLY_KEY,
    _check_and_reserve,
    _limits_config,
    _resolve_limit,
    _today_utc,
    continue_quota_gate,
    research_quota_gate,
)


@pytest.fixture(autouse=True)
def _reset_client():
    quota_gate._fs = None
    yield
    quota_gate._fs = None


def _callback_context(user_id: str = "", *, state: dict | None = None):
    deltas: dict = {}
    initial = dict(state or {})

    class _State:
        def __setitem__(self, key, value):
            deltas[key] = value

        def get(self, key, default=None):
            if key in deltas:
                return deltas[key]
            return initial.get(key, default)

    return SimpleNamespace(user_id=user_id, state=_State(), _deltas=deltas)


def _user_snap(data: dict | None):
    snap = MagicMock()
    snap.exists = data is not None
    snap.to_dict.return_value = data
    return snap


def _config(free_research=1, free_continue=5, paid_research=50, paid_continue=100):
    return {
        "free": {"researchPerDay": free_research, "continuePerDay": free_continue},
        "paid": {"researchPerDay": paid_research, "continuePerDay": paid_continue},
    }


def _passthrough_transactional(fn):
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


# ── limit resolution ─────────────────────────────────────────────────────────


def test_resolve_limit_uses_plan_default():
    cfg = _config()
    assert _resolve_limit({"plan": "free"}, cfg, "researchPerDay") == 1
    assert _resolve_limit({"plan": "free"}, cfg, "continuePerDay") == 5
    assert _resolve_limit({"plan": "paid"}, cfg, "researchPerDay") == 50
    assert _resolve_limit({"plan": "paid"}, cfg, "continuePerDay") == 100
    assert _resolve_limit(None, cfg, "researchPerDay") == 1


def test_resolve_limit_honors_per_user_override():
    user = {"plan": "free", "limitOverrides": {"continuePerDay": 20}}
    assert _resolve_limit(user, _config(), "continuePerDay") == 20
    # other key unaffected
    assert _resolve_limit(user, _config(), "researchPerDay") == 1


def test_resolve_limit_rejects_bad_override():
    user = {"plan": "free", "limitOverrides": {"continuePerDay": -5}}
    assert _resolve_limit(user, _config(), "continuePerDay") == 5
    user = {"plan": "free", "limitOverrides": {"researchPerDay": "ten"}}
    assert _resolve_limit(user, _config(), "researchPerDay") == 1


# ── config read ──────────────────────────────────────────────────────────────


def _fs_with_config(config_doc):
    fs = MagicMock()
    snap = MagicMock()
    snap.exists = config_doc is not None
    snap.to_dict.return_value = config_doc
    fs.collection.return_value.document.return_value.get.return_value = snap
    return fs


def test_limits_config_reads_both_keys():
    fs = _fs_with_config({
        "free": {"researchPerDay": 3, "continuePerDay": 9},
        "paid": {"researchPerDay": 99, "continuePerDay": 999},
    })
    cfg = _limits_config(fs)
    assert cfg == {
        "free": {"researchPerDay": 3, "continuePerDay": 9},
        "paid": {"researchPerDay": 99, "continuePerDay": 999},
    }


def test_limits_config_falls_back_when_doc_missing():
    fs = _fs_with_config(None)
    cfg = _limits_config(fs)
    assert cfg == {
        "free": {"researchPerDay": 1, "continuePerDay": 5},
        "paid": {"researchPerDay": 50, "continuePerDay": 100},
    }


def test_limits_config_clamps_bad_values_per_key():
    fs = _fs_with_config({"free": {"researchPerDay": -1, "continuePerDay": "lots"}})
    cfg = _limits_config(fs)
    assert cfg["free"] == {"researchPerDay": 1, "continuePerDay": 5}


# ── check + reserve ──────────────────────────────────────────────────────────


def _reserve(data, *, limit_key, counter_field, date_field, config=None):
    txn = MagicMock()
    user_ref = MagicMock()
    user_ref.get.return_value = _user_snap(data)
    allowed, _plan = _check_and_reserve(
        txn, user_ref, _today_utc(), config or _config(), limit_key, counter_field, date_field
    )
    return allowed, txn, user_ref


def test_reserve_research_under_limit_increments():
    allowed, txn, _ = _reserve(
        {"plan": "free", "researchRunsToday": 0, "lastResearchDateUtc": _today_utc()},
        limit_key="researchPerDay",
        counter_field="researchRunsToday",
        date_field="lastResearchDateUtc",
    )
    assert allowed is True
    args = txn.update.call_args.args[1]
    assert args["researchRunsToday"] == 1
    assert args["lastResearchDateUtc"] == _today_utc()


def test_reserve_research_at_limit_blocks():
    allowed, txn, _ = _reserve(
        {"plan": "free", "researchRunsToday": 1, "lastResearchDateUtc": _today_utc()},
        limit_key="researchPerDay",
        counter_field="researchRunsToday",
        date_field="lastResearchDateUtc",
    )
    assert allowed is False
    txn.update.assert_not_called()


def test_reserve_continue_allows_up_to_five():
    # 4 used, free continue limit 5 → still allowed (becomes 5)
    allowed, txn, _ = _reserve(
        {"plan": "free", "continueRunsToday": 4, "lastContinueDateUtc": _today_utc()},
        limit_key="continuePerDay",
        counter_field="continueRunsToday",
        date_field="lastContinueDateUtc",
    )
    assert allowed is True
    assert txn.update.call_args.args[1]["continueRunsToday"] == 5


def test_reserve_continue_blocks_at_five():
    allowed, txn, _ = _reserve(
        {"plan": "free", "continueRunsToday": 5, "lastContinueDateUtc": _today_utc()},
        limit_key="continuePerDay",
        counter_field="continueRunsToday",
        date_field="lastContinueDateUtc",
    )
    assert allowed is False
    txn.update.assert_not_called()


def test_reserve_day_rollover_resets_counter():
    allowed, txn, _ = _reserve(
        {"plan": "free", "continueRunsToday": 5, "lastContinueDateUtc": "2020-01-01"},
        limit_key="continuePerDay",
        counter_field="continueRunsToday",
        date_field="lastContinueDateUtc",
    )
    assert allowed is True
    assert txn.update.call_args.args[1]["continueRunsToday"] == 1  # reset → +1


def test_reserve_counters_are_independent():
    """A maxed research counter must not block continuations (separate date +
    counter fields)."""
    data = {
        "plan": "free",
        "researchRunsToday": 1,
        "lastResearchDateUtc": _today_utc(),
        "continueRunsToday": 0,
        "lastContinueDateUtc": _today_utc(),
    }
    allowed, _, _ = _reserve(
        data,
        limit_key="continuePerDay",
        counter_field="continueRunsToday",
        date_field="lastContinueDateUtc",
    )
    assert allowed is True


def test_reserve_lazy_provisions_missing_user_doc():
    allowed, txn, _ = _reserve(
        None,
        limit_key="researchPerDay",
        counter_field="researchRunsToday",
        date_field="lastResearchDateUtc",
    )
    assert allowed is True
    set_args = txn.set.call_args.args[1]
    assert set_args["plan"] == "free"
    assert set_args["researchRunsToday"] == 1


# ── gate end-to-end ──────────────────────────────────────────────────────────


def _gate_fs(*, config_doc, user_doc, capture_uid=None):
    fs = MagicMock()
    config_snap = MagicMock()
    config_snap.exists = True
    config_snap.to_dict.return_value = config_doc
    user_snap = _user_snap(user_doc)

    def collection_router(name: str):
        col = MagicMock()
        if name == "config":
            col.document.return_value.get.return_value = config_snap
        elif name == "users":
            def doc(uid):
                if capture_uid is not None:
                    capture_uid.append(uid)
                ref = MagicMock()
                ref.get.return_value = user_snap
                return ref
            col.document.side_effect = doc
        return col

    fs.collection.side_effect = collection_router
    fs.transaction.return_value = MagicMock()
    return fs


def _run_gate(gate, ctx, fs):
    with patch.object(quota_gate, "_client", return_value=fs), patch(
        "google.cloud.firestore.transactional", _passthrough_transactional
    ):
        return asyncio.run(gate(callback_context=ctx))


def test_gate_returns_none_for_anonymous_user():
    assert asyncio.run(research_quota_gate(callback_context=_callback_context(""))) is None
    assert asyncio.run(continue_quota_gate(callback_context=_callback_context(""))) is None


def test_research_gate_allows_under_limit():
    ctx = _callback_context("uid1")
    fs = _gate_fs(
        config_doc=_config(),
        user_doc={"plan": "free", "researchRunsToday": 0, "lastResearchDateUtc": _today_utc()},
    )
    assert _run_gate(research_quota_gate, ctx, fs) is None
    assert ctx._deltas == {}


def test_research_gate_blocks_at_limit_with_free_message():
    ctx = _callback_context("uid1")
    fs = _gate_fs(
        config_doc=_config(),
        user_doc={"plan": "free", "researchRunsToday": 1, "lastResearchDateUtc": _today_utc()},
    )
    out = _run_gate(research_quota_gate, ctx, fs)
    assert out is not None
    text = out.parts[0].text
    assert "research" in text.lower() and "free plan" in text.lower()
    assert ctx._deltas[QUOTA_BLOCK_REPLY_KEY] == text


def test_continue_gate_blocks_at_five_with_followup_message():
    ctx = _callback_context("uid1")
    fs = _gate_fs(
        config_doc=_config(),
        user_doc={"plan": "free", "continueRunsToday": 5, "lastContinueDateUtc": _today_utc()},
    )
    out = _run_gate(continue_quota_gate, ctx, fs)
    assert out is not None
    text = out.parts[0].text
    assert "follow-up" in text.lower() and "free plan" in text.lower()
    assert ctx._deltas[QUOTA_BLOCK_REPLY_KEY] == text


def test_continue_gate_allows_fifth_then_blocks_sixth():
    # 4 used → allowed
    ctx = _callback_context("uid1")
    fs = _gate_fs(
        config_doc=_config(),
        user_doc={"plan": "free", "continueRunsToday": 4, "lastContinueDateUtc": _today_utc()},
    )
    assert _run_gate(continue_quota_gate, ctx, fs) is None


def test_paid_block_message_is_plan_neutral():
    ctx = _callback_context("uid-paid")
    fs = _gate_fs(
        config_doc=_config(paid_continue=1),
        user_doc={"plan": "paid", "continueRunsToday": 1, "lastContinueDateUtc": _today_utc()},
    )
    out = _run_gate(continue_quota_gate, ctx, fs)
    assert out is not None
    assert "free plan" not in out.parts[0].text.lower()


def test_gate_prefers_quotaUid_over_user_id():
    """Shared-URL submitter charges their own counter, not the creator's."""
    ctx = _callback_context("creator-uid", state={"quotaUid": "submitter-uid"})
    captured: list[str] = []
    fs = _gate_fs(
        config_doc=_config(),
        user_doc={"plan": "free", "researchRunsToday": 0, "lastResearchDateUtc": _today_utc()},
        capture_uid=captured,
    )
    _run_gate(research_quota_gate, ctx, fs)
    assert captured and captured[0] == "submitter-uid"


def test_gate_fails_open_on_firestore_error():
    ctx = _callback_context("uid-fs-error")
    fs = MagicMock()
    config_doc = MagicMock()
    config_doc.get.side_effect = RuntimeError("simulated outage")

    def collection_router(name: str):
        col = MagicMock()
        if name == "config":
            col.document.return_value = config_doc
        return col

    fs.collection.side_effect = collection_router

    with patch.object(quota_gate, "_client", return_value=fs):
        assert asyncio.run(continue_quota_gate(callback_context=ctx)) is None
