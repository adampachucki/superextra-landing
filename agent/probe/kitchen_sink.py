"""Round-2 kitchen-sink probe agent.

Bundles the tools needed to verify R2.1 (outbound HTTP), R2.2 (env vars +
SecretRef), R2.3 (multi-turn state), R2.6 (logs visibility) in one deploy.
"""

from __future__ import annotations

import logging
import os
import sys
import urllib.request

from google.adk.agents import LlmAgent
from google.adk.apps import App

from .probe_plugin import ProbePlugin

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")

# R2.6 — logs visibility. Use stdlib logging plus stdout/stderr prints.
log = logging.getLogger("probe_kitchen")


def fetch_external_url(url: str) -> dict:
    """R2.1: hit an external URL from inside the deployed runtime.

    Returns status code + first 200 chars of body. We use urllib instead of
    requests to avoid extra dep. Failures surface as Python exceptions →
    Agent Runtime maps to tool-error event."""
    print(f"[probe_tool] PROBE_STDOUT_MARKER fetch_external_url url={url}", file=sys.stdout, flush=True)
    print(f"[probe_tool] PROBE_STDERR_MARKER fetch_external_url url={url}", file=sys.stderr, flush=True)
    log.info("PROBE_LOGGING_MARKER fetch_external_url url=%s", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "superextra-probe/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read(200).decode("utf-8", errors="replace")
            return {"status": resp.status, "body_preview": body, "ok": True}
    except Exception as e:
        return {"status": None, "error": f"{type(e).__name__}: {str(e)[:300]}", "ok": False}


def read_env(name: str) -> dict:
    """R2.2: read an env var (plain or SecretRef-injected)."""
    val = os.environ.get(name)
    return {"name": name, "value": val, "present": val is not None}


def write_state_marker(key: str, value: str) -> dict:
    """R2.3: write to session.state via tool. Tool-context state writes
    flow through to ADK's state_delta, then into the session. Whether
    they survive across stream_query invocations is what we're testing."""
    print(f"[probe_tool] write_state_marker key={key} value={value}", file=sys.stdout, flush=True)
    return {"set": True, "key": key, "value": value}


# Single root LlmAgent that exposes all tools. Instructions deliberately
# direct so the LLM is predictable.
kitchen_root = LlmAgent(
    name="probe_kitchen",
    model="gemini-2.5-flash",
    instruction=(
        "You are a probe agent. Follow instructions exactly. "
        "You have four tools: fetch_external_url, read_env, write_state_marker. "
        "Call only the tools the user asks for. If the user message is 'turn1', "
        "call write_state_marker(key='turn1_marker', value='set_in_turn1') and "
        "respond 'turn1_done'. If the user message is 'turn2', "
        "call read_env(name='_PROBE_STATE_CHECK') (don't worry if it returns None) "
        "and respond 'turn2_done'. "
        "If the user message starts with 'fetch:', extract the URL after 'fetch:' "
        "and call fetch_external_url with that URL exactly. "
        "If the user message starts with 'env:', extract the env-var name and call read_env."
    ),
    tools=[fetch_external_url, read_env, write_state_marker],
)


def make_kitchen_app() -> App:
    return App(
        name="superextra_probe_kitchen",
        root_agent=kitchen_root,
        plugins=[ProbePlugin(project=PROJECT)],
    )
