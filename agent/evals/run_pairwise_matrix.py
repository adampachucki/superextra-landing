#!/usr/bin/env python3
"""Run pairwise judge over all (venue × query × trial) for two variants.

Calls evals/pairwise.py once per matched pair, in parallel with bounded
concurrency. Aggregates the per-dimension verdicts into a summary CSV.

Usage:
    .venv/bin/python evals/run_pairwise_matrix.py \\
        --a-dir evals/results/baseline_t3 \\
        --b-dir evals/results/round1_t3 \\
        --a-label baseline --b-label round1 \\
        --out-verdicts evals/pairwise_verdicts/baseline_vs_round1 \\
        --out-summary evals/pairwise_verdicts/baseline_vs_round1.csv \\
        --model gemini-2.5-pro \\
        --concurrency 4
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import subprocess
from pathlib import Path
from collections import Counter

EVALS_DIR = Path(__file__).resolve().parent
PAIRWISE_SCRIPT = EVALS_DIR / "pairwise.py"
PYTHON = EVALS_DIR.parent / ".venv" / "bin" / "python"


async def _run_one(sem: asyncio.Semaphore, a_path: Path, b_path: Path,
                   out_path: Path, model: str, a_label: str, b_label: str) -> dict | None:
    if out_path.exists():
        try:
            return json.loads(out_path.read_text())
        except Exception:
            pass
    out_path.parent.mkdir(parents=True, exist_ok=True)
    async with sem:
        proc = await asyncio.create_subprocess_exec(
            str(PYTHON), str(PAIRWISE_SCRIPT),
            "--a", str(a_path), "--b", str(b_path),
            "--out", str(out_path),
            "--model", model,
            "--a-label", a_label,
            "--b-label", b_label,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            print(f"[pairwise] FAIL {a_path.name}: {stderr.decode()[-300:]}", flush=True)
            return None
    try:
        return json.loads(out_path.read_text())
    except Exception:
        return None


async def _main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--a-dir", required=True)
    p.add_argument("--b-dir", required=True)
    p.add_argument("--a-label", required=True)
    p.add_argument("--b-label", required=True)
    p.add_argument("--out-verdicts", required=True)
    p.add_argument("--out-summary", required=True)
    p.add_argument("--model", default="gemini-2.5-pro")
    p.add_argument("--concurrency", type=int, default=4)
    args = p.parse_args()

    a_dir = Path(args.a_dir)
    b_dir = Path(args.b_dir)
    out_dir = Path(args.out_verdicts)

    pairs = []
    for a_path in sorted(a_dir.glob("*.json")):
        b_path = b_dir / a_path.name
        if not b_path.exists():
            continue
        out_path = out_dir / a_path.name
        pairs.append((a_path, b_path, out_path))
    print(f"[pairwise] {len(pairs)} pairs to judge", flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(*[
        _run_one(sem, a, b, o, args.model, args.a_label, args.b_label)
        for (a, b, o) in pairs
    ])

    # Aggregate
    rows = []
    dim_keys = ["coverage", "specificity", "source_diversity", "actionability",
                "specialist_set_correctness"]
    overall_winners: list[str] = []
    dim_winners: dict[str, list[str]] = {k: [] for k in dim_keys}
    for (a, _, _), v in zip(pairs, results):
        if not v:
            continue
        winner = v.get("winner", "?")
        overall_winners.append(winner)
        for k in dim_keys:
            dim_winners[k].append((v.get("dimensions") or {}).get(k, "?"))
        rows.append({
            "venue_query_trial": a.stem,
            "winner": winner,
            **{k: (v.get("dimensions") or {}).get(k, "?") for k in dim_keys},
        })

    Path(args.out_summary).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_summary, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["venue_query_trial", "winner", *dim_keys])
        w.writeheader()
        w.writerows(rows)

    def fmt(c: Counter) -> str:
        n = sum(c.values()) or 1
        a = c.get("A", 0)
        b = c.get("B", 0)
        t = c.get("TIE", 0)
        return f"A={a} ({a*100//n}%)  B={b} ({b*100//n}%)  TIE={t} ({t*100//n}%)"

    print(f"\n=== {args.a_label} (A) vs {args.b_label} (B) — {len(rows)} verdicts ===\n")
    print(f"  overall  {fmt(Counter(overall_winners))}")
    for k in dim_keys:
        print(f"  {k:<28}  {fmt(Counter(dim_winners[k]))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
