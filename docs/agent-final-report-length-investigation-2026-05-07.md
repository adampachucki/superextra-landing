# Final-report length and depth — investigation

The question: are the agent's final research reports over-compressed relative to the specialist research feeding them? The hypothesis was that final answers might be settling into a default shape regardless of how much material the specialists actually surface.

## What the data shows

The right dataset is the V3 eval set in `agent/evals/results/V3` — 24 query/venue combinations run end-to-end through the current architecture, with `parse_events.py` capturing the final report text and each specialist's full output from event state_delta. Across those 24 runs:

- Final reports run **5,448 to 9,689 chars** (roughly 770–1,270 words). Median 7,039 chars / ~1,000 words.
- Specialist input feeding the lead totals **median 13,422 chars** per session.
- Compression ratio (specialist input ÷ final report) is **median 2.0×, range 0.55× to 3.5×**.

The "narrow band" finding from local JSONL logs that motivated the original investigation does not survive this. Those 340 logs were almost entirely from a deprecated synthesizer agent on a homogeneous test corpus, and `ChatLoggerPlugin` records only 500-char text previews — chars/words I derived from them were extrapolations, not measurements.

What the V3 data actually shows is that report length scales with question scope: q6 market saturation runs 8,500–9,700 chars on 4–5 specialists with ~19,000 chars of input, while q3 price comparison runs 5,400–7,300 chars on 2–3 specialists with ~12,000 chars of input. Single-specialist queries (q8 wage benchmarks) actually expand — final report is ~1.8× the specialist's response, since the lead adds framing the user needs around a narrow factual reply.

There is one mild signal worth flagging: when specialist input grows from ~12k to ~24k chars, final reports only grow from ~6.7k to ~9.7k. Output scales sublinearly with input. Whether that's "compression toward the mean" or "appropriate compression of redundant material" can't be settled from length alone — it would need the existing scorer's faithfulness/completeness ratings, which weren't part of this investigation.

Honest read: there is no clear over-compression defect in the current architecture's eval data. The original concern was a ghost from stale data.

## Recommendation — make it visible, change nothing

Two-line addition to the eval scorer (`agent/evals/score.py:382`) so future runs surface compression alongside the existing token totals:

```python
"final_chars": len(run.get("final_report") or ""),
"specialist_chars": sum(len(v) for v in (run.get("specialist_outputs") or {}).values()),
```

Both fields already come back from `parse_events.py:165`. With those columns in the CSV, length-vs-depth is visible at every eval rerun. If a future run shows a query where the lead heavily compressed rich specialist input _and_ the judge's faithfulness or completeness scores dropped, that's a concrete defect — and the trigger for a prompt change. Without that pairing, length alone proves nothing.

That is the entire intervention warranted by the data. No new rubric, no prompt program, no production-side audit script.

## Small prompt cleanup, while we're here

Independent of the depth question: `research_lead.md:71–86` ends with a "Recommended structure" block that lists Executive Summary / 2–5 insight sections / What this means for the operator / Follow-up questions. The same structure is already implied by rule 1 (lead with truth → exec-summary opening), rule 3 (organize by insight theme → insight sections), and rule 7 (end with follow-up questions). The block adds one new constraint not in the rules: the "2–5 insight sections" cap, which is the prompt's only fixed-length anchor.

Removing the block (six lines) leaves the rules intact and removes a redundant section ceiling. This is a cleanup, not a depth fix — justified on its own as redundant prose. If sectioning regresses on the next eval, restore.

Net change: **+2 lines in `score.py`, −6 lines in `research_lead.md`, net −4 LOC**.

## What we explicitly are not doing

- Not building a depth-preservation rubric. `judge_rubric.md` already covers faithfulness, completeness, specificity, and investigative stance — all sensitive to harmful compression. A new rubric would duplicate work the existing harness already does.
- Not setting `max_output_tokens`, `output_schema`, Vertex structured output, or any output-control config. Those shape content; they don't address depth, and there's no evidence the model is hitting any limit. Default Gemini 3.x output ceilings are well above the observed median, so truncation isn't the failure mode in play.
- Not running a four-variant pairwise comparison or operator review. The evidence threshold for that is "a defect we can name." This investigation didn't find one.

## References

- `agent/evals/parse_events.py:30–169` — captures full final-report text and per-specialist outputs from event state_delta. The data this investigation rests on.
- `agent/evals/score.py:382–417` — the row dict where the two compression columns belong.
- `agent/superextra_agent/instructions/research_lead.md:71–86` — final-report requirements; the candidate cleanup is removing lines 81–86.
- `docs/agent-research-depth-summary-2026-04-28.md` — the eval-driven methodology the V3 dataset was produced under.
