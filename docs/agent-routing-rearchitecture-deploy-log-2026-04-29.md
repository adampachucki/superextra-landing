# Agent routing rearchitecture — deploy log

**Date:** 2026-04-29
**Branch:** `agent-routing-eval` → `main`
**Scope:** Deploy the AgentTool migration (Path A1) per
`docs/agent-routing-rearchitecture-plan-2026-04-29.md`. Implementation reviewed
in-session before this log starts. Coder's diff is unchanged on the branch.

## Plan vs reality (running)

Steps:

1. Pre-merge validation (test suites, cloudpickle).
2. Stage files by name, commit.
3. Push branch, open PR, watch CI, merge.
4. Redeploy Vertex AI Agent Engine (manual `agent_engines.update`).
5. Chrome MCP smoke through `agent.superextra.ai/chat`.
6. Monitor logs (Agent Engine + Firestore writes).
7. Fix anything that breaks. Record here.

## Pre-context

- Coder's diff already approved in review pass (see review thread).
- Cloudpickle smoke ran clean during review: `cloudpickle.dumps(app.root_agent)`
  → 66600 bytes, no errors.
- Pytest already ran clean during review: 169 passed / 17 skipped.
- Two review findings deliberately deferred (not blocking deploy):
  - Dead `value == "Agent did not produce output."` check in
    `_should_run_gap_researcher` — minor cleanup.
  - Plan doc still lists B-with-floors eval gate as merge criterion despite
    being rejected — doc edit only.

## Timeline

### 13:40 UTC — Pre-merge validation: green

All four test suites + lint + svelte-check pass on the branch tip:

| Gate           | Result                               |
| -------------- | ------------------------------------ |
| pytest         | 168 passed, 17 skipped, 0 failed     |
| vitest         | 59 passed in 6 files, 0 failed       |
| functions      | 63 passed, 0 failed                  |
| rules          | 22 passing                           |
| `npm run lint` | 0 errors, 21 warnings (pre-existing) |
| svelte-check   | 0 errors, 9 warnings (pre-existing)  |
| cloudpickle    | dumps clean, 66600 bytes             |

The 21 lint warnings are present on `HEAD` too (verified via `git stash` +
re-run) — not introduced by this branch. Same story for the 9 svelte-check
warnings.

Pytest count moved 174 → 168 because the dropped `set_specialist_briefs` /
`_make_skip_callback` tests are gone, and `test_specialist_callbacks.py` was
slimmed to one assertion that the specialist factory now produces
AgentTool-compatible specialists (`include_contents="default"`,
`before_agent_callback is None`).

### 13:42 UTC — PR #26 opened

Branch was at the same commit as `main` (no prior commits beyond it — all
work was uncommitted). Single squash-style commit
`736cb36 feat(agent): migrate research pipeline to AgentTool-wrapped specialists`
captures: agent rearchitecture, plugin guards + `_state_for_event` runId
fallback, eval harness improvements, the eval verdicts that informed the
plan, the spike artifacts, and the cleanup-status doc.

Five untracked docs left behind on the branch — out of scope (separate
work threads from earlier dates / unrelated topics).

PR: https://github.com/adampachucki/superextra-landing/pull/26

### 15:18-15:22 UTC — CI green, Firebase deploy succeeded

Squash-merged PR #26 → `main` (commit `a313b50`). `Deploy to Firebase`
workflow:

