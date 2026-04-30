"""Turn a scored CSV into a human-readable scorecard.

Reads the CSV produced by `score.py` and emits a terminal-friendly
summary: per-variant aggregates, per-venue breakdown, primary-probe
breakdown, and a flag list for degenerate runs (missing final report,
errors, timeouts, low judge scores).

Usage:
    .venv/bin/python evals/summarize.py --csv evals/scores/V0.csv
    .venv/bin/python evals/summarize.py --csv evals/scores/V0.csv --csv evals/scores/V1.csv  # multi-variant comparison
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


def _f(v, default=None):
    """Safe float parse — empty string, None, non-numeric → default."""
    if v in (None, "", "None"):
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _load(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        with p.open() as f:
            rows.extend(csv.DictReader(f))
    return rows


def _aggregate(rows: list[dict], label: str) -> dict:
    ok_rows = [
        r
        for r in rows
        if r.get("final_outcome") == "ok"
        and not r.get("timed_out") == "True"
        and not r.get("error")
    ]

    def avg(field, source=None):
        source = source if source is not None else ok_rows
        vals = [_f(r.get(field)) for r in source]
        vals = [v for v in vals if v is not None]
        return round(statistics.mean(vals), 2) if vals else None

    def mean_int(field, source=None):
        source = source if source is not None else ok_rows
        vals = [_f(r.get(field)) for r in source]
        vals = [v for v in vals if v is not None]
        return round(statistics.mean(vals), 1) if vals else None

    return {
        "label": label,
        "n_total": len(rows),
        "n_ok": len(ok_rows),
        "n_missing_final": sum(1 for r in rows if r.get("final_outcome") != "ok"),
        "n_error": sum(1 for r in rows if r.get("error")),
        "n_timeout": sum(1 for r in rows if r.get("timed_out") == "True"),
        "p1_top_domain_share": avg("p1_top_domain_share"),
        "final_top_domain_share": avg("final_top_domain_share"),
        "p1_category_count": mean_int("p1_category_count"),
        "final_category_count": mean_int("final_category_count"),
        "wall_brand_count": mean_int("wall_brand_count"),
        "faithfulness": avg("faithfulness"),
        "completeness": avg("completeness"),
        "specificity": avg("specificity"),
        "investigative_stance": avg("investigative_stance"),
        "tokens_total": mean_int("tokens_total"),
        "elapsed_s": mean_int("elapsed_s"),
    }


def _print_block(title: str, agg: dict) -> None:
    print(f"\n── {title} ─────────────────────────")
    print(
        "runs ok/missing_final/error/timeout: "
        f"{agg['n_ok']}/{agg['n_missing_final']}/{agg['n_error']}/{agg['n_timeout']} "
        f"(total {agg['n_total']})"
    )
    print()
    print(f"  top_domain_share   phase1={agg['p1_top_domain_share']}   final={agg['final_top_domain_share']}")
    print(f"  category_count     phase1={agg['p1_category_count']}     final={agg['final_category_count']} (out of 8)")
    print(f"  wall_brands_matched  avg {agg['wall_brand_count']} (out of 29; google_maps auto-write excluded)")
    print()
    print(f"  faithfulness         {agg['faithfulness']}")
    print(f"  completeness         {agg['completeness']}")
    print(f"  specificity          {agg['specificity']}  ← guarded")
    print(f"  investigative_stance {agg['investigative_stance']}")
    print()
    print(f"  tokens_avg  {agg['tokens_total']}")
    print(f"  elapsed_avg {agg['elapsed_s']} s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", action="append", required=True, help="path to scored CSV (repeat for multi-variant)")
    parser.add_argument("--degenerate-flag", action="store_true", help="list runs with missing final report / errors / low scores")
    args = parser.parse_args()

    all_rows = _load([Path(p) for p in args.csv])
    by_variant: dict[str, list[dict]] = defaultdict(list)
    for r in all_rows:
        by_variant[r.get("variant", "?")].append(r)

    for variant, rows in sorted(by_variant.items()):
        agg = _aggregate(rows, variant)
        _print_block(f"Variant {variant} (aggregate)", agg)

    # Primary-probe aggregate, per variant
    for variant, rows in sorted(by_variant.items()):
        primary = [r for r in rows if r.get("primary_probe") == "True"]
        if primary:
            agg = _aggregate(primary, f"{variant} primary probes")
            _print_block(f"Variant {variant} — primary probes only (q1/q2/q3)", agg)

    # Per-venue breakdown (one variant only — if multiple, would need matrix)
    if len(by_variant) == 1:
        [(_, rows)] = by_variant.items()
        by_venue: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_venue[r.get("venue_key", "?")].append(r)
        for venue, vrows in sorted(by_venue.items()):
            agg = _aggregate(vrows, venue)
            _print_block(f"Per-venue: {venue}", agg)

    # Degenerate-run flag list
    if args.degenerate_flag:
        print("\n── degenerate / flagged runs ─────────────────────────")
        for r in all_rows:
            flags = []
            if r.get("final_outcome") != "ok":
                flags.append(f"final={r.get('final_outcome')}")
            if r.get("error"):
                flags.append(f"err={r.get('error')}")
            if r.get("timed_out") == "True":
                flags.append("timeout")
            for dim in ("faithfulness", "specificity"):
                v = _f(r.get(dim))
                if v is not None and v <= 2:
                    flags.append(f"{dim}={int(v)}")
            if flags:
                print(f"  {r.get('variant')}/{r.get('venue_key')}/{r.get('query_id')}  {' '.join(flags)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
