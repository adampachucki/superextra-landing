# Lean agent cleanup — implementation review

**Date:** 2026-04-30
**Reviewing:** the implementation of `docs/lean-agent-cleanup-plan-2026-04-30.md` against the plan and against the lean-codebase goals.
**Status:** implementation is technically correct and ships safely. The lean goal of net-deletion was not achieved — see "LOC delta" below.

---

## Test status

All test suites green:

- 36 tests for the changed files (test_firestore_progress_hooks.py + test_firestore_events.py + test_gear_run_state.py): pass.
- Full agent suite (153 passed + 17 skipped — the skipped are live-API/eval tests requiring credentials): pass.
- Frontend suite (60 tests): pass.

---

## LOC delta — honest framing

| File                                                 | Before   | After    | Δ        |
| ---------------------------------------------------- | -------- | -------- | -------- |
| `agent/superextra_agent/firestore_events.py`         | 438      | 430      | **−8**   |
| `agent/superextra_agent/firestore_progress.py`       | 576      | 653      | **+77**  |
| `agent/superextra_agent/gear_run_state.py`           | 221      | 233      | **+12**  |
| `agent/scripts/redeploy_engine.py`                   | 330      | 372      | **+42**  |
| Prompts (`specialist_base.md` + `research_lead.md`)  | 49 + 124 | 50 + 124 | **+1**   |
| `agent/tests/test_firestore_progress_hooks.py` (new) | 0        | 135      | **+135** |
| `agent/tests/test_firestore_events.py`               | 222      | 218      | **−4**   |
| `agent/tests/test_gear_run_state.py`                 | 244      | 264      | **+20**  |
| **Production code total**                            |          |          | **+124** |
| **Including tests**                                  |          |          | **+275** |

**The plan estimated −25 to −55 production LOC. The implementation delivered +124 production LOC.**

