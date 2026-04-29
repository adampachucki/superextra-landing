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
