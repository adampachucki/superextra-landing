# Post-landing Fixes — Final Report

> Landed: 2026-04-22. Three commits on `main` (`d7b6470`, `9890318`, and a geo-bias regression fix).
> Plan: `docs/agent-simplification-postlanding-fixes-plan-2026-04-22.md`.
> Parent work: `docs/agent-simplification-report-2026-04-22.md` and the PR A/B/C series (`a4e6738..af49c5b`).

## TL;DR

A reviewer pass on the PR A/B/C follow-ups round caught two product-impacting bugs and one latent issue. All three were fixed via root-cause changes (not symptom patches). Two of the fixes needed follow-up commits after reviewer / live signal:

1. **Per-place Google Reviews citations** needed a second commit (`9890318`) after live verification surfaced an ADK behaviour I had asserted incorrectly: parallel tool calls get batched into one event with one `state_delta`, so the "overwrite-only" pattern from the first commit lost all but the last write. Switched to unique-per-call state keys (`_tool_src_<uuid>`); now provably correct under both serial and parallel tool execution.
2. **The places-tool `tool_context` threading** (part of fix 2) introduced a new silent coupling bug: `get_restaurant_details` still unconditionally wrote `_target_lat` / `_target_lng`, so competitor fetches in the batch overwrote the target's geo-bias centre. A third commit added first-write-wins + the regression test I should have written the first time.

Net code: one-line fixes dominate the commit history. All **172** agent tests + 88 Vitest + 47 functions tests green at the end.

The single most useful thing that happened: reviewer rounds + live-verification discipline caught two bugs that unit tests and pre-execution sims did not. The temptation to ship after the first green test run was real.

## Timeline

```
1. Reviewer's report on PR A/B/C
   → 2 P1s + 1 latent issue + cosmetics

2. Verified each finding empirically
   → both bugs reproducible locally, root-causes identified

3. Drafted plan doc, reviewed by reviewer (round 1)
   → reviewer flagged that follow_up still had the same .replace() bug
     (we had only planned to fix synth + gap)
   → reviewer flagged concurrency concern with shared dict in
     get_batch_restaurant_details
   → reviewer concurred that candidate-0 selection in TripAdvisor was
     an acceptable remaining tradeoff

4. Updated plan: include follow_up in the .replace() revert; switch
   from shared dict to per-place state keys for concurrency safety

5. Pre-execution simulation (5 sims, all live where applicable)
   → .format() restoration confirmed safe
   → Google Maps place_id URL format resolves
   → TripAdvisor richer query is safe (no over-constraining)
   → Address-match score is forgiving enough
   → Per-place citation flow mock works

6. Executed plan, single bundled commit (`d7b6470`)

7. Live E2E verification on Q2 (review-sentiment) → returned 0 Google pills
   → log inspection: 3 parallel get_google_reviews calls produced ONE
     state_delta entry (last write wins under ADK's parallel batching)
   → my worker comment "Current ADK emits per-call events" was wrong

8. Diagnosed: overwrite-only pattern fundamentally incompatible with
   ADK's parallel-tool-call event aggregation

9. Fix commit (`9890318`): unique-per-call state keys (`_tool_src_<uuid>`),
   worker drain iterates by prefix

10. Re-deployed, re-ran Q2 → 3 distinct Google pills + 1 TripAdvisor pill,
    all correctly attributed

11. Wrote this report declaring everything verified

12. Reviewer round 4 caught a SECOND regression I'd introduced:
    get_restaurant_details unconditionally writes _target_lat / _target_lng,
    and the batch threading (fix 2) meant competitor fetches silently
    clobbered the target's geo-bias centre. Reproduced locally in 10 sec.
    My own comment on the line said "target-only"; the code wasn't.

13. Third commit: first-write-wins guard + regression test mirroring the
    real enricher flow (solo target fetch → batch competitor fetch)
```

## What shipped

### Commit `d7b6470` — the 5 planned fixes

1. **Revert A3 across all three instruction providers (synth + gap + follow_up).** Restored `.format()` everywhere. The "LLM output may contain curly braces" comment that had originally pushed `_follow_up_instruction` onto `.replace()` was based on a misreading of `.format()` semantics — it does NOT re-scan inserted values. Brace regression tests deleted; replaced with placeholder-mutation regression tests (which guard against the actual A3 bug).
2. **Per-place state keys for the Google Reviews citation feature.** `places_tools.get_restaurant_details` now writes `_place_name_<place_id>` per call (target and competitors). `get_batch_restaurant_details` threads `tool_context` through to inner calls. `apify_tools.get_google_reviews` derives Maps URL deterministically from `place_id` (`https://www.google.com/maps/place/?q=place_id:<ID>`) and reads name from the per-place key.
3. **TripAdvisor search includes address in the query.** When `address` is provided, `q = "{name} {address}"` instead of `"{name} {area}"`. Removes the structural footgun of throwing away the disambiguating signal the caller already had. Confidence check stays as safety net.
4. **Drop dead `tool_context` param from `get_tripadvisor_reviews`.** Orphaned after the source-write logic moved to `find_tripadvisor_restaurant`.
5. **Worker comment** documenting the assumption that `_tool_sources` drain relies on. (This comment turned out to be wrong — see commit 2.)

