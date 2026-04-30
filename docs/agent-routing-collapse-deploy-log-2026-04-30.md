# Agent routing collapse — deploy log

**Date:** 2026-04-30
**Branch:** `main`
**Scope:** Deploy the pipeline collapse from
`docs/agent-routing-collapse-plan-2026-04-29.md`: remove the dedicated
synthesizer, remove gap researcher, drop query-type floors, and let
`research_lead` plan, dispatch, iterate, and emit the final report.

## Commits

- `22d2540` — `feat(agent): collapse research pipeline to lead-as-synthesizer + drop floors`
- `8fb24d3` — `chore(docs): prettier --write on routing collapse + floors-handoff docs`

## Validation

Local and CI validation covered the collapse path:

| Gate            | Result                              |
| --------------- | ----------------------------------- |
| Agent pytest    | 152 passed, 17 skipped              |
| Vitest          | passed                              |
| Cloud Functions | 63 passed                           |
| Firestore rules | covered by CI                       |
| `npm run build` | passed, existing Svelte warnings    |
| `npm run check` | 0 errors, existing Svelte warnings  |
| Cloudpickle     | dumps clean, 66464 bytes            |
| Stale-ref scan  | no production refs to removed paths |

Local VM note: one local rules run was blocked by missing Java for the
Firestore emulator. This was an environment issue, not an app failure.

## Agent Engine Deploy

Reasoning Engine update completed via `agent_engines.update(...)`.

Operation ID: `8495080385296728064`

## Production Smoke

Chrome MCP smoke through `agent.superextra.ai/chat` passed on an
openings/closings query.

- Full report rendered.
- Runtime: 3m 16s.
- Sources rendered: 25.
- Logs were clean during the smoke.

## Notes

The collapse intentionally removes the stitched synth fallback. Empty
`final_report` still fails the turn rather than rendering a blank
success, via the mapper's terminal sanity check.

The old floor handoff is superseded. Future routing fixes should start
from evidence-surface planning and specialist descriptions, not from
reintroducing query-type floors.
