"""Scripted pairwise judge for variant comparisons.

Compares two run JSONs (typically V0 vs V2.1 on the same venue × query) and
emits a structured verdict using Gemini 2.5 Pro as the judge model.

This script is the **cheap unattended path** — fast, scriptable, and useful
for catching obvious regressions across many comparisons. For high-stakes
or close-call decisions, use **Claude subagents in-session as operator
judges** instead (the pattern documented in
`docs/research-depth-pairwise-verdicts-2026-04-25.md`). Subagents have
WebFetch and produce richer verifiable verdicts; the scripted Gemini judge
does not verify cited claims live, only reasons about internal consistency.

Usage:
    .venv/bin/python evals/pairwise.py \\
        --a evals/results/V0/monsun__q1_openings_closings.json \\
        --b evals/results/V2_1/monsun__q1_openings_closings.json \\
        --out evals/pairwise_verdicts/monsun_q1_V0_vs_V2_1.json

Output JSON:
    {
        "winner": "A" | "B" | "TIE",
        "supporting_urls": [...],
        "judge_model": "gemini-2.5-pro",
        "a_label": "<variant_a name>",
        "b_label": "<variant_b name>",
        "input_a_path": "...",
        "input_b_path": "...",
        "venue_key": "...",
        "query_id": "...",
        "raw_response": "...",
    }
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_DIR))

# Env setup mirrors run_matrix.py
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


_PROMPT_TEMPLATE = """You are roleplaying as the owner/GM of {venue_name} at {venue_secondary}. You asked an AI service: "{query}"

Two AI-generated reports follow. Variant A is "{a_label}"; Variant B is "{b_label}". Both ran on the same query and venue. Your job is to decide which is more useful **as the operator would**.

Compare along four axes:
1. Actionability — what could you do this week based on each report?
2. Specificity that verifies — do named figures, dates, and venues hold up?
3. Coverage of what matters for this query type — relevant evidence surfaces (delivery platforms, social, press, municipal, registries, neighborhood context).
4. Signal-to-noise — generic prose vs operator-relevant detail.

Spot-check at least one specific claim in each report by reasoning about internal consistency and cross-references between the report's named entities, dates, prices, and the cited drawer domains. (Note: you do not have live web access in this judging call — that's reserved for higher-stakes Claude subagent judging when needed.)

Pick a winner: A, B, or TIE. Give a 1-paragraph justification (~150 words). End your response with EXACTLY this JSON line and nothing after it:
```json
{{"winner": "A" | "B" | "TIE", "supporting_urls": ["url1", "url2"]}}
```

---

## Variant A — {a_label}

**Specialists dispatched:** {a_specialists}

**Drawer source domains ({a_n_drawer}):** {a_drawer_domains}

**Report:**

{a_report}

---

## Variant B — {b_label}

**Specialists dispatched:** {b_specialists}

**Drawer source domains ({b_n_drawer}):** {b_drawer_domains}

**Report:**

{b_report}

---

Now: which is the better answer for this operator on this question?"""


_JSON_LINE = re.compile(r"\{[^{}]*\"winner\"[^{}]*\}", re.DOTALL)


def _build_prompt(a: dict, b: dict, a_label: str, b_label: str) -> str:
    def domains(src):
        return sorted({s.get("domain") for s in src.get("drawer_sources") or [] if s.get("domain")})

    return _PROMPT_TEMPLATE.format(
        venue_name=a.get("venue_name", "?"),
        venue_secondary=a.get("venue_secondary", "?"),
        query=a.get("query_text", "?"),
        a_label=a_label,
        b_label=b_label,
        a_specialists=", ".join(a.get("specialists_dispatched") or []) or "(none)",
        a_n_drawer=len(a.get("drawer_sources") or []),
        a_drawer_domains=", ".join(domains(a)) or "(none)",
        a_report=a.get("final_report") or "(empty report)",
        b_specialists=", ".join(b.get("specialists_dispatched") or []) or "(none)",
        b_n_drawer=len(b.get("drawer_sources") or []),
        b_drawer_domains=", ".join(domains(b)) or "(none)",
        b_report=b.get("final_report") or "(empty report)",
    )


def _parse_response(text: str) -> dict:
    """Pull the JSON winner line out of the response."""
    m = _JSON_LINE.search(text)
    if not m:
        return {"winner": None, "supporting_urls": [], "parse_error": "no_json"}
    try:
        parsed = json.loads(m.group(0))
        return {
            "winner": parsed.get("winner"),
            "supporting_urls": parsed.get("supporting_urls") or [],
        }
    except json.JSONDecodeError as e:
        return {"winner": None, "supporting_urls": [], "parse_error": f"json: {e}"}


def _judge_gemini(prompt: str, model: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site"),
        location="global",
    )
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=4000),
    )
    return resp.text or ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True, help="path to run JSON A")
    parser.add_argument("--b", required=True, help="path to run JSON B")
    parser.add_argument("--out", required=True, help="output verdict JSON")
    parser.add_argument("--model", default="gemini-2.5-pro", help="Gemini model id")
    parser.add_argument("--a-label", help="label for variant A (defaults to file's variant field)")
    parser.add_argument("--b-label", help="label for variant B (defaults to file's variant field)")
    args = parser.parse_args()

    a_data = json.loads(Path(args.a).read_text())
    b_data = json.loads(Path(args.b).read_text())

    a_label = args.a_label or a_data.get("variant", "A")
    b_label = args.b_label or b_data.get("variant", "B")

    if (a_data.get("venue_key"), a_data.get("query_id")) != (b_data.get("venue_key"), b_data.get("query_id")):
        print(
            f"[pairwise] WARNING: A and B are for different venue/query pairs — "
            f"A=({a_data.get('venue_key')}, {a_data.get('query_id')}) "
            f"B=({b_data.get('venue_key')}, {b_data.get('query_id')})",
            flush=True,
        )

    prompt = _build_prompt(a_data, b_data, a_label, b_label)
    text = _judge_gemini(prompt, args.model)
    parsed = _parse_response(text)

    out = {
        "winner": parsed.get("winner"),
        "supporting_urls": parsed.get("supporting_urls") or [],
        "judge_model": args.model,
        "a_label": a_label,
        "b_label": b_label,
        "input_a_path": args.a,
        "input_b_path": args.b,
        "venue_key": a_data.get("venue_key"),
        "query_id": a_data.get("query_id"),
        "raw_response": text,
        "parse_error": parsed.get("parse_error"),
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(
        f"[pairwise] {a_label} vs {b_label} on {a_data.get('venue_key')}/{a_data.get('query_id')}: "
        f"winner={parsed.get('winner')}, written to {args.out}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
