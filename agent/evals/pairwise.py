"""Scripted pairwise judge for variant comparisons.

Compares two run JSONs (typically Variant A vs Variant B on the same
venue × query) and emits a structured verdict. Default judge is Claude
Opus 4.7 (`claude-opus-4-7`), chosen because the system being judged
runs on Gemini — same-family correlation bias would inflate scores for
Gemini-shaped outputs. Falls back to Gemini 2.5 Pro if `--model` starts
with `gemini`.

Usage:
    .venv/bin/python evals/pairwise.py \\
        --a evals/results/V_baseline/monsun__q3_price_comparison_t1.json \\
        --b evals/results/V_agenttool/monsun__q3_price_comparison_t1.json \\
        --out evals/pairwise_verdicts/agenttool/monsun_q3_t1.json \\
        --model claude-opus-4-7

Output JSON (backwards-compatible: `winner` field always present):
    {
        "winner": "A" | "B" | "TIE",
        "dimensions": {
            "coverage": "A" | "B" | "TIE",
            "specificity": "A" | "B" | "TIE",
            "source_diversity": "A" | "B" | "TIE",
            "actionability": "A" | "B" | "TIE",
            "specialist_set_correctness": "A" | "B" | "TIE"
        },
        "supporting_urls": [...],
        "judge_model": "claude-opus-4-7",
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

Two AI-generated reports follow. Variant A is "{a_label}"; Variant B is "{b_label}". Both ran on the same query and venue. Your job is to decide which is more useful **as the operator would**, scoring each named dimension.

## Dimensions to score

For each dimension below, pick a winner (`A`, `B`, or `TIE`):

1. **coverage** — Did the report address all relevant angles for this question type? Look for missing perspectives a real operator would want.
2. **specificity** — Does the report cite concrete numbers, named competitors, dated events, sourced claims? Or does it default to generic prose?
3. **source_diversity** — Did the report draw from at least two source types (delivery platforms, social, community/forums, press, government, structured-API)? Mono-source reports are weaker even if internally rich.
4. **actionability** — Could you, as the operator, do something this week based on this report? Or does it stop at observations without implications?
5. **specialist_set_correctness** — Did the orchestrator dispatch the right specialists for this query? Expected set (where defined): {expected_specialists}. Penalize spurious adds and meaningful misses; routine variation is TIE.

Spot-check at least one specific claim in each report by reasoning about internal consistency and cross-references between named entities, dates, prices, and the cited drawer domains. (Note: you do not have live web access in this judging call.)

## Overall winner

Pick `A`, `B`, or `TIE` for the **overall** verdict. The overall verdict is your holistic operator judgment, informed by but not strictly summed from the dimensions — a report that wins coverage and specificity but is unactionable can still lose overall.

Give a 1-paragraph justification (~150 words) referencing the dimensional reasoning. End your response with EXACTLY this JSON line and nothing after it:

```json
{{"winner": "A" | "B" | "TIE", "dimensions": {{"coverage": "A|B|TIE", "specificity": "A|B|TIE", "source_diversity": "A|B|TIE", "actionability": "A|B|TIE", "specialist_set_correctness": "A|B|TIE"}}, "supporting_urls": ["url1", "url2"]}}
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


# Find the trailing JSON object — must contain "winner" and may contain
# "dimensions". We look for the last `{...}` block in the text that has
# "winner" in it (allows multi-line JSON across `dimensions`).
_JSON_BLOCK = re.compile(r"\{[\s\S]*\"winner\"[\s\S]*\}", re.DOTALL)


def _build_prompt(a: dict, b: dict, a_label: str, b_label: str) -> str:
    def domains(src):
        return sorted({s.get("domain") for s in src.get("drawer_sources") or [] if s.get("domain")})

    expected = a.get("expected_specialists") or b.get("expected_specialists") or []
    expected_str = ", ".join(expected) if expected else "(not specified — judge on routing reasonableness alone)"

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
        expected_specialists=expected_str,
    )


def _parse_response(text: str) -> dict:
    """Pull the JSON winner block out of the response."""
    # Search for the LAST JSON block — judges sometimes write a sketch
    # earlier in their response.
    matches = list(_JSON_BLOCK.finditer(text))
    if not matches:
        return {
            "winner": None,
            "dimensions": {},
            "supporting_urls": [],
            "parse_error": "no_json",
        }
    raw = matches[-1].group(0)
    # Strip ``` fencing if the regex picked it up.
    raw = raw.strip().strip("`")
    try:
        parsed = json.loads(raw)
        return {
            "winner": parsed.get("winner"),
            "dimensions": parsed.get("dimensions") or {},
            "supporting_urls": parsed.get("supporting_urls") or [],
        }
    except json.JSONDecodeError as e:
        return {
            "winner": None,
            "dimensions": {},
            "supporting_urls": [],
            "parse_error": f"json: {e}",
        }


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
        config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=8000),
    )
    return resp.text or ""


def _judge_claude(prompt: str, model: str) -> str:
    """Claude judge path. Uses ANTHROPIC_API_KEY from env.

    The Anthropic SDK shape mirrors the Gemini one: client → messages.create.
    `max_tokens` is required by the SDK; 4000 matches the Gemini default.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY env var not set. Set it in your shell before "
            "running the Claude judge — agent/.env is not used for this key. "
            "Example: `export ANTHROPIC_API_KEY=sk-ant-...`"
        )
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    # `content` is a list of content blocks; collect text from each.
    parts = []
    for block in resp.content or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True, help="path to run JSON A")
    parser.add_argument("--b", required=True, help="path to run JSON B")
    parser.add_argument("--out", required=True, help="output verdict JSON")
    parser.add_argument(
        "--model",
        default="claude-opus-4-7",
        help="judge model id (claude-* dispatches to Anthropic, gemini-* to Vertex)",
    )
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
    if args.model.startswith("claude"):
        text = _judge_claude(prompt, args.model)
    else:
        text = _judge_gemini(prompt, args.model)
    parsed = _parse_response(text)

    out = {
        "winner": parsed.get("winner"),
        "dimensions": parsed.get("dimensions") or {},
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
        f"winner={parsed.get('winner')}, dims={parsed.get('dimensions')}, "
        f"written to {args.out}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
