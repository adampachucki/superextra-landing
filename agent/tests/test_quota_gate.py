"""Tests for the research-pipeline quota gate.

The gate is the single enforcement point for daily research-runs limits.
These tests cover: allow under limit, block at limit, day rollover reset,
plan-based limit selection, transactional check + reserve.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from google.cloud import firestore

from superextra_agent import quota_gate
from superextra_agent.quota_gate import (
    QUOTA_BLOCK_REPLY_KEY,
    _check_and_reserve,
    _research_limits,
    _resolve_limit,
    _today_utc,
    research_quota_gate,
)


@pytest.fixture(autouse=True)
def _reset_module_caches():
    """Reset module-level Firestore client + config cache between tests."""
    quota_gate._fs = None
    quota_gate._config_cache = None
    quota_gate._config_cached_at = 0.0
    yield
    quota_gate._fs = None
    quota_gate._config_cache = None
    quota_gate._config_cached_at = 0.0


def _callback_context(user_id: str = "", *, state: dict | None = None):
    """Minimal CallbackContext stand-in. `state` seeds the initial dict;
    `_deltas` captures writes during the test."""
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


def test_resolve_limit_uses_plan_default():
    assert _resolve_limit({"plan": "free"}, {"free": 1, "paid": 50}) == 1
    assert _resolve_limit({"plan": "paid"}, {"free": 1, "paid": 50}) == 50
    assert _resolve_limit(None, {"free": 1, "paid": 50}) == 1


def test_resolve_limit_honors_per_user_override():
    user = {"plan": "free", "limitOverrides": {"researchPerDay": 10}}
    assert _resolve_limit(user, {"free": 1, "paid": 50}) == 10


def test_resolve_limit_rejects_bad_override():
    user = {"plan": "free", "limitOverrides": {"researchPerDay": -5}}
    assert _resolve_limit(user, {"free": 1, "paid": 50}) == 1
    user = {"plan": "free", "limitOverrides": {"researchPerDay": "ten"}}
    assert _resolve_limit(user, {"free": 1, "paid": 50}) == 1


def test_research_limits_reads_config_doc():
    fs = MagicMock()
    snap = MagicMock()
    snap.exists = True
    snap.to_dict.return_value = {
        "free": {"researchPerDay": 3},
        "paid": {"researchPerDay": 99},
    }
    fs.collection.return_value.document.return_value.get.return_value = snap

    limits = _research_limits(fs)
    assert limits == {"free": 3, "paid": 99}


def test_research_limits_falls_back_when_doc_missing():
    fs = MagicMock()
    snap = MagicMock()
    snap.exists = False
    fs.collection.return_value.document.return_value.get.return_value = snap

    limits = _research_limits(fs)
    assert limits == {"free": 1, "paid": 50}


def test_research_limits_clamps_bad_values():
    fs = MagicMock()
    snap = MagicMock()
    snap.exists = True
    snap.to_dict.return_value = {
        "free": {"researchPerDay": -1},
        "paid": {"researchPerDay": "many"},
    }
    fs.collection.return_value.document.return_value.get.return_value = snap

    limits = _research_limits(fs)
    assert limits == {"free": 1, "paid": 50}


def test_check_and_reserve_under_limit_increments():
    txn = MagicMock()
    user_ref = MagicMock()
    user_ref.get.return_value = _user_snap({
        "plan": "free",
        "researchRunsToday": 0,
        "lastResearchDateUtc": _today_utc(),
    })

    allowed, limit = _check_and_reserve(txn, user_ref, _today_utc(), {"free": 1, "paid": 50})
    assert allowed is True
    assert limit == 1
    user_ref.get.assert_called_once_with(transaction=txn)
    txn.update.assert_called_once()
    update_args = txn.update.call_args.args[1]
    assert update_args["researchRunsToday"] == 1
    assert update_args["lastResearchDateUtc"] == _today_utc()


def test_check_and_reserve_at_limit_blocks():
    txn = MagicMock()
    user_ref = MagicMock()
    user_ref.get.return_value = _user_snap({
        "plan": "free",
        "researchRunsToday": 1,
        "lastResearchDateUtc": _today_utc(),
    })

    allowed, limit = _check_and_reserve(txn, user_ref, _today_utc(), {"free": 1, "paid": 50})
    assert allowed is False
    assert limit == 1
    txn.update.assert_not_called()


def test_check_and_reserve_day_rollover_resets_counter():
    txn = MagicMock()
    user_ref = MagicMock()
    user_ref.get.return_value = _user_snap({
        "plan": "free",
        "researchRunsToday": 1,
        "lastResearchDateUtc": "2020-01-01",  # old day
    })

    allowed, limit = _check_and_reserve(txn, user_ref, _today_utc(), {"free": 1, "paid": 50})
    assert allowed is True
    assert limit == 1
    txn.update.assert_called_once()
    update_args = txn.update.call_args.args[1]
    assert update_args["researchRunsToday"] == 1  # reset → +1


def test_check_and_reserve_lazy_provisions_missing_user_doc():
    txn = MagicMock()
    user_ref = MagicMock()
    user_ref.get.return_value = _user_snap(None)

    allowed, _ = _check_and_reserve(txn, user_ref, _today_utc(), {"free": 1, "paid": 50})
    assert allowed is True
    txn.set.assert_called_once()
    set_args = txn.set.call_args.args[1]
    assert set_args["plan"] == "free"
    assert set_args["researchRunsToday"] == 1


def test_gate_returns_none_for_anonymous_user():
    ctx = _callback_context("")
    out = asyncio.run(research_quota_gate(callback_context=ctx))
    assert out is None


def test_gate_prefers_quotaUid_over_user_id():
    """Shared-URL submitter: `quotaUid` in session state must be charged,
    not the engine session's creator `user_id`."""
    ctx = _callback_context("creator-uid", state={"quotaUid": "submitter-uid"})

    fake_fs = MagicMock()
    config_snap = MagicMock()
    config_snap.exists = True
    config_snap.to_dict.return_value = {"free": {"researchPerDay": 1}, "paid": {"researchPerDay": 50}}
    user_snap = _user_snap({
        "plan": "free",
        "researchRunsToday": 0,
        "lastResearchDateUtc": _today_utc(),
    })
    submitter_doc_calls: list[str] = []

    def collection_router(name: str):
        col = MagicMock()
        if name == "config":
            col.document.return_value.get.return_value = config_snap
        elif name == "users":
            def doc(uid):
                submitter_doc_calls.append(uid)
                user_ref = MagicMock()
                user_ref.get.return_value = user_snap
                return user_ref
            col.document.side_effect = doc
        return col

    fake_fs.collection.side_effect = collection_router
    fake_fs.transaction.return_value = MagicMock()

    def passthrough_transactional(fn):
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper

    with patch.object(quota_gate, "_client", return_value=fake_fs), patch(
        "google.cloud.firestore.transactional", passthrough_transactional
    ):
        asyncio.run(research_quota_gate(callback_context=ctx))

    # Must have charged the submitter's doc, not the creator's.
    assert submitter_doc_calls == ["submitter-uid"], submitter_doc_calls


