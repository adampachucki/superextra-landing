# Agent routing — rearchitecture plan (Path A1)

**Date:** 2026-04-29
**Owner:** Adam (PM); execution: Claude
**Status:** Implemented locally; staging/frontend/deploy verification pending
**Companion docs:**

- `docs/agent-routing-redesign-context-2026-04-29.md` — investigation background
- `docs/agent-routing-redesign-eval-plan-2026-04-29.md` — eval plan
- `docs/agent-routing-redesign-eval-results-2026-04-29.md` — eval results
- `docs/agent-tool-spike-findings-2026-04-29.md` — pre-eval spike

## Goal

Migrate the production research pipeline from `SequentialAgent +
ParallelAgent + set_specialist_briefs` to `AgentTool`-wrapped specialists
**with the production query-type-coverage floors preserved** (Path A1
from the eval-results doc). The redesigned routing rules (rich
descriptions + count-based principle) are _not_ part of this scope —
the eval showed they regress quality. We're shipping the architectural
change only; floor experiments are deferred to a separate phase.

## Constraints (from Adam, 2026-04-29)

1. **Simplification.** Lean and clean. Complete, stable, reliable, but
   pragmatic.
2. **No defensive architecture.** Don't add multiple paths to preserve
   behavior. We accept reduced live-progress-UI scope rather than
   complicate the architecture to keep every existing affordance.
3. **Compliance with Google ADK docs and best practices.** When ADK
   guidance conflicts with our pattern, prefer ADK guidance unless we
   have explicit reasons not to.
4. **Root-cause fixes.** When something breaks, fix the cause, not
   symptoms — even if the cause is two layers down.
5. **Complicate later.** First land the foundation, then iterate.

## Evidence-based caveat (read this first)