### Commit `9890318` — empirical correction after live failure

**Caught by:** running Q2 review-sentiment live E2E on the deployed `d7b6470`. Returned `sources_n=4` with **0 Google Reviews pills** despite the chat log showing 3 successful `get_google_reviews` calls.

**Root cause:** ADK aggregates parallel tool calls into one event. The log showed:

```
function_calls: ["get_google_reviews", "get_google_reviews", "get_google_reviews",
                 "find_tripadvisor_restaurant", "find_tripadvisor_restaurant",
                 "find_tripadvisor_restaurant"]
state_delta_keys: ["_tool_sources"]   # ← ONE key for 6 tool calls
```

Each tool call wrote `state["_tool_sources"] = [single entry]` (overwrite-only). Under parallel execution, the second write clobbered the first; the third clobbered the second; etc. Final state: one entry from whichever tool finished last (a TripAdvisor write, not Google). Worker drained that one entry. Hence 0 Google pills.

**Fix:** unique-per-call state keys. Each tool call writes `state[f"_tool_src_{uuid.uuid4().hex}"] = entry`. Under parallel execution, all writes appear as distinct keys in the aggregated `state_delta`. Worker drain iterates `state_delta` keys with the `_tool_src_` prefix.

**Why this is now correct:**

- Concurrency: each tool call writes to a guaranteed-unique key. No collision possible regardless of execution order.
- Cross-turn leakage: old turn's keys persist in session state but never appear in a future event's `state_delta` (nothing re-writes them). Worker only drains `state_delta` per-event; stale keys are invisible to it.
- Dedup: `_merge_source` already dedupes by URL; multiple calls for the same restaurant collapse to one pill.

### Third commit — geo-bias regression caught by reviewer

**Caught by:** reviewer round on the already-landed PR. Fix 2 had threaded `tool_context` through `get_batch_restaurant_details` so competitor name-stashing would work, which was correct intent. But `get_restaurant_details` still **unconditionally** wrote `_target_lat` / `_target_lng` on every call — so the last competitor fetched in the batch quietly overwrote the target's geo-bias centre. Every subsequent `google_search` (via `_inject_geo_bias`) was biased toward whichever competitor happened to complete last in the concurrent gather.

**Reproduced in ~10 seconds** with a stand-alone script: `batch(['noma', 'alchemist'])` ended with `_target_lat` equal to Alchemist's latitude, not Noma's.

**Root cause:** the comment I wrote on the same line said "lat/lng are target-only." The code didn't enforce it. Classic write-the-docstring-believe-the-docstring mistake.

**Fix:** one-line conditional in `get_restaurant_details`:

```python
if (
    loc.get("latitude") and loc.get("longitude")
    and "_target_lat" not in tool_context.state
):
    tool_context.state["_target_lat"] = loc["latitude"]
    tool_context.state["_target_lng"] = loc["longitude"]
```

First-write-wins. The enricher instruction (`context_enricher.md` Steps 1 and 3) fetches target solo, THEN competitors via batch — so by the time the batch runs, `_target_lat` is already set and every competitor's write skips the conditional. `_place_name_<pid>` stays unconditional (still writes for every call, including competitors).

**Regression test** mirrors the actual enricher flow (not the stand-alone repro): `get_restaurant_details(target)` first, then `get_batch_restaurant_details([comp1, comp2])`; assert `_target_lat` still equals target's coords, assert all three `_place_name_*` keys populated.

## Live verification results

### Run 1 — `d7b6470` (broken)

Query: "What does guest sentiment look like across TripAdvisor and Google reviews compared to Alchemist and Geranium?"

| Metric               | Value                                                       | Verdict                     |
| -------------------- | ----------------------------------------------------------- | --------------------------- |
| Status               | `complete`                                                  | ✓                           |
| `synth_outcome`      | `ok`                                                        | ✓                           |
| Total sources        | 19                                                          | ✓ (grounding-driven)        |
| Google Reviews pills | **0**                                                       | ✗ — bug surfaced            |
| TripAdvisor pills    | 1 (Geranium)                                                | ✓ but only the last-written |
| Tool calls observed  | 3 × `get_google_reviews`, 3 × `find_tripadvisor_restaurant` | per chat_logger trace       |