def test_gate_returns_none_when_under_limit():
    ctx = _callback_context("uid-allowed")

    fake_fs = MagicMock()
    # _research_limits path
    config_snap = MagicMock()
    config_snap.exists = True
    config_snap.to_dict.return_value = {"free": {"researchPerDay": 1}, "paid": {"researchPerDay": 50}}
    # _check_and_reserve path
    user_snap = _user_snap({
        "plan": "free",
        "researchRunsToday": 0,
        "lastResearchDateUtc": _today_utc(),
    })

    def collection_router(name: str):
        col = MagicMock()
        if name == "config":
            col.document.return_value.get.return_value = config_snap
        elif name == "users":
            user_ref = MagicMock()
            user_ref.get.return_value = user_snap
            col.document.return_value = user_ref
        return col

    fake_fs.collection.side_effect = collection_router
    fake_fs.transaction.return_value = MagicMock()

    # Skip real firestore.transactional by patching it to call the inner fn directly.
    def passthrough_transactional(fn):
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper

    with patch.object(quota_gate, "_client", return_value=fake_fs), patch(
        "google.cloud.firestore.transactional", passthrough_transactional
    ):
        out = asyncio.run(research_quota_gate(callback_context=ctx))

    assert out is None
    assert ctx._deltas == {}


def _make_block_fs(plan: str, limits: dict[str, int]):
    """Build a fake firestore.Client where the user is already AT the limit
    for the given plan."""
    fake_fs = MagicMock()
    config_snap = MagicMock()
    config_snap.exists = True
    config_snap.to_dict.return_value = {
        "free": {"researchPerDay": limits["free"]},
        "paid": {"researchPerDay": limits["paid"]},
    }
    used = limits[plan]
    user_snap = _user_snap({
        "plan": plan,
        "researchRunsToday": used,
        "lastResearchDateUtc": _today_utc(),
    })

    def collection_router(name: str):
        col = MagicMock()
        if name == "config":
            col.document.return_value.get.return_value = config_snap
        elif name == "users":
            user_ref = MagicMock()
            user_ref.get.return_value = user_snap
            col.document.return_value = user_ref
        return col

    fake_fs.collection.side_effect = collection_router
    fake_fs.transaction.return_value = MagicMock()
    return fake_fs


