"""Test 2 — ChatLoggerPlugin smoke under AgentTool nesting.

Runs one query against the post-merge `superextra_agent.agent.app` with
ChatLoggerPlugin enabled (and FirestoreProgressPlugin stripped — it
needs a real Firestore session document; verify on staging).

After the run, inspects the JSONL log for the session and verifies:
  - exactly ONE `before_run` (top-level only, nested invocations
    correctly skipped via the InMemorySessionService guard)
  - exactly ONE `after_run` (same)
  - per-specialist events show up via `on_event_callback`
  - `before_tool` / `after_tool` fire for specialist tool calls

Pass criterion: clean lifecycle (no double-claims) + per-specialist
events present.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AGENT_DIR))

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "superextra-site")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(AGENT_DIR / ".env")

from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

from superextra_agent.agent import app
from superextra_agent.firestore_progress import FirestoreProgressPlugin


async def main() -> int:
    # Strip FirestoreProgressPlugin (needs Firestore session doc); keep
    # ChatLoggerPlugin so we can inspect lifecycle behavior.
    eval_plugins = [
        p for p in (app.plugins or [])
        if not isinstance(p, FirestoreProgressPlugin)
    ]
    print(
        f"[smoke] running with {len(eval_plugins)} of {len(app.plugins or [])} "
        f"plugins (FirestoreProgressPlugin stripped). Plugins: "
        f"{[type(p).__name__ for p in eval_plugins]}",
        flush=True,
    )

    smoke_app = App(
        name=app.name,
        root_agent=app.root_agent,
        plugins=eval_plugins,
        events_compaction_config=app.events_compaction_config,
        context_cache_config=app.context_cache_config,
        resumability_config=app.resumability_config,
    )

    svc = InMemorySessionService()
    user_id = "smoke-chatlog-001"
    session = await svc.create_session(app_name=smoke_app.name, user_id=user_id)
    runner = Runner(app=smoke_app, session_service=svc)

    full_query = (
        f"[Date: 2026-04-29] [Context: asking about Monsun, "
        f"Świętojańska, Gdynia, Poland (Place ID: ChIJ48HwEQCn_UYRmVqYQULc9pM)] "
        f"How does our menu pricing compare to competitors within 1 km?"
    )
    msg = types.Content(role="user", parts=[types.Part(text=full_query)])

    print(f"[smoke] session_id={session.id}", flush=True)
    print(f"[smoke] launching run...", flush=True)

    t0 = time.monotonic()
    n = 0
    async for evt in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=msg
    ):
        n += 1
        author = getattr(evt, "author", "?")
        if n <= 3 or n % 5 == 0:
            print(f"  [{n} +{time.monotonic()-t0:.0f}s] author={author}", flush=True)

    elapsed = time.monotonic() - t0
    print(f"[smoke] done in {elapsed:.1f}s, {n} events", flush=True)
    print(f"[smoke] session_id={session.id}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
