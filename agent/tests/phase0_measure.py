"""Phase 0 p99 gate measurement.

Runs `agent/tests/fixtures/phase0_queries.json` against the in-process ADK
Runner with Agent Engine session service. Captures wall-clock duration per
run + a light event summary. Appends to `agent/tests/phase0_measurements.json`
after every run so partial progress survives a crash.

Gate: p99 < 22 min. With 10 runs, p99 is effectively max(runs).

Env (run from repo root):
    export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/legacy_credentials/<you>/adc.json
    export GOOGLE_CLOUD_PROJECT=superextra-site
    export GOOGLE_CLOUD_LOCATION=us-central1
    export GOOGLE_GENAI_USE_VERTEXAI=TRUE

Usage:
    cd agent && PYTHONPATH=. .venv/bin/python tests/phase0_measure.py
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import sys
import time
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
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


from google.adk.runners import Runner
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService
from google.genai import types

from superextra_agent.agent import app
from superextra_agent.places_tools import search_restaurants


PROJECT = "superextra-site"
LOCATION = "us-central1"
AGENT_ENGINE_ID = "2746721333428617216"
USER_ID_PREFIX = "phase0-"

FIXTURE_PATH = AGENT_DIR / "tests" / "fixtures" / "phase0_queries.json"
OUTPUT_PATH = AGENT_DIR / "tests" / "phase0_measurements.json"

# Optional: PHASE0_TIERS=broad to filter runs; PHASE0_OUTPUT overrides output file.
_TIER_FILTER = set(os.environ.get("PHASE0_TIERS", "").split(",")) - {""}
if os.environ.get("PHASE0_OUTPUT"):
    OUTPUT_PATH = Path(os.environ["PHASE0_OUTPUT"])

PER_RUN_TIMEOUT_S = 30 * 60  # 30 min — the ceiling we're gating against
GATE_P99_S = 22 * 60


async def _resolve_place_id(name: str, secondary: str) -> tuple[str | None, str | None]:
    """Use the Places text-search tool to find a Place ID for name + area."""
    query = f"{name} {secondary}".strip()
    try:
        result = await search_restaurants(query=query)
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"
    if (result or {}).get("status") != "success":
        return None, (result or {}).get("error_message") or "search failed"
    places = (result or {}).get("results") or []
    if not places:
        return None, f"no result for '{query}'"
    top = places[0]
    return top.get("id"), None


def _save(records: list[dict]) -> None:
    payload = {
        "fixture": str(FIXTURE_PATH),
        "started_at": records[0].get("started_at") if records else None,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "runs": records,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, default=str))


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    # Nearest-rank method, 1-indexed.
    n = len(sorted_values)
    rank = max(1, min(n, int(round((pct / 100.0) * n + 0.5))))
    return sorted_values[rank - 1]


async def _run_one(
    svc: VertexAiSessionService,
    runner: Runner,
    spec: dict,
    place: dict,
) -> dict:
    run_id = spec["id"]
    user_id = f"{USER_ID_PREFIX}{run_id}"
    today = datetime.date.today().isoformat()
    pid = place.get("place_id") or "unknown"
    context_line = (
        f"[Context: asking about {place['name']}, {place['secondary']} (Place ID: {pid})]"
    )
    full_query = f"[Date: {today}] {context_line} {spec['query']}"

    session = await svc.create_session(app_name=app.name, user_id=user_id)
    msg = types.Content(role="user", parts=[types.Part(text=full_query)])

    t0 = time.monotonic()
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    authors: dict[str, int] = {}
    final_events = 0
    has_final_report = False
    error: str | None = None
    timed_out = False

    async def _consume() -> None:
        nonlocal final_events, has_final_report
        async for evt in runner.run_async(
            user_id=user_id, session_id=session.id, new_message=msg
        ):
            author = getattr(evt, "author", None) or "?"
            authors[author] = authors.get(author, 0) + 1
            try:
                if evt.is_final_response():
                    final_events += 1
            except Exception:  # noqa: BLE001
                pass
            actions = getattr(evt, "actions", None)
            sd = getattr(actions, "state_delta", None) if actions else None
            if sd and "final_report" in sd:
                has_final_report = True

    try:
        await asyncio.wait_for(_consume(), timeout=PER_RUN_TIMEOUT_S)
    except asyncio.TimeoutError:
        timed_out = True
        error = f"timeout after {PER_RUN_TIMEOUT_S}s"
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"

    elapsed = time.monotonic() - t0
    return {
        "id": run_id,
        "tier": spec["tier"],
        "place_key": spec["place_key"],
        "place_name": place["name"],
        "place_id": pid,
        "adk_session_id": session.id,
        "started_at": started_at,
        "elapsed_s": round(elapsed, 2),
        "elapsed_min": round(elapsed / 60.0, 2),
        "timed_out": timed_out,
        "has_final_report": has_final_report,
        "final_events": final_events,
        "authors": authors,
        "error": error,
    }


async def main() -> int:
    fixture = json.loads(FIXTURE_PATH.read_text())
    places = fixture["places"]
    runs = fixture["runs"]
    if _TIER_FILTER:
        runs = [r for r in runs if r["tier"] in _TIER_FILTER]
        print(f"[phase0] filtered to tiers={sorted(_TIER_FILTER)} → {len(runs)} runs", flush=True)

    print(f"[phase0] fixture: {len(runs)} runs, {len(places)} places", flush=True)
    print(f"[phase0] gate: p99 < {GATE_P99_S}s ({GATE_P99_S / 60:.0f} min)", flush=True)

    # Resolve missing Place IDs
    for key, place in places.items():
        if not place.get("place_id"):
            pid, err = await _resolve_place_id(place["name"], place["secondary"])
            if err:
                print(f"[phase0] WARN: could not resolve '{place['name']}': {err} — using 'unknown'", flush=True)
            else:
                place["place_id"] = pid
                print(f"[phase0] resolved {key} → {pid}", flush=True)

    svc = VertexAiSessionService(
        project=PROJECT, location=LOCATION, agent_engine_id=AGENT_ENGINE_ID
    )
    runner = Runner(app=app, session_service=svc)

    records: list[dict] = []
    for i, spec in enumerate(runs, 1):
        place = places[spec["place_key"]]
        print(
            f"[phase0] ({i}/{len(runs)}) id={spec['id']} tier={spec['tier']} "
            f"place={place['name']} query={spec['query'][:60]!r}",
            flush=True,
        )
        rec = await _run_one(svc, runner, spec, place)
        records.append(rec)
        _save(records)
        status = "TIMEOUT" if rec["timed_out"] else ("ERROR" if rec["error"] else "OK")
        print(
            f"[phase0] ({i}/{len(runs)}) id={spec['id']} {status} "
            f"elapsed={rec['elapsed_min']:.2f}min final_report={rec['has_final_report']} "
            f"err={rec['error']}",
            flush=True,
        )

    # Summary
    elapsed_s = sorted(r["elapsed_s"] for r in records if not r["timed_out"])
    p50 = _percentile(elapsed_s, 50)
    p95 = _percentile(elapsed_s, 95)
    p99 = _percentile(elapsed_s, 99)
    max_s = elapsed_s[-1] if elapsed_s else None
    timed_out_n = sum(1 for r in records if r["timed_out"])
    errored_n = sum(1 for r in records if r["error"] and not r["timed_out"])
    no_report_n = sum(1 for r in records if not r["has_final_report"])

    gate_pass = (p99 is not None) and (p99 < GATE_P99_S) and (timed_out_n == 0)

    print("\n[phase0] === SUMMARY ===")
    print(f"runs_ok     = {len(elapsed_s)}/{len(records)}")
    print(f"timed_out   = {timed_out_n}")
    print(f"errored     = {errored_n}")
    print(f"no_report   = {no_report_n}")
    if elapsed_s:
        print(f"p50 (min)   = {p50/60:.2f}")
        print(f"p95 (min)   = {p95/60:.2f}")
        print(f"p99 (min)   = {p99/60:.2f}")
        print(f"max (min)   = {max_s/60:.2f}")
    print(f"gate        = p99 < {GATE_P99_S/60:.0f} min → {'PASS' if gate_pass else 'FAIL'}")

    # Append summary to output file
    payload = json.loads(OUTPUT_PATH.read_text())
    payload["summary"] = {
        "runs_ok": len(elapsed_s),
        "timed_out": timed_out_n,
        "errored": errored_n,
        "no_report": no_report_n,
        "p50_s": p50,
        "p95_s": p95,
        "p99_s": p99,
        "max_s": max_s,
        "gate_s": GATE_P99_S,
        "gate_pass": gate_pass,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"[phase0] results → {OUTPUT_PATH}")
    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
