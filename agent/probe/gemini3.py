"""Round-2 R2.4 — Gemini 3.1 routing via lazy-init Gemini subclass.

Production's pattern in `_make_gemini(force_global=True)` builds a live
`genai.Client(location='global')` at LlmAgent construction time and
attaches it as `gemini.api_client`. Cloudpickle can't serialize the live
Client (holds a `_thread.lock`), so deploy fails — see [adk-python#3628].

Workaround: a Gemini subclass that constructs the Client lazily on first
access. Pickle-safe because no live client exists at pickle time.
"""

from __future__ import annotations

import os
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.models.google_llm import Gemini
from google.genai import Client, types

from .probe_plugin import ProbePlugin

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")

RETRY = types.HttpRetryOptions(attempts=3, initial_delay=2.0, max_delay=10.0)


class GeminiGlobalEndpoint(Gemini):
    """Gemini variant whose api_client is constructed lazily, with
    `location='global'`. Pickle-safe because the live client never
    exists at pickle time — only the model name + retry config are
    serialized."""

    @property
    def api_client(self) -> Client:  # type: ignore[override]
        # Cache on instance dict so subsequent reads don't re-create
        client = self.__dict__.get("_lazy_global_client")
        if client is not None:
            return client
        client = Client(
            vertexai=True,
            location="global",
            http_options=types.HttpOptions(retry_options=RETRY),
        )
        self.__dict__["_lazy_global_client"] = client
        return client

    @api_client.setter
    def api_client(self, value: Any) -> None:
        # ADK occasionally tries to set this; honor it but the lazy
        # path will rebuild on next access if cleared.
        self.__dict__["_lazy_global_client"] = value


gemini3_root = LlmAgent(
    name="probe_gemini3",
    # Match production: `gemini-3.1-pro-preview` is the actual ID we use.
    model=GeminiGlobalEndpoint(model="gemini-3.1-pro-preview", retry_options=RETRY),
    instruction="You are a probe agent. Reply with 'ok-from-gemini-3.1' and nothing else.",
)


def make_gemini3_app() -> App:
    return App(
        name="superextra_probe_gemini3",
        root_agent=gemini3_root,
        plugins=[ProbePlugin(project=PROJECT)],
    )
