import os

# Set env vars BEFORE importing agent modules
os.environ.setdefault("GOOGLE_PLACES_API_KEY", "test-key")
os.environ.setdefault("GEMINI_VERSION", "3.1")

import pytest


@pytest.fixture(autouse=True)
def reset_places_client():
    """Reset the lazy-initialized httpx client between tests."""
    from superextra_agent import places_tools

    places_tools._client = None
    yield
    places_tools._client = None
