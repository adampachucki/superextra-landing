"""Subprocess-per-variant runner for the research-depth eval harness.

Workflow:
  1. Resolve Place IDs for all venues via the Places API (once per invocation).
  2. For the requested --variant, build a temp instructions dir by copying
     the default `instructions/` tree and overlaying any files from
     `instructions_variants/<variant>/`.
  3. Spawn a child Python process with SUPEREXTRA_INSTRUCTIONS_DIR pointing
     at the temp dir. The child imports the agent (which now reads that
     env var) and runs the query × venue matrix in-process.
  4. Parent collects one JSON per run (venue × query) under `results/<variant>/`.

Usage (from repo root):
    cd agent
    .venv/bin/python evals/run_matrix.py --variant V0 \\
        --queries evals/queries.json \\
        --venues evals/venues.json \\
        --out evals/results/V0/
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_INSTRUCTIONS = AGENT_DIR / "superextra_agent" / "instructions"
VARIANTS_ROOT = EVALS_DIR / "instructions_variants"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _build_variant_dir(variant: str) -> Path:
    """Overlay variant files on top of the default instructions tree.

    Returns a temp directory path that the caller is expected to pass via
    SUPEREXTRA_INSTRUCTIONS_DIR and clean up when done. V0 is pass-through
    (pure copy of the default tree — nothing to overlay).
    """
    tmp = Path(tempfile.mkdtemp(prefix=f"superextra-eval-{variant}-"))
    shutil.copytree(DEFAULT_INSTRUCTIONS, tmp, dirs_exist_ok=True)
    overlay = VARIANTS_ROOT / variant
    if overlay.exists():
        for src in overlay.rglob("*"):
            if src.is_file():
                rel = src.relative_to(overlay)
                dst = tmp / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    return tmp


async def _resolve_place_ids(venues: list[dict]) -> None:
    """Resolve missing Place IDs in-place. Mutates the venues list."""
    # Import here so env is already set by the time we touch the Places client
    from superextra_agent.places_tools import search_restaurants

    for v in venues:
        if v.get("place_id"):
            continue
        query = f"{v['name']} {v.get('secondary') or ''}".strip()
        try:
            result = await search_restaurants(query=query)
        except Exception as e:  # noqa: BLE001
            print(f"[runner] place resolve failed for {v['key']}: {e}", flush=True)
            continue
        places = (result or {}).get("results") or []
        if not places:
            print(f"[runner] no places for '{query}'", flush=True)
            continue
        v["place_id"] = places[0].get("id")
        print(f"[runner] resolved {v['key']} → {v['place_id']}", flush=True)


async def _run_single(
    runner,
    svc,
    app_name: str,
    venue: dict,
    query_spec: dict,
    user_id_prefix: str,
) -> dict:
    """Run a single query × venue end-to-end and return the captured run record."""
    from google.genai import types

    from evals.parse_events import parse_run

    today = datetime.date.today().isoformat()
    pid = venue.get("place_id") or "unknown"
    context = (
        f"[Context: asking about {venue['name']}, {venue['secondary']} "
        f"(Place ID: {pid})]"
    )
    full_query = f"[Date: {today}] {context} {query_spec['text']}"

    user_id = f"{user_id_prefix}-{venue['key']}-{query_spec['id']}"
    session = await svc.create_session(app_name=app_name, user_id=user_id)
    msg = types.Content(role="user", parts=[types.Part(text=full_query)])

    events: list = []
    t0 = time.monotonic()
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    error: str | None = None
    timed_out = False

    async def _consume() -> None:
        async for evt in runner.run_async(
            user_id=user_id, session_id=session.id, new_message=msg
        ):
            events.append(evt)

    try:
        # 20-min per-run cap — phase0 gate is 22 min p99, so this is a ceiling.
        await asyncio.wait_for(_consume(), timeout=20 * 60)
    except asyncio.TimeoutError:
        timed_out = True
        error = "timeout"
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"

    elapsed = time.monotonic() - t0
    parsed = parse_run(events)

    return {
        "query_id": query_spec["id"],
        "query_text": query_spec["text"],
        "query_pill_category": query_spec.get("pill_category"),
        "query_primary_probe": bool(query_spec.get("primary_probe")),
        "venue_key": venue["key"],
        "venue_name": venue["name"],
        "venue_secondary": venue.get("secondary"),
        "place_id": pid,
        "adk_session_id": session.id,
        "started_at": started_at,
        "elapsed_s": round(elapsed, 2),
        "timed_out": timed_out,
        "error": error,
        **parsed,
    }


async def _run_matrix_in_process(args: argparse.Namespace) -> int:
    """Child-process entry point: imports agent, runs matrix, writes JSONs."""
    from google.adk.runners import Runner
    from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService

    from superextra_agent.agent import app

    queries = json.loads(Path(args.queries).read_text())["queries"]
    venues_data = json.loads(Path(args.venues).read_text())["venues"]

    if args.query_id:
        queries = [q for q in queries if q["id"] == args.query_id]
        if not queries:
            print(f"[runner] no query matches --query-id={args.query_id}", flush=True)
            return 2

    if args.venue_key:
        venues_data = [v for v in venues_data if v["key"] == args.venue_key]
        if not venues_data:
            print(f"[runner] no venue matches --venue-key={args.venue_key}", flush=True)
            return 2

    await _resolve_place_ids(venues_data)

    # Persist resolved Place IDs back to the venues file so subsequent runs
    # (and other variants) don't re-pay the Places cost.
    venues_path = Path(args.venues)
    full = json.loads(venues_path.read_text())
    by_key = {v["key"]: v for v in venues_data}
    for v in full["venues"]:
        if v["key"] in by_key and by_key[v["key"]].get("place_id"):
            v["place_id"] = by_key[v["key"]]["place_id"]
    venues_path.write_text(json.dumps(full, indent=2, ensure_ascii=False) + "\n")

    svc = VertexAiSessionService(
        project="superextra-site",
        location="us-central1",
        agent_engine_id="2746721333428617216",
    )
    runner = Runner(app=app, session_service=svc)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    combos = [(v, q) for v in venues_data for q in queries]
    print(
        f"[runner] variant={args.variant} combos={len(combos)} "
        f"(venues={len(venues_data)}, queries={len(queries)})",
        flush=True,
    )

    for i, (venue, query) in enumerate(combos, 1):
        out_path = out_dir / f"{venue['key']}__{query['id']}.json"
        if out_path.exists() and not args.force:
            print(f"[runner] ({i}/{len(combos)}) skip existing {out_path.name}", flush=True)
            continue
        print(
            f"[runner] ({i}/{len(combos)}) venue={venue['key']} query={query['id']}",
            flush=True,
        )
        rec = await _run_single(runner, svc, app.name, venue, query, args.variant)
        rec["variant"] = args.variant
        out_path.write_text(json.dumps(rec, indent=2, ensure_ascii=False, default=str))
        status = "TIMEOUT" if rec["timed_out"] else ("ERROR" if rec["error"] else "OK")
        synth = rec.get("synth_outcome", "?")
        n_drawer = len(rec.get("drawer_sources") or [])
        n_fetched = len(rec.get("fetched_urls") or [])
        print(
            f"[runner] ({i}/{len(combos)}) {status} elapsed={rec['elapsed_s']:.1f}s "
            f"synth={synth} drawer={n_drawer} fetched={n_fetched} "
            f"specialists={rec.get('specialists_dispatched')} err={rec['error']}",
            flush=True,
        )

    return 0


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True, help="V0 | V1 | V2 | V3")
    parser.add_argument("--queries", default=str(EVALS_DIR / "queries.json"))
    parser.add_argument("--venues", default=str(EVALS_DIR / "venues.json"))
    parser.add_argument("--out", required=True, help="output directory for per-run JSONs")
    parser.add_argument("--force", action="store_true", help="overwrite existing run JSONs")
    parser.add_argument("--query-id", help="run only this query id")
    parser.add_argument("--venue-key", help="run only this venue key")
    parser.add_argument(
        "--child",
        action="store_true",
        help="internal: signals this process is the in-process runner child",
    )
    args = parser.parse_args()

    # Make agent imports work regardless of how this is invoked.
    sys.path.insert(0, str(AGENT_DIR))

    # Always ensure cloud env is set before any import that touches Vertex/Places.
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "superextra-site")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
    _load_dotenv(AGENT_DIR / ".env")

    if args.child:
        # We're inside the subprocess. SUPEREXTRA_INSTRUCTIONS_DIR is already set
        # by the parent. Agent imports happen inside _run_matrix_in_process()
        # (deferred until after env setup) so the override takes effect.
        return asyncio.run(_run_matrix_in_process(args))

    # Parent: build the overlay dir, spawn child with env override.
    variant_dir = _build_variant_dir(args.variant)
    try:
        env = os.environ.copy()
        env["SUPEREXTRA_INSTRUCTIONS_DIR"] = str(variant_dir)
        child_cmd = [
            sys.executable,
            str(Path(__file__)),
            "--variant", args.variant,
            "--queries", args.queries,
            "--venues", args.venues,
            "--out", args.out,
            "--child",
        ]
        if args.force:
            child_cmd.append("--force")
        if args.query_id:
            child_cmd += ["--query-id", args.query_id]
        if args.venue_key:
            child_cmd += ["--venue-key", args.venue_key]
        print(
            f"[runner] spawning child: variant={args.variant} "
            f"instructions={variant_dir}",
            flush=True,
        )
        return subprocess.call(child_cmd, env=env, cwd=str(AGENT_DIR))
    finally:
        shutil.rmtree(variant_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(_main())
