"""Unit tests for `superextra_agent.secrets.get_secret`.

Covers the three runtime contracts called out in plan §Phase 3:
  1. env-set: returns env value, never reaches Secret Manager
  2. env-unset: hits Secret Manager exactly once
  3. cached: a second call with the same name does not re-call SM

Plus the failure path: when env is empty AND Secret Manager raises,
``get_secret`` wraps the underlying exception in ``RuntimeError`` whose
message includes the secret name (existing tool callers rely on the
substring contract).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from superextra_agent import secrets


@pytest.fixture(autouse=True)
def _reset_secrets_cache():
    """Clear lru_cache + reset the lazy SM client between tests."""
    secrets.get_secret.cache_clear()
    secrets._client = None
    yield
    secrets.get_secret.cache_clear()
    secrets._client = None


def _mock_sm_response(value: str) -> MagicMock:
    resp = MagicMock()
    resp.payload.data = value.encode("utf-8")
    return resp


def test_env_set_returns_env_value(monkeypatch):
    """env hit: returns env value without touching Secret Manager."""
    monkeypatch.setenv("APIFY_TOKEN", "from-env")
    fake_client = MagicMock()
    with patch.object(secrets, "_get_client", return_value=fake_client) as get_client:
        out = secrets.get_secret("APIFY_TOKEN")

    assert out == "from-env"
    assert get_client.call_count == 0
    assert fake_client.access_secret_version.call_count == 0


def test_env_unset_hits_secret_manager_once(monkeypatch):
    """env miss: falls through to Secret Manager exactly once."""
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    fake_client = MagicMock()
    fake_client.access_secret_version.return_value = _mock_sm_response("from-sm")

    with patch.object(secrets, "_get_client", return_value=fake_client):
        out = secrets.get_secret("APIFY_TOKEN")

    assert out == "from-sm"
    assert fake_client.access_secret_version.call_count == 1
    # Verify the version path is constructed correctly
    call_kwargs = fake_client.access_secret_version.call_args.kwargs
    assert (
        call_kwargs["name"]
        == f"projects/{secrets.PROJECT}/secrets/APIFY_TOKEN/versions/latest"
    )


def test_second_call_is_cached(monkeypatch):
    """Two calls with the same name produce one Secret Manager call."""
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    fake_client = MagicMock()
    fake_client.access_secret_version.return_value = _mock_sm_response("cached-value")

    with patch.object(secrets, "_get_client", return_value=fake_client):
        a = secrets.get_secret("APIFY_TOKEN")
        b = secrets.get_secret("APIFY_TOKEN")

    assert a == b == "cached-value"
    assert fake_client.access_secret_version.call_count == 1


def test_secret_manager_failure_wraps_runtime_error(monkeypatch):
    """env empty + SM raises: RuntimeError carries the secret name."""
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    fake_client = MagicMock()
    fake_client.access_secret_version.side_effect = RuntimeError("permission denied")

    with patch.object(secrets, "_get_client", return_value=fake_client):
        with pytest.raises(RuntimeError) as ei:
            secrets.get_secret("APIFY_TOKEN")

    assert "APIFY_TOKEN" in str(ei.value)


def test_empty_env_value_falls_through_to_sm(monkeypatch):
    """env set to empty string is treated as missing — empty isn't a secret."""
    monkeypatch.setenv("APIFY_TOKEN", "")
    fake_client = MagicMock()
    fake_client.access_secret_version.return_value = _mock_sm_response("from-sm")

    with patch.object(secrets, "_get_client", return_value=fake_client):
        out = secrets.get_secret("APIFY_TOKEN")

    assert out == "from-sm"
    assert fake_client.access_secret_version.call_count == 1