The lean goal of net-deletion was not met. The plan's "delete ~150 lines from `firestore_events.py`" claim was wrong, and the implementer correctly identified that — the per-tool branching couldn't be deleted, only relocated. So `_map_function_call` became `map_tool_call` (renamed, made public, kept its body); `_map_function_response` became `map_tool_result`; new `map_tool_error` was added. The pill-shape logic stayed roughly the same size — it just moved from "called by `map_event` event-parser" to "called by typed hooks." Plus the typed hooks themselves are 80+ lines, the accumulator method adds 12, and the env-var preservation in the deploy script adds 42 lines (which wasn't in the original plan estimate at all — only added in review pass 3).

If "lean" was the primary metric, this work didn't deliver. The structural wins (one source of truth for pill shape, typed hooks own observation, Cloud Trace observability, citation discipline rule, env-var preservation) are real but came at +124 LOC.

---

## Item-by-item review

### Item 3 — citation rule (prompts) — clean ✅

Two files touched:

- `agent/superextra_agent/instructions/specialist_base.md:13-19` — adds one new bullet alongside the existing "Acknowledge gaps honestly" rule, naming the failure mode explicitly with the tool list (`google_search`, `fetch_web_content`, `get_*` tools) and the no-memory clause.
- `agent/superextra_agent/instructions/research_lead.md:75` — appends "Cite only sources that appear in this turn's tool or specialist results" to the existing rule #5.

Net +1 line. Clean, lean, on-spec.

**Minor nit:** the specialist_base wording is "If a source is not in tool results, do not cite it even if the URL or domain is familiar from memory." The plan's "even if you can recall the URL or domain from training data" was slightly more direct (training data being the actual mechanism), but the substantive rule is the same.

### Item 1 — Cloud Trace + env-var preservation — clean ✅ (with one minor concern)

`agent/scripts/redeploy_engine.py:172-194` adds `_deployment_env_vars(agent_engine)` that pulls existing env vars (both plain and secret) from the deployed engine. The deploy path at `:344-358`:

1. Calls `agent_engines.get(args.resource_name)` to fetch current state.
2. Extracts existing env vars via `_deployment_env_vars(existing)`.
3. Merges in `TRACE_ENV_VARS` (the two telemetry flags).
4. Passes the union to `existing.update(env_vars=...)`.

SecretRef round-trip verified against SDK source: `_agent_engines.py:1337-1340` routes SecretRef values back to `secret_env`, so secret env vars round-trip correctly.

The print statement `f"  env vars: preserving/updating {', '.join(sorted(env_vars))}"` shows only keys, not values — good for security.

**One concern:** the function reaches into `agent_engine._gca_resource.spec.deployment_spec` — private SDK attribute. Fragile to SDK upgrades. A two-line comment explaining "no public accessor exists for the deployment spec on the AgentEngine wrapper" would help future readers understand why.

### Item 2 — typed hook migration — works, but design deviated from plan

**Design deviation worth flagging.** The plan said "delete `_map_function_call` (~44 lines), `_map_function_response` (~95 lines), `narrate` detection (~11 lines)." The implementation kept all three function bodies and renamed/repurposed them as public callers (`map_tool_call`, `map_tool_result`, `map_tool_error`). This is actually a _better_ design — single source of truth for pill shape, callable from typed hooks — but it explains why the LOC numbers went the wrong direction.

#### Issues found

1. **`_state_for_tool` near-duplicates `_state_for_event`** at `firestore_progress.py:355-373` and `:377-393`. Two near-identical 15-line helpers do the same lookup pattern. They differ in:
   - `_state_for_event` has a `_is_nested_invocation` guard before the run_id fallback; `_state_for_tool` does not (intentional — typed hooks must propagate to nested AgentTool calls).
   - Inconsistent invocation_id handling: one assumes string, the other isinstance-checks.

   Could be deduped behind one helper that takes a context-with-`invocation_id`-and-`session` shape, or at least a comment noting the intentional differences.

2. **`map_tool_error` synthetic-response trick is fragile.** At `firestore_events.py:368-376`, it builds `synthetic_response = dict(args)` then sets `status="error"` and routes through `map_tool_result`. This works because _every_ current error branch in `map_tool_result` only reads `status` (not other response fields). If someone adds a new error branch that reads response-shape data, it will silently misbehave (because `args` shape ≠ response shape). Worth a `# WARNING: only check status here, args shape differs from response shape` comment in `map_tool_result`.

3. **Public `map_tool_*` functions have no docstrings.** `map_tool_call`, `map_tool_result`, `map_tool_error`, `_tool_row_id` are now part of the firestore_events public API (called from firestore_progress.py) but have no documentation. One-line each saying "called by FirestoreProgressPlugin's typed hooks to build pill rows" would help future readers.

4. **Edge case worth flagging:** `map_tool_error` for tools without an error branch in `map_tool_result` (e.g., `get_restaurant_details`, `find_nearby_restaurants`, `search_restaurants`, `get_batch_restaurant_details`) returns an empty list. The hook silently emits no pill. This is acceptable behavior — better than emitting a generic warning that might be wrong — but it's untested. If a Places-side tool starts failing consistently, no UX signal will appear. Worth a one-line note in `map_tool_error`'s docstring.

#### Things that landed correctly

- **`after_tool_callback` dedupe-pill guard.** Lines 482-484 in `firestore_progress.py`:

  ```python
  if isinstance(result, dict) and result.get("error"):
      return None
  ```

  Catches the agent-level `_on_tool_error` substitute case. Test `test_tool_error_agent_level_fallback_does_not_duplicate_pill` verifies it (`await_count == 1`).

- **`observe_typed_pill` is async but the dedupe decision is sync.** `gear_run_state.py:124-134` calls `accept_detail` (sync) before any `await` — so even though the method is `async def`, the dedupe happens atomically per asyncio's single-thread guarantee. Header docstring updated to reflect this.

- **AgentTool nested invocations propagate correctly.** Verified via `test_nested_tool_context_routes_by_run_id` (a tool_context with an unknown invocation_id falls back to the run_id-based lookup).

- **Eval helpers preserved.** `_iter_function_calls`, `_iter_function_responses`, `_get`, `_state_delta`, `_has_state_delta`, `extract_sources_from_grounding` all still in `firestore_events.py` (lines 64-95, 153-174, 392-411). The eval-side dependency in `agent/evals/parse_events.py:14-19` continues to import them.

- **Public ToolContext fields used.** `tool_context.invocation_id`, `tool_context.session`, `tool_context.function_call_id` — no reaches into `tool_context._invocation_context.*`.

#### Test coverage

All 5 plan-required tests are present (distributed across two files):

- ✅ `test_before_tool_google_search_writes_search_pill` (search pill)
- ✅ `test_before_tool_narrate_writes_note` + `test_narrate_tool_call_emits_note` (narrate note)
- ✅ `test_tool_error_fetch_web_content_writes_warning` (fetch_web_content error → warning pill)
- ✅ `test_map_event_ignores_tool_parts_after_typed_hook_migration` (no on_event_callback double-emission)
- ✅ `test_tool_error_agent_level_fallback_does_not_duplicate_pill` (no duplicate pill on tool exception)

Plus a useful extra: `test_observe_typed_pill_dedupes_detail_rows` verifies the dedupe property at the GearRunState level.

---

## What landed vs what didn't

### Plan promises that landed

- ✅ Earlier pill emission (`before_tool_callback` fires before tool execution, not after the function_call event arrives).
- ✅ Visible recovery (`on_tool_error_callback` emits a warning pill on tool failure).
- ✅ AgentTool nested invocations propagate correctly.
- ✅ Single source of truth for pill shape (`firestore_events.py` retains all per-tool branching).
- ✅ Eval helpers (`_iter_function_calls`, `extract_sources_from_grounding`, etc.) preserved.
- ✅ Public ToolContext fields used (no `_invocation_context` reach-throughs).
- ✅ Env-var preservation across deploys handles the REPLACE-not-MERGE risk.
- ✅ Citation discipline rule lands in both prompts.
- ✅ Cloud Trace env vars wired through the deploy script.

### Plan promises that didn't land

- ❌ **Net deletion of code.** The implementation grew the codebase by 124 production lines, not shrunk it by 25-55. The plan's accounting was wrong, and the implementer correctly identified that the per-tool branching had to live somewhere.

### Deferred per the plan

- `_map_router_complete` and `_map_final_complete` are still in `firestore_events.py` (lines 176-211). The plan called for deferring deletion until typed-hook coverage of `transfer_to_agent` is verified end-to-end on Agent Engine. Correctly deferred.

---

## Recommended follow-ups (all optional, no blockers)

1. **Docstrings for `map_tool_call`, `map_tool_result`, `map_tool_error`** in `firestore_events.py` — one-liner each saying they're called from typed hooks.
2. **Comment in `map_tool_error`** noting the synthetic-response trick is fragile — only works because all error branches in `map_tool_result` check only `status`.
3. **Comment in `_deployment_env_vars`** explaining the `_gca_resource` private-attribute access (no public alternative exists on the AgentEngine wrapper).
4. **Either dedup `_state_for_tool` / `_state_for_event`** in `firestore_progress.py`, or add a comment explaining the intentional differences (the `_is_nested_invocation` guard, the isinstance-check on invocation_id).

None of these are blockers. The implementation can ship as-is.

---

## Net assessment

**Technically:** correct, well-tested, architecturally sensible. All tests pass. The structural goals (typed hooks for tool observation, Cloud Trace observability, citation discipline, env-var preservation) are met.

**Against the lean goal:** production code grew by +124 lines. The framing in the plan — "delete the parser layer" — was wrong, and the implementation correctly identified that. The honest read: this was a structural cleanup with operability wins, not a line-count reduction.

**If we want net-deletion in future passes:**

- Remove the deferred `_map_router_complete` / `_map_final_complete` parsers after typed-hook coverage is verified.
- Revisit whether the duplicate `_state_for_tool` / `_state_for_event` helpers can be consolidated.
- Both of those together might recover ~30-50 lines.

**Worth landing:** yes. The structural improvements + Cloud Trace flip + citation rule are durable wins. But the "lean cleanup" framing should be retired — for changes touching the agent runtime layer, "structural improvement at modest LOC cost" is a more honest goal than "net deletion."

---

## References

### Files modified

- `agent/scripts/redeploy_engine.py`
- `agent/superextra_agent/firestore_events.py`
- `agent/superextra_agent/firestore_progress.py`
- `agent/superextra_agent/gear_run_state.py`
- `agent/superextra_agent/instructions/specialist_base.md`
- `agent/superextra_agent/instructions/research_lead.md`
- `agent/tests/test_firestore_events.py`
- `agent/tests/test_gear_run_state.py`

### Files added

- `agent/tests/test_firestore_progress_hooks.py`

### Plan documents

- `docs/lean-agent-cleanup-plan-2026-04-30.md` — implementation plan (detailed engineering reference).
- `docs/lean-agent-cleanup-overview-2026-04-30.md` — narrative overview for product/founders.
