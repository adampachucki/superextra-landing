"""Tiny isolated probe — runs menu_pricing alone with a pre-set brief to see
whether the specialist works in isolation, before debugging the
ParallelAgent integration.

Logs every event verbosely (including thought parts and raw content reprs).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
AGENT_DIR = SPIKE_DIR.parents[1]
sys.path.insert(0, str(AGENT_DIR))

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "superextra-site")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")


def _load_dotenv(p):
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(AGENT_DIR / ".env")

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

from spikes.agent_tool.build import _make_specialist_a  # type: ignore
from spikes.agent_tool.places_context import PLACES_CONTEXT  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


async def main():
    spec = _make_specialist_a("menu_pricing", "pricing_result")

    svc = InMemorySessionService()
    session = await svc.create_session(
        app_name="probe",
        user_id="probe",
        state={
            "places_context": PLACES_CONTEXT,
            "specialist_briefs": {
                "menu_pricing": (
                    "Compare Monsun's menu pricing to its competitive set on "
                    "Świętojańska and nearby streets in Gdynia. Specifically: "
                    "find Monsun on Pyszne.pl, Wolt, Glovo, Uber Eats and Bolt "
                    "Food. Note current dish prices and any visible delivery "
                    "markup vs dine-in. Then do the same for Tłusta Kaczka, "
                    "Kurkuma Cafe, Pueblo Desayuno. Return a comparison table "
                    "with 3-5 representative dishes per restaurant."
                )
            },
        },
    )

    runner = Runner(app_name="probe", agent=spec, session_service=svc)
    msg = types.Content(role="user", parts=[types.Part(text="Begin researching now.")])

    n = 0
    async for evt in runner.run_async(user_id="probe", session_id=session.id, new_message=msg):
        n += 1
        author = getattr(evt, "author", "?")
        content = getattr(evt, "content", None)
        bits = []
        if content and getattr(content, "parts", None):
            for p in content.parts:
                if getattr(p, "function_call", None):
                    fc = p.function_call
                    bits.append(f"call:{fc.name}({list((fc.args or {}).keys())})")
                elif getattr(p, "function_response", None):
                    fr = p.function_response
                    rl = len(str(fr.response or ""))
                    bits.append(f"resp:{fr.name}(len={rl})")
                elif getattr(p, "text", None):
                    if getattr(p, "thought", False):
                        bits.append(f"thought({len(p.text)})")
                    else:
                        bits.append(f"text({len(p.text)})")
        actions = getattr(evt, "actions", None)
        if actions and getattr(actions, "state_delta", None):
            bits.append(f"state_delta={list(actions.state_delta.keys())}")
        ec = getattr(evt, "error_code", None)
        em = getattr(evt, "error_message", None)
        if ec or em:
            bits.append(f"ERROR ec={ec} em={em}")
        print(f"[{n:>3}] {author:<25} {' '.join(bits) or '(empty content)'}", flush=True)

    final = await svc.get_session(app_name="probe", user_id="probe", session_id=session.id)
    pr = final.state.get("pricing_result", "")
    print(f"\n=== final state pricing_result: len={len(pr) if pr else 0} ===")
    if pr:
        print(pr[:600])


if __name__ == "__main__":
    asyncio.run(main())