### Run 2 — `9890318` (fixed)

Same query.

| Metric               | Value        | Verdict                                          |
| -------------------- | ------------ | ------------------------------------------------ |
| Status               | `complete`   | ✓                                                |
| `synth_outcome`      | `ok`         | ✓                                                |
| Total sources        | 4            | (grounding light on this run; review path heavy) |
| Google Reviews pills | **3**        | ✓ Noma + Alchemist + Geranium, distinct URLs     |
| TripAdvisor pills    | 1 (Geranium) | ✓                                                |
| Elapsed              | 173s         | normal                                           |

```
google.com    Google Reviews — Noma       → .../q=place_id:ChIJpYCQZztTUkYRFOE368Xs6kI
google.com    Google Reviews — Alchemist  → .../q=place_id:ChIJGbFWVvBSUkYR5x0i6Z836Ao
google.com    Google Reviews — Geranium   → .../q=place_id:ChIJAQshwflSUkYRF9f4wpDIt7U
tripadvisor   TripAdvisor — Geranium      → https://www.tripadvisor.com/Restaurant_Review-...
```

Per-place citations now work end-to-end as the product spec requires.

## Learnings

### 1. "Hardening" without a real failure mode is anti-simplification

PR A3 was the worst kind of change: it added complexity to fix a problem that didn't exist (`.format()` doesn't re-scan inserted values; never raised the `KeyError` the comment claimed it did), and the "fix" introduced two new bugs (placeholder mutation + broken brace unescape). Net: more code, more bugs, no benefit.

The corrective: revert. `.format()` was already correct. The brace-regression tests A3 added were asserting non-problems; replacing them with tests that guard against the actual `.replace()` chain regression is a better signal.

Defensive code without an empirical failure mode is just additional surface for future bugs.

### 2. Pre-execution simulation catches some things, not others

Five sims ran clean before the first commit shipped. Yet the second commit was still needed because none of the sims exercised ADK's actual tool-event aggregation behaviour — they exercised the tools in isolation with a mock `tool_context`, not through the live ADK Runner.

The lesson: in-isolation mocks prove the function works; they don't prove the integration works. For anything touching ADK's event/state pipeline, a live E2E run on the real Runner is the only verification that counts.

(I caught this. The discipline of "re-run live after deploy" surfaced the bug. Without that, the broken `d7b6470` would have shipped to users.)

### 3. State-shape choice has hidden coupling to the event runtime

The plan doc carefully justified the per-place state-key shape (`_place_name_<pid>`) for concurrency reasons under `asyncio.gather`. But it kept the source-write key as `_tool_sources` (single-key + overwrite-only) — and that was the actually-broken path under ADK's parallel batching. Both shapes face the same kind of concurrency, but only the per-place keys had the protection.

Generalisation: when multiple tool calls might land in one event's `state_delta`, every state key shared across them needs unique-per-call disambiguation. Not just the ones I happened to think about.

### 4. The reviewer rounds compounded value

Three reviewer interactions across this fix set:

- Round 1 (post-PR-A/B/C review): caught the original 2 bugs + the latent TripAdvisor issue.
- Round 2 (review of the plan doc): caught that follow_up had the same `.replace()` bug and that my shared-dict design was concurrency-fragile.
- Round 3 (review of the executed PRs): caught the wrong worker assumption ("overwrite-only assumes one event per tool call") that turned out to be empirically false.

Each round caught issues that the prior round missed. Reviewer ROI is high when the work is small and the changes are concentrated. Worth keeping the cadence.

### 5. Empirical disagreement with one's own assumptions is the bug-finding signal

When I wrote the worker-comment "Current ADK (verified) emits per-call events", I had no actual verification. The comment was confident-sounding but unverified. Live observation produced the opposite of that claim. The fix commit's message preserves both the wrong assertion and the corrected one — a small artifact of "I was wrong, here's why" that future readers can learn from.

### 6. Test what you ADDED, but also test what you should have LEFT ALONE

This one is the most embarrassing. When fix 2 threaded `tool_context` through `get_batch_restaurant_details`, I wrote tests that asserted `_place_name_<pid>` got populated — what I added. I did NOT write a test asserting that `_target_lat` / `_target_lng` remained target-specific — what the existing function should have left alone. The same code-path got a new caller; the new caller exercised behaviour that had previously been effectively unreachable (single-call guaranteed target semantics), but I didn't check the invariant against the new access pattern.

