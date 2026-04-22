# Agent Simplification — Follow-up Plan

> Planned 2026-04-22 after the simplification pass (`docs/agent-simplification-report-2026-04-22.md`), a post-landing review (`docs/agent-simplification-followups-plan-review-2026-04-22.md`), and a live deadness test for A2's fallback path. Deletion-first / hardening-first discipline continues — no new architectural layers unless a direct change doesn't work.
>
> **Plan history note:** an earlier draft of this document descoped A2 ("verify first, probably keep the fallback") and routed B2 through markdown-link citations to avoid `_tool_sources` state plumbing. After instrumenting the fallback and running three varied live queries (see A2 §Evidence), the fallback proved empirically dead — zero contributions across 7 invocations. That frees B2 to use structured state cleanly, because there's nothing to break when we delete the fallback. The plan below reflects that revised shape.

## Context

The 6-phase simplification pass shipped clean. The post-landing review surfaced two quality regressions that predate the refactor but got amplified by it (TripAdvisor fail-open on low-confidence matches; review-heavy runs losing user-visible sources), plus a set of minor structural cleanups flagged in the simplification report itself. This plan groups them into three shippable PRs, ordered so the smallest / lowest-risk changes go first.

Explicit non-goals:

- No changes to the Phase 5 gap-researcher gate here. It's flagged as a separate P1 followup in the report and will be decided after more real-user traffic.
- No new template-partial / include infrastructure. Markdown files stay self-contained.
- No new feature flags or config surfaces.

## PR A — One-liners and hardening

Lowest risk, no behavior surprises, ship first.

### A1. Loosen the chart requirement