External research (this session) surfaced one finding that's worth
flagging up front: **ADK's own deep-search sample uses
`SequentialAgent + LoopAgent + sub_agents`, NOT `AgentTool` wrapping
for its specialists.** ADK's documentation explicitly recommends
`ParallelAgent` for "Parallel Information Gathering"
(https://adk.dev/agents/multi-agents/index.md). The `AgentTool` pattern
that Anthropic's Research multi-agent system, LangGraph supervisor, and
Claude Code use is **not the ADK idiom for fan-out research with
progress UIs.**

There's a real tension between two of Adam's constraints:

- "Compliant with Google docs and best practices" → keep `ParallelAgent`.
- "AgentTool aligns with Claude Code / Anthropic / human analyst teams"
  (the rationale Adam gave for choosing this direction).

The eval didn't disambiguate this — it showed the failure was in floors,
not architecture. So we have two coherent choices:

- **Proceed with A1 as planned** (AgentTool wrapping). Choose
  cross-platform pattern over ADK-specific idiom. Pay for the plugin
  lifecycle complexity, gain iterative-dispatch capability + single
  source of truth for descriptions. **This plan documents this path.**
- **Revert architecture** (keep ParallelAgent), do the description
  fattening + targeted floor rework on top of current structure. ~50%
  less work, full ADK-idiom compliance, but no iterative-dispatch
  capability.

**My recommendation:** proceed with A1. The eval already built most of
the infrastructure (it works, it's tested), and iterative-dispatch is
the future-proof affordance that justifies the migration. But the
choice should be made eyes-open: this is "cross-platform pattern" over
"ADK-canonical pattern."

If you want to revert that direction, stop reading and we replan. If
you're aligned, the rest of this doc is the execution plan.

## Implementation state — 2026-04-29

The local implementation now follows this plan:

- `agent.py` exports the single production `app`; the `_v3` sidecar
  files are deleted.
- The pipeline is
  `Router -> Context Enricher -> Research Orchestrator -> specialists
via AgentTool -> Gap Researcher -> Synthesizer`.
- The old brief-dict dispatch path is deleted:
  `set_specialist_briefs`, `_make_skip_callback`, `VALID_BRIEF_KEYS`,
  and `specialist_briefs` writes are no longer production concepts.
- `ORCHESTRATOR_SPECIALISTS` is the catalog source for the specialists
  the orchestrator can call. Their `description` fields are consumed by
  `AgentTool`.
- `research_orchestrator.md` is AgentTool-shaped and keeps the
  production query-type floors.
- `FirestoreProgressPlugin` routes AgentTool child events back to the
  parent run state by `runId`, because child runners have distinct
  invocation IDs.
- `run_matrix.py` uses `App(plugins=...)` instead of deprecated
  `Runner(plugins=...)`.

Still pending before deploy:

- Full-plugin dev or staging smoke with FirestoreProgressPlugin and
  ChatLoggerPlugin enabled.
- Chrome MCP progress-UI verification on staging.
- Vertex AI Agent Engine `agent_engines.update(...)`.

## What this plan does NOT include (deliberately out of scope)

- **Floor experiments.** Floors stay as-is. No description
  experiments, no count-based principle, no removal. A separate plan
  comes after this one.
- **Gap researcher rework.** Stays as-is. Separate plan.
- **EventCapturePlugin in production.** It's an eval-side tool only;
  production uses FirestoreProgressPlugin + ChatLoggerPlugin.
- **Backwards-compatibility shims.** Old `set_specialist_briefs` tool,
  `_make_skip_callback` pattern, duplicate `Available specialists` list
  in the .md — all deleted, not deprecated.
- **Multiple paths to preserve every UI affordance.** If something
  about the live progress UI changes shape (per Adam's "I'm OK with
  limiting scope"), we accept it.

## Plan

**Execution order:** Sec 1-4 and Sec 6 are implemented locally.
Cleanup in Sec 8 happened during implementation rather than waiting
until after deploy, because the removed code had no remaining callers.
The B-with-floors eval is no longer a required pre-merge gate; run it
only if routing quality looks questionable after smoke testing. The
remaining gates are full-plugin smoke, Chrome MCP progress-UI
verification, deploy, and production smoke.

### 0. Branch hygiene

We're on `agent-routing-eval`. Two options:

- Continue on this branch, merge to main when ready.
- Cut a fresh `agent-routing-rearchitecture` branch from current state.

**Decision:** continue on `agent-routing-eval` (already has all the
eval-built artifacts; cutting a fresh branch loses that work or
requires cherry-picking). Rename if needed at PR time.

### 1. Keep the existing `_is_nested_invocation` check (no refactor)

**Why this section was originally a refactor and why it isn't anymore:**
The eval-built helper uses
`isinstance(invocation_context.session_service, InMemorySessionService)`
to detect nested invocations. The original plan flagged this as
"hacky and version-fragile" and proposed a sentinel-state replacement.
On review: `agent_tool.py:232` hardcodes
`session_service=InMemorySessionService()` as a structural property of
how AgentTool spawns child runners — not a private implementation
detail that drifts with refactors. ADK would have to redesign
AgentTool to break this check.

**Decision:** keep the isinstance check as-is. Add a one-line code
comment in `firestore_progress.py` and `chat_logger.py` explaining
why it's reliable (refers to `agent_tool.py:232`). No code change to
the guard itself.

This is the "no defensive architecture" call: 8-10 lines of sentinel-
state machinery to harden a check that's already structurally reliable
is over-engineering. We accept the small risk that ADK someday
restructures AgentTool's child-runner construction, and we'd update
the check then.

Files affected:

- `agent/superextra_agent/firestore_progress.py` — add comment.
- `agent/superextra_agent/chat_logger.py` — add comment.

### 2. Merge `agent_v3.py` into `agent.py`, delete `_v3` files

**Root cause being fixed:** keeping both `app` and `app_v3` is
permanent legacy. Two pipelines, two prompts, two `follow_up`
agents, two of everything. Delete the old, rename the new.

Concretely:

- Move all `app_v3` definitions from `agent_v3.py` into `agent.py`.
- Delete `agent_v3.py`.
- Delete `_follow_up_v3` (reuse production `follow_up`; the spike
  agent built `_follow_up_v3` only because of pydantic single-parent
  constraint when both apps coexisted).
- Update imports in tests and any deploy scripts.

The new `agent.py` exports a single `app` (the rearchitected one).

### 3. Merge `research_orchestrator_v3.md` into `research_orchestrator.md` with floors preserved

**Root cause being fixed:** v3 dropped the floors and lost the eval.
A1 says preserve floors. So we restore the floors in the new prompt.

Concretely:

- Start from `research_orchestrator_v3.md` (88 lines — already has the
  AgentTool-style dispatch language, no `set_specialist_briefs`).
- Restore the production floors section verbatim from
  `research_orchestrator.md:84-106` (5 query-type rules).
- Adapt the floor language to AgentTool dispatch: "for these query
  types you MUST call specialists X + Y + Z **as tools** before
  finalizing" (instead of "MUST include in the brief dict").
- Keep the iterative-dispatch invitation. Floors set the _minimum_
  spec set; iterative dispatch can add more. They're compatible.
- Keep the count-based "≥2 specialists" principle as a fallback for
  query types that don't match a floor. This is what the production
  prompt has today (just less explicit).
- Drop the duplicate `## Available specialists` list (lines 65-73 in
  prod). Catalog descriptions are now consumed at routing time via
  AgentTool, no need to duplicate.
- Save as `research_orchestrator.md`. Delete the v3 file.

This produces a single orchestrator prompt that is AgentTool-shaped +
production-floor-preserving. ~110-130 lines (slightly bigger than
v3's 88 because we restore floors; smaller than the prod 124 because
we drop the duplicate specialist list).

### 4. Migrate from deprecated `Runner(plugins=...)` to `App(plugins=...)`

**Root cause being fixed:** the `plugins=` kwarg on `Runner` is
deprecated in current ADK (research finding from
runners.py:182,251 — "Please use the `app` argument to provide
plugins instead"). Production already uses `App(plugins=...)` via the
`app = App(...)` definition at `agent.py:290-299`. The eval's
`run_matrix.py:230-235` constructs Runner with the deprecated kwarg
to strip FirestoreProgressPlugin. Move the strip-plugin logic to
construct a separate `App` for evals.

Concretely:

- In `agent/evals/run_matrix.py:_run_matrix_in_process`, after loading
  `app`, build an `eval_app = App(name=app.name,
root_agent=app.root_agent, plugins=eval_plugins)` and use `eval_app`
  for the Runner. Drop the `plugins=` Runner kwarg entirely.

This is a small fix and aligns with current ADK guidance.

### 5. Frontend progress UI — verify, accept reduced scope if needed

**Per Adam's constraint #2:** we accept reduced UI scope rather than
complicate architecture. The verification path:

- Deploy to staging Firebase Hosting site.
- Run a real query through `landing.superextra.ai/agent` (the agent UI).
- Use Chrome MCP to navigate to a research session, watch the activity
  rows render in real time.
- **Expected behavior under AgentTool wrapping:**
  - Per-specialist activity rows still appear (because
    `on_event_callback` fires for child events with sentinel-guarded
    plugins).
  - Specialist names + status (running, complete) update live.
  - Source pill counts update.
- **What we're prepared to accept losing if it doesn't work
  out-of-box:**
  - Per-specialist token-count granularity in progress events (if
    `usage_metadata` doesn't propagate cleanly under AgentTool, we
    accept aggregate-only).
  - Cross-specialist event ordering accuracy (parallel AgentTool
    calls are last-writer-wins on shared state per ADK research; our
    state model uses per-specialist keys so this is a non-issue, but
    flagging).
  - Any UX affordance that depends on `before_run_callback` being
    called per-specialist (it isn't, with sentinel guards).

**Verification gate:** progress UI rendering must not visually break
(activity rows must update, terminal state must arrive). Granularity
losses are acceptable. If activity rows don't render at all under
AgentTool, that's a real bug — root-cause fix before shipping.

### 6. Tests update

**Root cause being fixed:** tests written against the old pipeline
shape will break.

Affected test files (likely):

- `agent/tests/test_specialist_callbacks.py` — references
  `_make_skip_callback` and `set_specialist_briefs`. These are gone.
  Either update tests for AgentTool dispatch path, or delete tests
  that test deleted behavior.
- `agent/tests/test_follow_up_routing.py` /
  `agent/tests/test_router_evals.py` — may depend on agent topology;
  verify they still pass.
- `agent/tests/test_gap_researcher.py` — may pass through unchanged
  but verify.
- `agent/tests/test_specialists.py` — likely needs adjustment for
  new `_make_specialist` signature (no skip callback, default
  `include_contents`).

Run `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` after each
change. Target: all tests pass before deployment. Per build agent's
report: 174 passed / 17 skipped at eval time (with `_v3` files
existing) — should still pass after merge.

Also: `npm run test`, `cd functions && npm test`,
`npm run test:rules`. These shouldn't be affected by agent code
changes but worth running before deploy.

### 7. Deployment

Standard agent deployment per CLAUDE.md ("Transport architecture"):

1. Push branch, open PR, merge to `main`.
2. GitHub Actions runs CI (lint, format, svelte-check, vitest,
   functions tests, rules emulator, agent pytest).
3. CI deploys Firebase Hosting + Cloud Functions + Firestore rules/indexes.
4. **Manual step:** redeploy the Vertex AI Agent Engine Reasoning
   Engine. Per CLAUDE.md: "redeploy via `agent_engines.update(...)`
   from the agent venv when the agent code changes." This is the agent
   code change.
5. Post-deploy smoke: run one real query end-to-end through the
   production UI, verify report renders + activity rows + final
   report.

### 8. Remove the now-unused machinery

Completed during implementation:

- Deleted `set_specialist_briefs` from `specialists.py`.
- Deleted `_make_skip_callback` from `specialists.py`.
- Deleted `VALID_BRIEF_KEYS`.
- Renamed `BRIEFABLE_SPECIALISTS` to `ORCHESTRATOR_SPECIALISTS`.
- Kept only a historical parser branch for old eval captures that
  already contain `specialist_briefs`.

This intentionally removed the duplicate dispatch path instead of
preserving it as compatibility architecture.

## Risks and mitigations

| Risk                                                                                   | Mitigation                                                                                                                                                                                                                     |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Frontend progress UI breaks visually under AgentTool                                   | Verify on staging before prod deploy; if broken, root-cause (likely a `branch` field correlation issue in `firestore_progress.py:on_event_callback`) and fix.                                                                  |
| AgentTool child events have different invocation IDs                                   | `FirestoreProgressPlugin._state_for_event` falls back to the copied `runId` in child session state and routes events to the parent `GearRunState`.                                                                             |
| ADK 1.28 has a quirk we haven't observed                                               | Pre-deploy: run a single full-pipeline query against `app` (the new one) on the dev VM with full plugins enabled. We haven't done this — eval mode stripped FirestoreProgressPlugin. This single test would catch most quirks. |
| `agent_engines.update(...)` deploy fails because of pydantic single-parent constraints | Build agent flagged this for `follow_up_v3` reuse. We're collapsing to a single `follow_up`; verify pickle-ability before deploy. The eval ran agent_v3 in-process so didn't pickle.                                           |
| Production sessions in flight get split-brain                                          | Vertex Agent Engine `update(...)` is atomic per ADK research — old sessions continue on previous version. No split-brain.                                                                                                      |
| Test coverage misses something                                                         | Run all four test suites before deploy. Manual smoke test post-deploy.                                                                                                                                                         |

## Acceptance criteria

Before merge:

- [ ] All four test suites pass: `npm run test`, `cd agent && PYTHONPATH=. .venv/bin/pytest tests/`, `cd functions && npm test`, `npm run test:rules`.
- [ ] `agent.py` has no references to `agent_v3`, `app_v3`, `_v3`,
      `set_specialist_briefs`, `_make_skip_callback`.
- [ ] `research_orchestrator.md` is the only orchestrator prompt;
      contains the production floors verbatim (or near-verbatim adapted to
      AgentTool dispatch language).
- [ ] Single-query smoke run on dev VM with full plugin set
      (FirestoreProgressPlugin + ChatLoggerPlugin) completes successfully
      end-to-end.
- [ ] **Cloudpickle smoke test passes.** Run
      `cloudpickle.dumps(app.root_agent)` (or equivalent — match what
      `agent_engines.update(...)` does internally). Vertex AI Agent Engine
      deploys via cloudpickle; instruction providers are closures, plugin
      instances hold lazily-init clients. The build agent's pydantic
      single-parent surprise around `follow_up_v3` warns this is a real
      failure mode. **Discovering pickle failure post-CI is a 30-min fire
      drill — gate before merge.**
- [ ] Optional: run a targeted B-with-floors eval if smoke testing
      suggests routing quality regressed. This is not a required gate for
      the architecture cleanup.

Before agent_engines deploy:

- [ ] Frontend progress UI verified on staging via Chrome MCP — activity
      rows render, terminal state arrives.

After deploy:

- [ ] One real query through production UI, full activity-row to
      final-report cycle works.
- [ ] No new errors in Vertex AI Agent Engine logs in the first hour.
- [ ] No new errors in Firestore-progress writes (look for "ownership
      lost" / "claim failed" in the agent logs).

## Time estimate

- Sec 1 (comment-only on existing check): 5 min
- Sec 2 (merge agent files): 30-45 min
- Sec 3 (merge prompt with floors): 30 min
- Sec 4 (deprecated plugins kwarg): 15 min
- Sec 5 (frontend verify): 30-60 min depending on findings
- Sec 6 (tests): 1-2 hours
- Sec 7 (deploy): 30-45 min including Agent Engine update
- Sec 8 (cleanup): complete locally
- **Optional B-with-floors eval:** ~45 min if routing quality is in
  doubt after smoke testing
- **Pre-merge cloudpickle smoke (new gate):** ~10 min

**Remaining work:** staging/full-plugin smoke, Chrome MCP progress-UI
verification, deploy, and production smoke.

If frontend verification surfaces a real progress-UI bug (Sec 5 worst
case), add 1-2 hours for root-cause + fix.

If smoke testing shows material routing-quality regression, stop and
run the targeted eval before deploying.

## Open questions

1. **Should we delete the spike code?** `agent/spikes/agent_tool/` is a
   reference but no longer needed. Deletion candidate post-deploy.
2. **Catalog derived views.** Resolved locally:
   `BRIEFABLE_SPECIALISTS` became `ORCHESTRATOR_SPECIALISTS`;
   `VALID_BRIEF_KEYS` was deleted; output-key and author-label maps
   remain because progress mapping and follow-up state still use them.
3. **Frontend code expectations.** Does any frontend code key off
   "specialist X has a brief assigned" (i.e. read `specialist_briefs`
   from session state)? If yes, we need a small frontend update
   because that state key won't exist anymore. Quick grep before
   proceeding.

## Sources

- ADK plugin docs: https://adk.dev/plugins/index.md
- ADK multi-agents: https://adk.dev/agents/multi-agents/index.md
- AgentTool source: https://github.com/google/adk-python/blob/main/src/google/adk/tools/agent_tool.py
- BasePlugin source: https://github.com/google/adk-python/blob/main/src/google/adk/plugins/base_plugin.py
- InvocationContext source: https://github.com/google/adk-python/blob/main/src/google/adk/agents/invocation_context.py
- ADK Runner deprecated `plugins=` kwarg: https://github.com/google/adk-python/blob/main/src/google/adk/runners.py
- Parallel tool gather + state_delta merge: https://github.com/google/adk-python/blob/main/src/google/adk/flows/llm_flows/functions.py
- Reference deep-search ADK sample (uses SequentialAgent, NOT AgentTool wrapping): https://github.com/google/adk-samples/tree/main/python/agents/deep-search/app/agent.py