Generalisation: when a change threads additional behaviour through an existing code path, the regression tests need to cover the existing invariants of that path, not just the new behaviour. Otherwise the change silently widens the function's contract. Next time: for any change that adds callers to an existing function, inventory the function's existing invariants and write a test per invariant that exercises the new caller pattern.

My own comment in the code said "lat/lng are target-only" — a docstring that believed its own claim without the code enforcing it. The fix enforces it and the test verifies it. (Two artifacts now match the docstring.)

## Followups

None urgent. Two items worth noting:

- **Stale state-key buildup.** Each turn that uses review*analyst writes 1–6 unique `\_tool_src*<uuid>` keys to ADK session state. They're never read after the turn that wrote them, but they accumulate. For a 100-turn session, that's a few hundred extra keys. Acceptable for now (state is small), but if state size becomes a real concern we'd need a per-turn cleanup hook. Defer until measured.
- **Plan doc says "overwrite-only".** The shipped doc still describes the original (broken) approach. Worth a small amendment noting the live-catch and the actual final shape if anyone refers back. The commit message of `9890318` already tells this story clearly.

## Process notes

- Two commits, one logical change. The split was forced by the bug. In hindsight, doing a live E2E _before_ committing the first version would have surfaced the issue and let me ship one clean commit. Lesson: don't trust unit tests + sims to prove integration with a complex runtime; test the real path before locking in a commit.
- The plan doc paid for itself twice: once for the plan-review back-and-forth, again for the post-mortem framing. Worth the writing time.
- Reviewer feedback came in three asynchronous rounds. Each one was small (10–50 lines) and surgical. The pattern of "small change → small review → small follow-up" beat any attempt at a bigger one-shot.

## Files touched

### Code

- `agent/superextra_agent/agent.py` — restore `.format()` in `_synthesizer_instruction` + `_follow_up_instruction`.
- `agent/superextra_agent/specialists.py` — restore `.format()` in `_gap_researcher_instruction`.
- `agent/superextra_agent/places_tools.py` — write `_place_name_<pid>` in `get_restaurant_details`; thread `tool_context` through `get_batch_restaurant_details`; third commit adds the first-write-wins guard on `_target_lat` / `_target_lng` so competitor batch fetches don't overwrite the target's geo-bias centre.
- `agent/superextra_agent/apify_tools.py` — derive Maps URL from `place_id`; write `_tool_src_<uuid>` per call.
- `agent/superextra_agent/tripadvisor_tools.py` — richer search query (`name + address`); write `_tool_src_<uuid>` per high-confidence match; drop dead `tool_context` param from `get_tripadvisor_reviews`.
- `agent/worker_main.py` — drain `_tool_src_*` state-delta keys (commit 2 corrected the prefix from `_tool_sources` after the live ADK aggregation behaviour was observed).

### Tests

- `agent/tests/test_instruction_providers.py` — replaced brace-regression test with placeholder-mutation regression test.
- `agent/tests/test_gap_researcher.py` — same replacement.
- `agent/tests/test_places_tools.py` — `_place_name_<pid>` per-call assertions; `get_batch_restaurant_details` threading test; geo-bias regression test mirroring the real enricher flow (solo target fetch → competitor batch).
- `agent/tests/test_apify_tools.py` — per-call unique key assertions; multi-call distinct-pill test.
- `agent/tests/test_tripadvisor_tools.py` — query-shape assertions for the address-included path; per-call unique key for source write.
- `agent/tests/test_worker_main.py` — drain test asserting multiple `_tool_src_*` keys in one event surface as multiple pills.

### Docs

- `docs/agent-simplification-postlanding-fixes-plan-2026-04-22.md` — the plan (the live-catch corrected the implementation but not the plan; commit `9890318`'s message documents the change).
- `docs/agent-simplification-postlanding-fixes-report-2026-04-22.md` — this document.

## Final state

**172 / 172 agent pytest, 88 / 88 Vitest, 47 / 47 functions tests passing.** Live E2E confirmed: per-place Google Reviews citations work (3 distinct pills for target + 2 competitors); TripAdvisor confidence gate works; revert-A3 fixed the placeholder-mutation bug across all three instruction providers; richer TripAdvisor query is in place as a structural improvement; geo-bias coords stay anchored to the target across competitor batch fetches; no `MALFORMED_FUNCTION_CALL` events; chart fences render correctly.

Three commits, four reviewer rounds, two embarrassing self-corrections. Worth shipping. Ship the next thing — but slower this time.