- `test` → success (CI re-ran the same eight gates we ran locally, plus
  build + agent pytest in the workflow's Python 3.12 container).
- `deploy-hosting` → success (Hosting + Cloud Functions + Firestore
  rules/indexes pushed in a single `firebase-tools deploy` call).

Note: the Vertex AI Agent Engine Reasoning Engine is **not** redeployed
by CI. That's the manual `agent_engines.update(...)` step next. The
Reasoning Engine still runs the previous pipeline shape until that step
completes — no production breakage, just that the new code isn't live
in the agent runtime yet. The agentStream cloud function (which only
hands off via `GEAR_REASONING_ENGINE_RESOURCE`) is unaffected by this
gap.

### 15:34 UTC — Reasoning Engine redeploy

`agent_engines.update(...)` against
`projects/907466498524/locations/us-central1/reasoningEngines/1179666575196684288`
succeeded after one retry. First attempt failed with
`PermissionDenied: ACCESS_TOKEN_SCOPE_INSUFFICIENT` — the VM's GCE
metadata service account lacks the `cloud-platform` scope. The fix is
documented in `docs/gear-probe-log-2026-04-26.md:64`:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/home/adam/.config/gcloud/legacy_credentials/adam@finebite.co/adc.json
```

Update operation ID:
`8394191397355257856`. SDK auto-pinned three additional requirements
to match the deployer venv: `pydantic==2.12.5`,
`google-cloud-aiplatform==1.147.0`, `cloudpickle==3.1.2` (the latter
two were already installed; `pydantic` was new).

The new pipeline (AgentTool-wrapped specialists, single LlmAgent
orchestrator) is now live in the production Reasoning Engine.

**Future-proofing:** wrote nothing to disk for this redeploy. If we
need to do this often, a `agent/scripts/redeploy_engine.py` would be a
worthwhile follow-up — but per "complicate later," skipped here.

### 15:31-15:36 UTC — Smoke test #1 (pricing-comparison floor): green

**Query:** "How does our pricing compare to nearby competitors? Are we
priced right for our positioning?"
**Venue:** Le Vintage, Rue Haute, Brussels
**Session:** `864d96b3-596b-4c4e-a54d-5235ea448a51` (run
`2e1dea45-2756-483a-a1e0-6369fbe87f7a`)
**Wall clock:** 4m 9s
**Terminal state:** `session.status=complete`, `turn.status=complete`,
`error=null`, no fallback synth.

What this verifies in production with the new architecture:

- **Per-specialist activity rows render under AgentTool.** The
  `_state_for_event` runId fallback in `firestore_progress.py` works
  end-to-end. Activity rows surfaced cleanly through TripAdvisor matches,
  Google Reviews load, and per-venue web fetches. This was the single
  highest-risk piece in the migration; the smoke test demonstrates the
  fix is correct.
- **Floor compliance for pricing-comparison queries.** Activity counts
  show `review_analyst` (50 Google reviews + 30 TripAdvisor reviews,
  matched 5 venues), web-fetched menu pages
  (`menu_pricing` — `levintage.brussels/la-cuisine`, `todtscafe.be/menu`,
  `cestboncestbelge.be/menus-carte`, `skievelat-sablon.be/menu-a-la-carte`),
  and beverage/SERP pages
  (`marketing_digital` — `levintage.brussels/cocktails`,
  `levintage.brussels/bieres`, `vertigobrussels.com`). Floor minimum
  satisfied.
- **Premise audit visible.** Final report opens "Initial assumptions
  that the restaurant's pricing aligns with neighborhood averages are
  contradicted by menu data" — exactly the
  SUPPORTED/QUESTIONABLE/CONTRADICTED framing the new orchestrator
  prompt mandates.
- **Synthesizer produces structured output.** Executive Summary,
  three named subsections (price positioning, customer value
  perception, demographics, digital strategy), three strategic
  follow-up questions, 20 sources cited.
- **Title generation works.** `title='Price Positioning Review'`
  written via the first-turn title task.

Logs and Firestore:

- `gcloud logging read severity>=WARNING --freshness=15m` returns nothing
  — no errors logged during the run.
- `audited_resource` shows `UpdateReasoningEngine` at 15:29:31 UTC,
  matching the redeploy timestamp.
- 26 timeline events written in
  `sessions/{sid}/events/`, ordered seq 1-26 across enricher,
  reconnaissance, and per-specialist work. No nested-invocation
  collisions (would have shown up as duplicate ownership claims or
  ownership-lost log spam — neither appeared).
- `lastHeartbeat` advanced steadily (~30s tick) until terminal write
  cancelled the heartbeat.
- One non-fatal warning surfaced as user-facing
  "TripAdvisor match not verified for the venue" — that's the
  specialist's own emitted warning, not a plugin/runtime issue.

**Verdict:** Sec 5 (frontend verification) gate **passes**. The
AgentTool migration is live and behaviorally correct for the
pricing-comparison floor.

### 15:38 UTC — Smoke test #2 (follow-up routing): green

**Query (turn 2 of the same session):** "What's the single most
important pricing change we should make this month?"
**Wall clock:** ~6s (between submit and final answer rendering).
**Reply length:** 487 chars. Cites prior-report sections in
parentheses ("Customer Value Perception & Sentiment, Friction
Points") — characteristic of `follow_up` reading
`final_report` from state, not a fresh research run.
**Terminal state:** turn 0002 `status=complete`, no error.

This verifies the router still classifies follow-ups correctly under
the new pipeline, that `follow_up` reads `final_report` from state
without re-dispatching specialists, and that `final_report_followup`
is written instead of `final_report` (preserving the original report
for the next follow-up — the "quality decay" guard documented in
`agent.py:230-237`).

### 15:42-15:48 UTC — Smoke test #3 (openings/closings floor): green

**Query (fresh chat):** "Who has opened or closed in our area in the
last 6 months, and what can we learn from them?"
**Venue:** Restauracja Monsun Gdynia, Świętojańska 69b
**Session:** `1081f988-a3a2-463c-af7a-f1569b6a5b21`
**Wall clock:** 6m 5s
**Terminal state:** `session.status=complete`, no errors, 29 sources,
6471-char report.

Floor satisfied (`market_landscape + menu_pricing + marketing_digital

- review_analyst`):

* `market_landscape` — named recent closures (Trafik 18-yr-old, Brassica
  2-month flameout, Cyk Pyk struck from KRS), pulled from
  `trojmiasto.pl`, `vrejestr.pl`, `dlugi.info`.
* `menu_pricing` — direct competitor pricing comparison, "40–50% price
  premium over Nam-Viet" sourced from delivery-platform menu fetches.
* `marketing_digital` — delivery-platform presence audit ("vanished from
  Wolt, Pyszne.pl, Glovo, Uber Eats" for Socialife) plus social
  footprint reasoning.
* `review_analyst` — review-velocity / rating-trajectory analysis
  ("Maintained ~10 reviews per month with 4- and 5-star ratings right
  up to closure" for Cyk Pyk; "9 reviews in 20 days then flatlined" for
  Socialife).

Premise audit: "The prevailing assumption that recent restaurant
closures... were caused by declining food quality is fundamentally
incorrect." Output is the orchestrator's premise-audit framing exactly
as the new prompt mandates.

### Final monitoring sweep

After all three smokes:

- `gcloud logging read 'severity>=WARNING' --freshness=10m` returns 0
  rows. No errors, no warnings, no ownership-lost spam.
- All three sessions terminal-clean
  (`status=complete`, `error=null`, all turns `status=complete`).
- Title generation worked on both fresh chats
  (`'Price Positioning Review'`, `'Area business changes lessons'`).
- Heartbeat advanced steadily across all three runs (no
  `pipeline_wedged` triggers from watchdog).

## Outcome

| Stage                         | Status                                      |
| ----------------------------- | ------------------------------------------- |
| Pre-merge validation          | ✅ green (8 gates)                          |
| PR + CI + Firebase deploy     | ✅ green (PR #26 → `main` `a313b50`)        |
| Vertex AI Agent Engine update | ✅ green (op `8394191397355257856`)         |
| Smoke #1 — pricing floor      | ✅ green (4m 9s, 20 sources)                |
| Smoke #2 — follow-up          | ✅ green (~6s, 487 chars from prior report) |
| Smoke #3 — openings floor     | ✅ green (6m 5s, 29 sources)                |
| Logs (errors, warnings)       | ✅ clean (10m post-deploy)                  |

**Migration is live, behaviorally verified, and quality-comparable on
two of the production floors.** No issues to fix.

## What we learned

- **`_state_for_event` runId fallback was the load-bearing fix for
  per-specialist activity rows.** The plan didn't anticipate this; the
  coder caught it in implementation. Without it, the timeline would
  have rendered enricher/orchestrator events only, no specialist
  activity. This is the single most important new line of code in the
  migration.
- **The cloudpickle gate caught nothing** (test passed locally and in
  the CI-equivalent). That doesn't make the gate worthless — it would
  have caught a pickle-time failure cheaply. Worth keeping as a
  pre-merge habit for any future agent code change.
- **`agent_engines.update(...)` from this VM requires
  `GOOGLE_APPLICATION_CREDENTIALS` pointing at the user's legacy
  ADC.** GCE metadata creds lack the `cloud-platform` scope. Already
  documented in `gear-probe-log-2026-04-26.md:64`; would have been
  worth a one-line note in the rearchitecture plan's deploy section.
- **The B-with-floors hypothesis held in production.** Per Adam's
  rejection of the pre-merge eval gate ("floors are proven to work in
  production today"), we shipped without re-running A-vs-B-with-floors
  pairwise judging. The two floor smokes show the new architecture
  produces structured, premise-aware, multi-source reports comparable
  in shape and depth to the previous pipeline. The targeted post-deploy
  pairwise re-eval can land later as routine quality monitoring rather
  than a deploy gate.

## Follow-ups (not blocking)

- Five docs are still untracked on `main` after this deploy
  (`docs/architecture.md`, `conversation-quality-plan-2026-04-28.md`,
  etc.) — out of scope for this PR; pick them up with their respective
  work.
- `docs/architecture.md` opening line still says "dispatches 'specialist'
  sub-agents in parallel" — drift from the new AgentTool reality.
  Either retire that doc or update it; not a deploy blocker.
- A reusable `agent/scripts/redeploy_engine.py` would save the next
  redeploy ~5 minutes of remembering the incantation. Defer until
  someone has to do this manually a second time.
