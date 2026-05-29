import os

# Set env vars BEFORE importing agent modules
os.environ.setdefault("GOOGLE_PLACES_API_KEY", "test-key")
os.environ.setdefault("APIFY_TOKEN", "test-key")
os.environ.setdefault("SERPAPI_API_KEY", "test-key")
os.environ.setdefault("GEMINI_VERSION", "3.1")

import pytest


@pytest.fixture(autouse=True)
def reset_places_client():
    """Reset the lazy-initialized httpx client between tests."""
    from superextra_agent import places_tools

    places_tools._client = None
    yield
    places_tools._client = None


@pytest.fixture(autouse=True)
def reset_secrets_cache():
    """Clear get_secret's lru_cache between tests so tests that
    monkeypatch env vars don't see stale resolutions from earlier runs.
    Also resets the lazy Secret Manager client."""
    from superextra_agent import secrets

    secrets.get_secret.cache_clear()
    secrets._client = None
    yield
    secrets.get_secret.cache_clear()
    secrets._client = None
