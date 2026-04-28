"""Runtime secret resolution: env first, Secret Manager fallback.

Vertex AI Agent Engine reserves env-var space, so the agent can't get
secrets through env vars at runtime. The Reasoning Engine SA
(`service-907466498524@gcp-sa-aiplatform-re...`) has
`secretmanager.secretAccessor` granted, so this module reads
`APIFY_TOKEN`, `GOOGLE_PLACES_API_KEY`, `SERPAPI_API_KEY` from Secret
Manager when the env var is missing.

Local dev and CI use env vars (from `agent/.env` or GHA secrets); the
env-first ordering means dev iterates without touching Secret Manager.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from google.cloud import secretmanager

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")

_client: Optional[secretmanager.SecretManagerServiceClient] = None


def _get_client() -> secretmanager.SecretManagerServiceClient:
    global _client
    if _client is None:
        _client = secretmanager.SecretManagerServiceClient()
    return _client


@lru_cache(maxsize=32)
def get_secret(name: str) -> str:
    """Resolve a secret by name. Env var first, Secret Manager fallback.

    Cached for the process lifetime — call ``get_secret.cache_clear()`` in
    tests that need fresh resolution. Tests that delete the env var must
    also mock ``_get_client`` (or the underlying ``access_secret_version``)
    to avoid reaching production Secret Manager.

    Raises:
        RuntimeError: if neither env nor Secret Manager produces a value.
            The message contains the secret name so existing tool error
            paths (e.g. ``apify_tools._get_api_key``) keep their substring
            contract.
    """
    val = os.environ.get(name)
    if val:
        return val
    try:
        resp = _get_client().access_secret_version(
            name=f"projects/{PROJECT}/secrets/{name}/versions/latest"
        )
    except Exception as e:
        raise RuntimeError(
            f"{name} not in env and Secret Manager fetch failed: {e}"
        ) from e
    return resp.payload.data.decode("utf-8")
