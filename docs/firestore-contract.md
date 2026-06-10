# Firestore contract — sessions / turns / events

The chat transport's data contract binds three codebases: **Cloud Functions**
write session/turn lifecycle docs (`functions/index.js`, `watchdog.js`), the
**agent plugin** writes progress and terminal state from inside Agent Engine
(`agent/superextra_agent/firestore_progress.py`, `gear_run_state.py`,
`timeline.py`), and the **frontend** reads everything through four listeners
(`src/lib/chat-state.svelte.ts`; reader-facing types in `src/lib/chat-types.ts`).

This page is a writer/reader map, not a schema system — code remains the
source of truth. Update it when a field is added, renamed, or changes owner.

## `sessions/{sid}`

| Field                                                                                         | Type                                         | Written by                                                    | Read by                                                            |
| --------------------------------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------ |
| `userId`                                                                                      | string (creator uid)                         | agentStream (first message)                                   | rules, frontend (`canDelete`)                                      |
| `participants`                                                                                | string[] (arrayUnion per submitter)          | agentStream                                                   | rules (`array-contains` list), sidebar listener                    |
| `createdAt` / `updatedAt`                                                                     | timestamp                                    | agentStream; every writer bumps `updatedAt`                   | sidebar ordering (`updatedAt desc`)                                |
| `title`                                                                                       | string \| null                               | intake reply txn; agent title task (fenced, best-effort)      | sidebar                                                            |
| `placeContext`                                                                                | object \| null                               | agentStream (validated)                                       | frontend, agent query prefix                                       |
| `currentRunId`                                                                                | string                                       | agentStream (new run per turn)                                | **the fence** — every agent-side write and watchdog flip checks it |
| `status`                                                                                      | `queued` → `running` → `complete` \| `error` | see state machine below                                       | active-session listener (`loadState`), watchdog queries            |
| `queuedAt`                                                                                    | timestamp                                    | agentStream                                                   | watchdog (stuck-queued detection)                                  |
| `lastHeartbeat`                                                                               | timestamp \| null                            | plugin heartbeat loop (fenced)                                | watchdog (stale-running detection)                                 |
| `lastEventAt`                                                                                 | timestamp \| null                            | plugin on_event (fenced, best-effort)                         | watchdog                                                           |
| `error` / `cancelledAt`                                                                       | string \| null / timestamp                   | agentCancel, watchdog, agent terminal write                   | frontend error display                                             |
| `lastTurnIndex`                                                                               | number                                       | agentStream txn (with matching turn doc)                      | plugin claim, frontend                                             |
| `engineSessionId` / `engineSessionGeneration` / `engineSessionStarted`                        | string / number / bool                       | agentStream (rotation after cancel), markEngineSessionStarted | agentStream only (engine-session reuse)                            |
| `intakeState`                                                                                 | object \| null                               | intake reply txn; cleared on engine start                     | intake conversation (functions)                                    |
| `language`                                                                                    | string (ISO-639-1, per turn)                 | agentStream (detect-language)                                 | frontend activity-label localization                               |
| `activeAgent` / `activeStage` / `activeStageStartedAt` / `activeModel` / `activeInvocationId` | transient strings/timestamps                 | plugin during run (fenced); deleted by terminal write         | live status label                                                  |

### Session status machine

```
(agentStream txn)            (plugin before_run claim,        (plugin terminal write,
 new currentRunId             fenced: status==queued           fenced on currentRunId)
 ────────────────► queued ──────────────────► running ──────────────► complete
                      │                          │                       │
                      │ watchdog: stuck queued   │ watchdog: stale       │ next turn:
                      │ agentCancel              │ heartbeat; agentCancel│ agentStream
                      ▼                          ▼                       ▼ re-queues
                    error ◄──────────────────────┘                     queued
```

The intake path (`turnKind: intake_reply`) completes a turn directly in
Cloud Functions without an engine run. Cancel flips the session to `error`
with `cancelledAt`; the engine run keeps executing but every fenced write
fails (`TimelineOwnershipLost` / `OwnershipLost`) and the plugin goes quiet.

## `sessions/{sid}/turns/{0001…}` (key = zero-padded turnIndex)

| Field                                | Type                                                         | Written by                                       | Read by                                                      |
| ------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------ | ------------------------------------------------------------ |
| `turnIndex` / `runId`                | number / string                                              | agentStream txn                                  | turns listener (ordered by `turnIndex`), events attach       |
| `userMessage`                        | string                                                       | agentStream                                      | message list                                                 |
| `language`                           | string                                                       | agentStream                                      | reply rendering                                              |
| `status`                             | `pending` → `running` → `complete` \| `error`                | claim + terminal writes (same fences as session) | turn rendering, optimistic-turn reconciliation               |
| `acknowledgement` / `acknowledgedAt` | string \| null                                               | recordResearchStart (intake → research handoff)  | message list                                                 |
| `reply`                              | string \| null                                               | agent terminal write; intake reply txn           | final answer                                                 |
| `sources`                            | `ChatSource[]` \| null                                       | agent terminal write (`[]` for intake)           | source pills                                                 |
| `turnSummary`                        | `{startedAtMs, finishedAtMs, elapsedMs}`                     | agent terminal write; intake txn                 | completed-activity hydration                                 |
| `turnKind`                           | `research_report` \| `agent_reply` \| `intake_reply` \| null | terminal writes                                  | rendering variants                                           |
| `feedback.<uid>`                     | `{rating: 'up'\|'down'}`                                     | agentFeedback function                           | thumbs state                                                 |
| `createdAt` / `completedAt`          | timestamp                                                    | agentStream / terminal writes                    | timestamps, audit_turns.py (collection-group on `createdAt`) |
| `error`                              | string \| null                                               | terminal/cancel/watchdog writes                  | error display                                                |

## `sessions/{sid}/events/{auto-id}`

Written **only** by `TimelineWriter` (one fenced transaction per event;
raises `TimelineOwnershipLost` when the run lost ownership). TTL: `expiresAt`
is set +180 days; Firestore TTL deletes them (sessions/turns have no TTL).

| Field                                           | Type                                                                                                         | Notes                                                                                                                  |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| `userId` / `runId` / `attempt` / `seqInAttempt` | string / string / number / number                                                                            | events listener filters `runId == latestTurn.runId`, orders by (attempt, seqInAttempt); frontend dedupes on the triple |
| `type`                                          | `'timeline'`                                                                                                 |                                                                                                                        |
| `data`                                          | `TimelineEvent` (`kind: 'detail'` rows with `group`/`family`/`text`/`labelKey`/`vars`, or `kind: 'thought'`) | produced by `firestore_events.py`; `labelKey` resolves to Paraglide messages (`activity-i18n.ts`)                      |
| `ts` / `expiresAt`                              | timestamp                                                                                                    |                                                                                                                        |

## `users/{uid}` (brief)

Identity fields written by agentStream/sendMagicLink; `plan`/billing fields
owned by `functions/billing.js` (Stripe webhooks); quota counters owned by the
agent-side quota gate (`quota_gate.py`). Frontend listens via
`billing-state.svelte.ts`. Never write quota fields from Functions.