def _passthrough_transactional(fn):
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    return wrapper


def test_gate_blocks_with_free_message_at_limit():
    ctx = _callback_context("uid-blocked")
    fake_fs = _make_block_fs("free", {"free": 1, "paid": 50})

    with patch.object(quota_gate, "_client", return_value=fake_fs), patch(
        "google.cloud.firestore.transactional", _passthrough_transactional
    ):
        out = asyncio.run(research_quota_gate(callback_context=ctx))

    assert out is not None
    text = out.parts[0].text
    assert "free plan" in text.lower()
    assert "tomorrow" in text.lower()
    assert ctx._deltas[QUOTA_BLOCK_REPLY_KEY] == text


def test_gate_blocks_paid_plan_with_plan_neutral_message():
    """Paid users hitting their limit get a different message (no 'free
    plan' wording — that would be misleading)."""
    ctx = _callback_context("uid-paid-blocked")
    fake_fs = _make_block_fs("paid", {"free": 1, "paid": 1})

    with patch.object(quota_gate, "_client", return_value=fake_fs), patch(
        "google.cloud.firestore.transactional", _passthrough_transactional
    ):
        out = asyncio.run(research_quota_gate(callback_context=ctx))

    assert out is not None
    text = out.parts[0].text
    assert "free plan" not in text.lower()
    assert "tomorrow" in text.lower()
    assert ctx._deltas[QUOTA_BLOCK_REPLY_KEY] == text


def test_gate_fails_open_on_firestore_error():
    """Firestore outage must not block the user — quota is a fairness control,
    not a security boundary."""
    ctx = _callback_context("uid-fs-error")

    fake_fs = MagicMock()
    # collection().document() builds local refs and won't throw; the failure
    # mode we care about is reads/transactions blowing up under load.
    config_doc = MagicMock()
    config_doc.get.side_effect = RuntimeError("simulated firestore outage")
    user_ref = MagicMock()

    def collection_router(name: str):
        col = MagicMock()
        if name == "config":
            col.document.return_value = config_doc
        elif name == "users":
            col.document.return_value = user_ref
        return col

    fake_fs.collection.side_effect = collection_router

    with patch.object(quota_gate, "_client", return_value=fake_fs):
        out = asyncio.run(research_quota_gate(callback_context=ctx))

    assert out is None
