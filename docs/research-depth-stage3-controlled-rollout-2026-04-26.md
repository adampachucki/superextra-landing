# Stage 3 — controlled-rollout amendments

A second review of the Stage 3 results doc raised seven points; all verified, all accepted. None changes the ship decision. Five tighten framing; two close real artifact gaps.

## What the reviewer got right (verified)

| #   | claim                                                                 | verification                                                                                                                                                                                         |
| --- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | "all 6 gates PASS, V2.3 ships" overstates a mixed-but-positive result | The 6 gates technically pass on stated criteria, but evidence is mixed (rep 3 collapse, V2.1 still better on sliwka q1, lower Warsaw faith/spec). "Controlled rollout" is more honest.               |
| 2   | Operator-subagent transcripts under-artifacted                        | Confirmed: `pairwise-verdicts-2026-04-25.md` has Rounds 1–5 (only Stage 2 V0-vs-V2.3 monsun q2 from Stage 3). Missing 9 Stage 3 operator transcripts (Phase B tiebreaker + Phase C ×3 + Phase D ×5). |
| 3   | "Only instruction files swapped" is misleading                        | Confirmed via `git status`: `agent.py` and `specialists.py` also modified — `SUPEREXTRA_INSTRUCTIONS_DIR` env-fallback (2-line diff each, harness support added during Stage 1).                     |
| 4   | "V2.3 generalizes cleanly to non-Polish" overstates                   | Holdout is 5 queries × 1 Berlin venue × 1 rep. Functional + no source bleed is a real finding; "generalizes cleanly" is too strong. Soften headline; keep nuanced body.                              |
| 5   | Gate #6 name "multi-topic robustness" is misleading                   | Tested single-turn multi-bucket synthesis, NOT actual multi-turn follow-up. Rename to "single-turn multi-topic synthesis robustness."                                                                |
| 6   | V2.3 may trade focus for breadth                                      | Berlin HQ5 confirms this. Real product risk. Add explicit post-ship monitoring item.                                                                                                                 |
| 7   | Faithfulness still unresolved                                         | Warsaw faith 4.00 → 3.60 (Gemini, noisy). V2.3 improves research depth ≠ V2.3 improves quality across the board. Frame faithfulness as separate ongoing risk.                                        |

## Action plan — 5 steps, can execute in ~30 min

### A. Append Stage 3 operator transcripts to the verdicts file

Append a "Round 6 — Stage 3 operator-subagent verdicts" section to `docs/research-depth-pairwise-verdicts-2026-04-25.md` containing:

- Phase B monsun q1 V0 rep 1 vs V2.3 rep 3 tiebreaker → `V2_3_COMPETENTLY_NARROWER`
- Phase C ×3 showdowns (V2.1 vs V2.2 vs V2.3 on monsun q2, sliwka q1, bar_leon q3) → 3 rankings
- Phase D ×5 holdout operator pairwise (HQ5×Warsaw, HQ1×Warsaw, HQ3×Warsaw, HQ5×Berlin, HQ2×Berlin) → 5 verdicts

For each: include the full subagent verdict text (already exists in this conversation's output) so the reasoning + spot-checks are auditable.

### B. Update Stage 3 doc wording

Edit `docs/research-depth-stage3-validation-2026-04-26.md`:

1. **Headline**: "all 6 ship gates PASS. V2.3 ships." → "All 6 ship gates pass on their stated criteria. V2.3 promoted to production as a **controlled instruction rollout** — the evidence is materially stronger than Stage 2 and addresses the overfitting concern, but residual risks remain (see Limitations)."
2. **Berlin headline**: "V2.3 generalizes cleanly to a non-Polish market without source-priors bleed" → "V2.3 stays functional on a non-Polish venue without Polish source bleed. Tested on n=1 Berlin venue × 5 queries × 1 rep — informative but not validation of cross-market generalization."
3. **Gate #6 rename**: "Multi-topic robustness" → "Single-turn multi-topic synthesis robustness." Add note: "Multi-turn / follow-up behavior is NOT tested by this gate; that's a separate eval."
4. **Add explicit "controlled rollout" caveat** at the top: this ship is contingent on monitoring (see post-ship plan below).

### C. Clarify production code change scope

Add a section to Stage 3 doc:

> ## Production code changes shipped with V2.3
>
> Two instruction files (the V2.3 ship target):
>
> - `agent/superextra_agent/instructions/research_orchestrator.md`
> - `agent/superextra_agent/instructions/specialist_base.md`
>
> Plus two pre-existing harness-support changes that have been in the working tree throughout the project (added during Stage 1 to enable subprocess-per-variant runner; both are 2-line env-fallback diffs that are byte-identical when `SUPEREXTRA_INSTRUCTIONS_DIR` is unset):
>
> - `agent/superextra_agent/agent.py:36-37` — `_dir_override = os.environ.get("SUPEREXTRA_INSTRUCTIONS_DIR")`
> - `agent/superextra_agent/specialists.py:23-24` — same pattern
>
> These env-override changes are required for the eval harness to function but are zero-behavior-change in production (when env var is unset, code path is identical to pre-change). Including them in the same commit as the V2.3 instruction files is correct — they are the supporting infrastructure for any future eval round.

Replace the misleading "Not modified: all other agent code" line with this section.

### D. Add post-ship monitoring plan

Add to Stage 3 doc:

> ## Post-ship monitoring
>
> V2.3 trades narrower-but-focused for broader-but-sometimes-sprawling. Two specific risks to monitor:
>
> 1. **Focus loss on prioritization queries.** When users ask "what should I do this week" or "what's the ONE change," V2.3 may sprawl. Sample 10–20 production answers in the first 2 weeks; specifically check responses to single-decision prompts.
> 2. **Faithfulness regression.** Warsaw holdout shows Gemini-judged faith 3.60 vs V0's 4.00. Operator reviews favored V2.3 but Gemini is noisy. Sample the same 10–20 answers and spot-check named figures/dates against cited sources. If unsupported-claim rate rises above ~10%, re-investigate.
> 3. **Berlin / non-Polish behavior.** Not gated by ship, but if non-Polish queries become common, log them and review separately. V2.3 was not validated for cross-market.

### E. Run agent test suite before final commit

```
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v
```

Two production code files are modified (the env override). The test suite should pass without those env changes affecting anything (the env-fallback is byte-identical when unset). If any test fails, investigate before committing.

## What stays the same

- Ship V2.3. Decision unchanged.
- The 6 ship gates and their pass results stay correct on their stated criteria.
- All number tables in the Stage 3 doc are verified-accurate (already audited).
- Production file replacements (`research_orchestrator.md`, `specialist_base.md`) stay in place.

## What I'd push back on

Nothing material. Reviewer's critique is well-founded. Item #4 (Berlin holdout small) borders on being unfair given the explicit "exploratory" framing throughout the doc — the only fix needed is softening the _headline_ sentence. The body of the doc was already honest about Berlin's exploratory status.

## Estimated time

- (A) Transcripts: ~20 min — large copy-paste from this conversation
- (B) Wording fixes: ~10 min — 4 specific edits
- (C) Code-scope clarification: ~5 min — replace one line, add one section
- (D) Monitoring plan: ~5 min — append section
- (E) Tests: ~5 min wall-clock if they pass; investigate if any fail

Total: ~45 min. No new compute, no new agent runs.