**Why.** Current `synthesizer.md:40-56` says "This is a core deliverable" and "Skip only if genuinely no numerical data exists." That wording biases the model toward producing charts even for qualitative queries (Q2's guest-sentiment stress run still emitted a pie chart of review-driver categories — defensible, but the same wording on a purely qualitative query can produce contrived / fabricated numeric splits).

**Change.** In `agent/superextra_agent/instructions/synthesizer.md`, replace:

```
When findings include numerical data for comparison, emit chart specs as
fenced code blocks — inline, where they support the narrative. This is a
core deliverable. Skip only if genuinely no numerical data exists.
```

with:

```
When findings include enough numerical data to meaningfully strengthen a
comparison or trend claim, emit chart specs as fenced code blocks — inline,
where they support the narrative. Prefer no chart over a contrived one; if
the data is purely qualitative, a single data point, or already well
conveyed in a small table, skip the chart.
```

**Verify.** Re-run two live queries — one quantitative (pricing comparison) should still chart; one purely qualitative ("what's the service culture at X?") should skip cleanly. No code tests required.

---

### A2. Delete the dead `extract_sources_from_text` markdown-link fallback

**Why.** `_append_sources` is gone; specialists no longer emit `## Sources` blocks; synth's instruction tells it to _preserve_ specialist citations, not invent its own. The fallback in `firestore_events.py:365-381` with its two call sites exists only for a legacy pattern nobody writes anymore.

**Evidence (live deadness test, 2026-04-22).** Instrumented `extract_sources_from_text` to log every call, input length, extracted URL count, and whether any extracted URL reached the terminal session `sources[]`. Ran three live queries covering the shapes most likely to exercise the fallback:

| Query                                                  | Grounding sources | Fallback calls | URLs extracted | Contribution to terminal `sources[]` |
| ------------------------------------------------------ | ----------------: | -------------: | -------------: | -----------------------------------: |
| Pricing comparison (quantitative, google_search-heavy) |                20 |              3 |              0 |                                    0 |
| Guest sentiment (review tools, zero grounding)         |                 0 |              2 |              0 |                                    0 |
| Broad Nordic landscape                                 |                45 |              2 |              0 |                                    0 |

**7 invocations, 0 URL extractions, 0 contributions.** The fallback executes on the happy path (each specialist + the synth call it when grounding is empty) but finds nothing to parse because none of today's agents embed inline `[title](url)` citations in prose. Raw data at `/tmp/a2_deadness_result.json`.

**Change.**

- Delete `extract_sources_from_text` and `_MD_LINK_RE` in `agent/superextra_agent/firestore_events.py`.
- In `_map_specialist` and `_map_synthesizer`, drop the text-fallback branch — keep only `extract_sources_from_grounding(event)`.
- Update `test_firestore_events.py` tests that exercise the text path.

**Verify.** pytest green; one live pipeline run; confirm `sources[]` count unchanged vs the pre-deletion baseline on the same query.

---

### A3. Format-safe template substitution for synth + gap

**Why.** `_synthesizer_instruction` (`agent.py:76`) and `_gap_researcher_instruction` (`specialists.py:252`) call `str.format(**values)` with specialist outputs as values. If any specialist output contains a literal `{` (JSON snippet, URL template, code sample — all realistic now that specialists describe quantitative data more often), `.format()` raises `KeyError`. `follow_up.md` already migrated to `.replace()` for this exact reason, with a comment explaining it.

This is defensive hardening, not new logic.

**Change.** In both `_synthesizer_instruction` and `_gap_researcher_instruction`, replace the single `.format(**values)` call with the `.replace(f"{{{key}}}", value)` loop pattern already used by `_follow_up_instruction:294-305`.

**Tests.** Existing instruction-provider tests in `test_instruction_providers.py` cover substitution. Add one test per provider that feeds a value containing a literal `{` and asserts no `KeyError`.

**Verify.** pytest green.

---

## PR B — Review pipeline quality

Addresses the two P1s from the review. Review-heavy runs today can both (a) act on low-confidence TripAdvisor matches without the LLM knowing and (b) surface zero sources to the user despite having used TripAdvisor + Google Reviews APIs.

### B1. Make the TripAdvisor tool contract honest about low-confidence matches

**Why.** `find_tripadvisor_restaurant` (`tripadvisor_tools.py:98-180`) already computes `match_confidence = "high" | "low"` from an address-match score, then returns `status: "success"` regardless of the result. The reviewer verified (and a re-read of `review_analyst.md:27-30` confirms) that the **prompt already tells the LLM** to "Check `match_confidence` — if 'low', review the `candidates` list and only retry with a different name phrasing if none of the candidate addresses match the Places address." So the prompt isn't blank; the tool is dishonest. Fixing the tool is the root cause; the prompt is a symptom-level workaround the LLM has to remember to apply.

**Change — tool contract only.** In `tripadvisor_tools.py`, when `match_confidence == "low"`, return `status: "low_confidence"` (not `"success"`), keeping the ranked `candidates` list in the return so the LLM can still reason about the ambiguity. That's it. No prompt edits — the existing guidance becomes truthful once the signal it checks is reliable.

**Tests.** Add a `test_tripadvisor_tools.py` case: mock SerpAPI responses so address-match score falls below the 0.4 threshold; assert the tool returns `status: "low_confidence"`.

**Verify.** Live query against a restaurant whose name is ambiguous across cities (e.g. a common name in a different locale). Confirm the low-confidence path surfaces in logs and the specialist output acknowledges the uncertainty.

---

### B2. Provider-level attribution in terminal `sources[]` via structured tool state

**Why.** The current `sources[]` only carries URL-citable entries from grounding metadata. Review-heavy runs drive analysis through `TripAdvisor` (SerpAPI) and `Google Reviews` (Apify), both structured APIs that never surface `grounding_metadata`. Result: review-heavy runs emit `sources=[]`, contradicting the product promise of "show what was used." The live deadness test above confirmed this: the guest-sentiment query returned zero grounding sources and zero fallback contributions → users see an empty source list despite two review providers being queried.

**Why Option S (structured state) and not Option M (markdown citations).** We considered having `review_analyst` emit provider URLs as markdown citations, relying on the A2 fallback to pick them up. Three problems: (1) it depends on the LLM reliably formatting markdown citations, (2) it forces us to keep the A2 fallback alive indefinitely, and (3) hallucinated URLs would land as "sources." Option S writes deterministically from the tool boundary the moment a tool call succeeds — no LLM formatting dependency, no fallback to preserve, no hallucination risk.

**Correction to an earlier draft.** A previous draft of this plan claimed the review tools "already have access to `tool_context`." Not true — verified in `tripadvisor_tools.py:185-257` and `apify_tools.py:43-109`. Adding `tool_context` as a parameter is a one-line signature change per tool; ADK auto-injects it when declared. This is not a new state channel — `tool_context.state` is the documented ADK pattern for exactly this use case, and the repo previously used the same idiom for `_web_search_queries` before Phase 1 deleted it.

**Change.**

- In `tripadvisor_tools.py`:
  - `find_tripadvisor_restaurant`: accept `tool_context`. On high-confidence match (`status="success"`), preserve the TripAdvisor place URL. SerpAPI's TripAdvisor Search returns a `link` field per place (currently dropped at lines 89-96 where we build the candidate list) — capture it and write `{title: "TripAdvisor — <restaurant name>", url: <link>, domain: "tripadvisor.com"}` to `tool_context.state["_tool_sources"]`. Skip on `low_confidence` (see B1).
  - `get_tripadvisor_reviews`: accept `tool_context`. On success, either append to the existing `_tool_sources` entry (e.g. annotate review count) or add a sibling entry with the same URL but a title like "TripAdvisor (N reviews analysed)". Dedup by URL so we don't double-count a single provider.
- In `apify_tools.py:get_google_reviews`: accept `tool_context`. On success, write `{title: "Google Reviews (N reviews analysed)", url: <restaurant page URL>, domain: "google.com"}`. The URL comes from the Places enricher's `places_context` (Places API returns `googleMapsUri`/`reviewsUri`) — verify the enricher surfaces it; if not, one-line add to the enricher template.
- In `agent/worker_main.py`, extend the event loop: for every event whose `state_delta` carries a `_tool_sources` list, drain it through the existing `_merge_source` + `specialist_sources_seen` accumulator. Three lines.

**Why not a new payload field.** Users see "resources used," not an internal taxonomy. The UI already renders `sources[]`; repurposing it for provider attribution needs zero frontend changes and zero session-doc shape changes.

**Tests.**

- Unit: for each of the three review tools, assert that after a successful call, `tool_context.state["_tool_sources"]` contains the expected provider entry (title, url, domain).
- Worker: extend `test_sources_accumulate_across_specialist_events` with a case where a specialist event's `state_delta` carries `_tool_sources`; assert the entries land in the final `sources[]`.

**Verify.** Re-run Q2 from the stress test (review-sentiment, currently `sources=0`). Confirm the new run returns ≥ 1 entry with `domain: "tripadvisor.com"` and ≥ 1 with `domain: "google.com"`.

---

## PR C — Structural dedup

Catalog consolidation. Bigger surface-area touch than A/B, but mechanical — no behavior change expected. Group in one PR since the sub-items pull in the same files.

### C1. One source of truth for the specialist catalog

**Why.** Five structurally identical mappings across three files:

- `agent.py:_SPECIALIST_RESULT_KEYS` — orchestrator-instruction injection of existing findings (name → label).
- `agent.py:_FALLBACK_SECTIONS` — `_build_fallback_report` stitch order (output_key → label).
- `specialists.py:_SPECIALIST_CONFIGS` — specialist factory inputs (name + description + output_key + thinking_config).
- `specialists.py:_ROLE_TITLES` — role-title string injected into specialist instructions.
- `specialists.py:_SPECIALIST_OUTPUT_KEYS` — gap-gate lookup (name → output_key).
- `firestore_events.py:AUTHOR_TO_OUTPUT_KEY`, `OUTPUT_KEY_TO_LABEL` — event-mapper lookups.

Every new specialist has to update at least four of these. AUTHORING.md already documents the burden as an acknowledged drift risk.

**Change.** Create `agent/superextra_agent/specialist_catalog.py` exporting a single list of `Specialist` records (a dataclass or `NamedTuple` with fields: `name`, `brief_key`, `output_key`, `label`, `role_title`, `description`, `thinking_config`, `author`). Derive every existing map from this list:

```python
# Example derivations (not final code):
AUTHOR_TO_OUTPUT_KEY = {s.author: s.output_key for s in SPECIALISTS}
OUTPUT_KEY_TO_LABEL   = {s.output_key: s.label for s in SPECIALISTS}
SPECIALIST_OUTPUT_KEYS = {s.name: s.output_key for s in SPECIALISTS if s.brief_key}
FALLBACK_SECTIONS      = [(s.output_key, s.label) for s in SPECIALISTS]
ROLE_TITLES            = {s.name: s.role_title for s in SPECIALISTS}
```

Then update each of the five sites above to import / derive from the catalog rather than hold its own copy. The review_analyst and dynamic_researcher_1 specialists (which have special tools / instruction names) stay in the catalog with the extra fields.

Gap researcher stays separately constructed — it's not a catalog entry — but imports the catalog when building its instruction key list (see C2).

**Tests.** A catalog invariant test: every specialist constructed via `_make_specialist` appears in `SPECIALISTS`; every `SPECIALISTS` entry has a corresponding factory call. Keeps catalog + factory in sync automatically.

**Verify.** Full pytest; one live E2E; confirm no regression in specialist behavior, firestore event shapes, or orchestrator prompt content.

---

### C2. Merge `_SYNTHESIZER_KEYS` and `_GAP_RESEARCHER_KEYS`

**Why.** `agent.py:_SYNTHESIZER_KEYS` and `specialists.py:_GAP_RESEARCHER_KEYS` overlap 100% except for the trailing gap-result key.

**Change.** After C1, derive both from the catalog: e.g. `_SPECIALIST_OUTPUT_KEY_LIST = [s.output_key for s in SPECIALISTS]`, then `_SYNTHESIZER_KEYS = ["places_context", "research_plan", *_SPECIALIST_OUTPUT_KEY_LIST, "gap_research_result"]` and `_GAP_RESEARCHER_KEYS = _SYNTHESIZER_KEYS[:-1]`.

**Verify.** Folded into C1 verification.

---

### C3. Unify Gemini client construction

**Why.** `_FAST_MODEL` in `agent.py:28-36` hand-rolls the `vertexai + location="global" + retry` wiring that `specialists.py:_make_gemini` already encapsulates for the 3.1 models. Silent drift source.

**Change.** Move `_make_gemini` to a more shared location (either keep in `specialists.py` and re-export, or move to `gemini.py` adjacent). Have `_FAST_MODEL` call `_make_gemini("gemini-2.5-flash", force_global=True)` — adding a `force_global` flag if Gemini 2.5 is already global-only (in which case the 3.1 branch in `_make_gemini` can apply by default to any model passed to it).

**Tests.** Existing specialist/agent construction tests.

**Verify.** Folded into C1.

---

### C4. Rename `dynamic_result_2` → `gap_research_result`

**Why.** Gap researcher's output key is `dynamic_result_2` — a leftover name from when it was framed as a "second dynamic researcher." It is no longer dynamic; the synth and orchestrator docs refer to it as gap research. Clarity-only rename.

**Change.** Rename across:

- `specialists.py:make_gap_researcher` `output_key="gap_research_result"`.
- `_SYNTHESIZER_KEYS` (agent.py), `_GAP_RESEARCHER_KEYS` (specialists.py) — both updated via C2's derivation.
- `firestore_events.py:AUTHOR_TO_OUTPUT_KEY` and `OUTPUT_KEY_TO_LABEL`.
- `agent/superextra_agent/instructions/synthesizer.md`: the `{dynamic_result_2}` placeholder in the "Additional Research 2" line becomes `{gap_research_result}` with a rephrased label ("Gap research").
- `agent.py:_FALLBACK_SECTIONS` — update the label at the same time.
- `test_gap_researcher.py`, `test_instruction_providers.py`, `test_worker_main.py` — any string refs.

**Tests.** Existing tests should all still pass after the rename. A grep test that `dynamic_result_2` does not appear in the repo outside of git history is a reasonable guardrail.

**Verify.** Folded into C1.

---

## Explicitly deferred

- **Template-partial / include system for prompt dedup.** Markdown files stay self-contained — include-resolver overhead is not worth the ~35 lines of remaining duplication.
- **Phase 5 gap-gate revisit.** Own decision after observing real-user traffic for a week.
- **Router-as-function (not LlmAgent).** Too large for this round; evaluate separately.
- **Enricher + orchestrator merge.** Same.
- **`dynamic_researcher_1` usage audit.** Worth doing after C1 lands, since telemetry questions are easier when the catalog is consolidated.
- **Chart-fence TTS/follow-up filtering.** Only if real traffic shows audible noise on read-aloud or degraded follow-up quality.

## Critical files

- `agent/superextra_agent/instructions/synthesizer.md` (A1)
- `agent/superextra_agent/firestore_events.py` (A2, C1)
- `agent/superextra_agent/specialists.py` (A3, C1, C2, C3, C4)
- `agent/superextra_agent/agent.py` (A3, C1, C2, C3, C4)
- `agent/superextra_agent/tripadvisor_tools.py` (B1, B2)
- `agent/superextra_agent/apify_tools.py` (B2)
- `agent/superextra_agent/instructions/context_enricher.md` — only if `places_context` doesn't already carry `googleMapsUri` (check first; likely untouched)
- `agent/worker_main.py` (B2)
- New: `agent/superextra_agent/specialist_catalog.py` (C1)
- Tests: `test_firestore_events.py`, `test_tripadvisor_tools.py`, `test_apify_tools.py`, `test_worker_main.py`, `test_gap_researcher.py`, `test_instruction_providers.py`

## Verification per PR

Identical gate for each:

1. `cd agent && PYTHONPATH=. .venv/bin/pytest tests/` — green.
2. `npm run test` (Vitest) — green.
3. `cd functions && npm test` — green (probably irrelevant; still run).
4. `npm run lint` + `npm run build` — 0 errors.
5. Push → Firebase deploy.
6. Live E2E via `E2E_QUERY=<varied> tests/e2e_worker_live.py` — ≥ 1 query per PR, PR B targets the guest-sentiment query that caught the sources-0 issue.
7. For A1 (instruction change), run both a quantitative and a qualitative query and compare chart emission.

## Recommended order

A → B → C. Each PR stands alone; A is the safest warmup, B addresses the user-visible regressions, C is the bigger refactor and benefits from A/B already being verified.

## What I'd defer inside these PRs if time is tight

- C3 (Gemini unification) can fall out of scope if C1 gets tangly — it's cosmetic.
- A1 is a single-line instruction change and can ship even if A2/A3 slip.
- B1 and B2 can ship as separate PRs if the tool-state plumbing for B2 turns out to touch more than expected; B1 is a pure tightening either way.
