# Cold-start listener race in agent chat — 2026-05-07

## Incident

User submitted a real prompt on production from `agent.superextra.ai/`
(RestaurantHero) on 2026-05-06. Three observed symptoms in one session:

1. Timer stuck at "0s" for a long time after the chat page opened.
2. The user's own message was never visible in the thread.
3. After ~10 s, the timer disappeared and the page flipped to "Couldn't
   load this chat".

URL the user shared: `agent.superextra.ai/agent/chat?sid=0db2323e-3a59-4b29-85d6-a30322f161ea`.

## Backend was healthy — symptoms were entirely client-side

Verified directly from Firestore for sid `0db2323e-...`:

- Session `status='complete'`, `title='Foot traffic patterns neighborhood'`,
  `placeContext='Monsun Gdynia'`, `participants=['feadLLD5IuUrJNeQTPPu9QIg3wg1']`.
- `createdAt=21:30:17.099Z`, `updatedAt=21:32:32.970Z`.
- `turns/0001` complete with reply (4091 chars), full sources array,
  populated `turnSummary` (elapsedMs=133942).
- 21 timeline events written to `events` subcollection across the run.
- Watchdog ran every 2 minutes and never flagged the session
  (`stuck=0 flipped=0` consistently).
- `agentstream` Cloud Function returned 202 in ~5 s for this request.

Vertex AI Reasoning Engine logs confirm: invocation_id
`e-e76365d7-…`, conversation `se-0db2323e-…`, full pipeline
context_enricher → research_lead → router fired between 21:30:27 and
21:32:32.

The reply has been sitting in Firestore the whole time. Reloading the
shared URL hydrates it on a fresh listener.

## Root cause: cold-start race in the 10 s `LOAD_TIMEOUT_MS` gate

### Deploy + idle drain set up the cold path

| Time (UTC, 2026-05-06) | Event                                                                                                        |
| ---------------------- | ------------------------------------------------------------------------------------------------------------ |
| 21:21:22               | Deploy of d3e4efd completes — new `agentstream` revision + new Firebase Hosting bundles                      |
| 21:09:04               | Last `agentstream` request before incident                                                                   |
| 21:09 → 21:29          | 20 minutes idle. Cloud Run scales `agentstream` to **0 instances**                                           |
| **21:29:36 (≈)**       | User clicks send on `/`. Browser does its first-ever load of new bundles, fires POST + `goto('/agent/chat')` |
| 21:29:45.989           | Cloud Run logs: `Starting new instance. Reason: AUTOSCALING — no existing capacity`                          |
| 21:29:47.456           | Container TCP probe succeeds                                                                                 |
| 21:29:47.850           | First session `b3507255-...` createdAt — txn finally commits                                                 |
| **21:30:11 (≈)**       | User submits the same prompt **a second time**                                                               |
| 21:30:16.933           | Second `agentstream` POST → 202. Latency 5 s (instance warm)                                                 |
| 21:30:17.099           | Second session `0db2323e-...` createdAt                                                                      |
| 21:30:27 → 21:32:32    | Both sessions run on Reasoning Engine in parallel; both complete                                             |

### Evidence the user submitted twice

Firestore has two sessions for the same UID `feadLLD5IuUrJNeQTPPu9QIg3wg1`,
same place `Monsun Gdynia`, with **identical** `userMessage`:

> "What are the foot traffic patterns in my neighbourhood by day and daypart?"

- `b3507255-4abe-4bb8-8817-ed5a74f0dbc9` — createdAt `21:29:47.850Z`,
  title "Neighbourhood foot traffic patterns".
- `0db2323e-3a59-4b29-85d6-a30322f161ea` — createdAt `21:30:17.099Z`,
  title "Foot traffic patterns neighborhood".

The first one (`b3507255`) is the one that hit the post-deploy cold start.
The user did not see it succeed, so they re-submitted, generating
`0db2323e` (the URL they shared).

### The race itself

Code is in `src/lib/chat-state.svelte.ts:288-422`
(`attachActiveListeners`). On submit, `selectSession(sid)` synchronously
sets `loadState='loading'` and fires `void attachActiveListeners(sid)`.
Inside that async function:

```
attachActiveListeners(sid)
├─ await ensureAnonAuth()                  // cold: ~0.5–2 s
├─ await getFirebase()                     // cold: fetch /__/firebase/init.json
├─ await import('firebase/firestore')      // cold: ~150–300 KB chunk
│
├─ loadState = 'loading'
├─ setTimeout(..., 10_000)                 // 10 s timer ARMED HERE — line 306
└─ onSnapshot(sessionRef, ...)             // listener attached
```

The 10 s timer at `chat-state.svelte.ts:306-310` flips `loadState` to
`'loadTimedOut'` if the listener is still in `'loading'` when it
fires. The listener clears the timer on the **first server-confirmed**
snapshot (`fromCache=false`), regardless of `exists`
(`chat-state.svelte.ts:321-326`). Cache-only snapshots
(`fromCache=true, exists=false` — the default for a fresh sid not in
IndexedDB) do **not** clear the timer.

So `loadTimedOut` fires precisely when no `fromCache=false` snapshot
arrives within 10 s of the listener attaching.

On the first post-deploy submit, three cold-paths stack:

1. **Browser bundle cold.** New bundle hashes after deploy → first
   download/parse of the firebase chunk.
2. **Firestore SDK init cold.** `initializeFirestore` with
   `persistentLocalCache` + `persistentMultipleTabManager`
   (`firebase.ts:73-78`) needs IndexedDB schema setup and leader
   election before opening a `Listen` RPC.
3. **WebChannel handshake cold.** First `Listen` RPC over WebChannel
   needs a full session-init handshake.

On the **server** side, the cold-start agentStream txn doesn't commit
until ~T+11 s after submit. Until then, even if WebChannel were up the
server has `exists=false` to push.

The two stacks combine: client opens the Listen at maybe T+3 s, server
has nothing useful until T+11 s, and the 10 s client timer (measured
from T+3) fires at T+13 — exactly the edge where it wins the race
against WebChannel's first push.

## Why each symptom maps cleanly

- **"0s timer".** `chatState.currentTurnStartedAtMs`
  (`chat-state.svelte.ts:702-707`) returns `latest.createdAtMs ?? null`.
  While `turns=[]`, `LiveActivity`'s `durationLabel`
  (`LiveActivity.svelte:161-165`) falls through to `0`. No fallback to
  "moment user clicked send".
- **"Didn't see my message".** `flattenTurnsToMessages`
  (`chat-state.svelte.ts:177-201`) is the only producer of the messages
  array. No optimistic local push of the user's message exists — the
  comment at `chat-state.svelte.ts:18-22` notes the design rejected a
  browser-local conversation store.
- **"Couldn't load this chat".** Only path with the doc actually present
  is `loadState='loadTimedOut'`. The page renders the error at
  `src/routes/agent/chat/+page.svelte:654-663`.

## Why subsequent prompts worked

By the second submit:

- IndexedDB schema is in place.
- `firebase/firestore` chunk is in the HTTP cache.
- WebChannel session handle is established (or mid-handshake).
- Cloud Run instance is warm (5 s latency, not 9.7 s).

None of the three cold paths apply. Same code, no race.

## Deepest root cause: `LOAD_TIMEOUT_MS` is defensive against an

## unrecoverable scenario

The cold start exposed the bug, but the bug is the timer itself.

`LOAD_TIMEOUT_MS = 10_000` was introduced in 5f810d5 (2026-04-23) as part
of the original server-stored-sessions feature. Its declared purpose, per
`docs/gear-post-review-fixes-plan-2026-04-27.md:20`, is "catches network-
blackhole cases without false-positiving on legitimate slowness."

Walking through what `loadTimedOut` actually catches:

- **Bogus sid in URL** — already handled by `'missing'`
  (`chat-state.svelte.ts:336`, server-confirmed `exists=false` outside the
  optimistic window). Doesn't need the timer.
- **Pre-Firestore POST failure** — already handled by the `startNewChat`
  catch path at `chat-state.svelte.ts:566-591` (`getDoc` check →
  `clearActiveState` → `loadState='missing'`). Doesn't need the timer.
- **Post-Firestore failure** — already handled by `gearHandoffCleanup`
  (`functions/gear-handoff.js:254-271`) writing `status='error'` to the
  session+turn under a `currentRunId`-fenced txn. Doesn't need the timer.
- **Network blackhole during initial load** — listener never connects.
  Timer flips to `'loadTimedOut'` and shows "Couldn't load this chat".
  But the user has no network; they can't refresh, recover, or do
  anything different from what they'd do at "loading". The timer adds
  no information and no agency.
- **Legitimately slow first load (cold start, post-deploy)** — false
  positive. This is the incident.

The timer protects only the network-blackhole case, where the user
can't act on the information. It produces false positives in the only
common case it actually fires in. Symptom-treatment of an
unrecoverable scenario.

## Recommended path

Ordered. This is what we should land.

1. **Delete `LOAD_TIMEOUT_MS`, `loadTimeoutHandle`, the `'loadTimedOut'`
   member of `LoadState`, the `setTimeout` block at
   `chat-state.svelte.ts:305-310`, and the `clearTimeout` calls in
   `detachActiveListeners` + the listener's `!fromCache` branch.** The
   `LoadState` type collapses to `'idle' | 'loading' | 'loaded' |
'missing'`. Slow connections show "loading" indefinitely — honest,
   no UI lie. Bogus sids still surface "Couldn't load this chat" via
   `'missing'`.

2. **Revert the route-template tweak.** Without `'loadTimedOut'`, the
   condition at `src/routes/agent/chat/+page.svelte:654` simplifies back
   to `chatState.loadState === 'missing'`. The
   `&& chatState.messages.length === 0` guard is vestigial.

3. **Delete the two `loadTimedOut` spec tests** at
   `src/lib/chat-state.spec.ts:364-377` and `:379-397`. They assert
   behavior we no longer have.

4. **Keep the optimistic-turn install** (`installOptimisticTurn` +
   listener guard). This is genuine UX — even on the warm path there's a
   1–2 s window where Firestore is propagating and the user otherwise
   sees a blank thread. With (1) in place, the listener guard is the
   only "complication" left, and it bridges real Firestore latency, not
   a broken timer.

Net LOC after all four: roughly break-even with what was just shipped
(≈ +25 LOC of optimistic-turn logic, ≈ −30 LOC from removing the timer
and its tests). The harmful mechanism is gone; the route + state
machine are simpler, not more layered.

## Explicitly not recommended

- **`min-instances=1` on `agentstream`.** Masks the trigger but the
  broken client mechanism would still false-positive on any other source
  of slow first load (browser bundle cold, slow network, WebChannel
  handshake under proxy). Infrastructure dollars to paper over a code
  defect, defect still present.
- **Increasing the timeout** (e.g., 30 s instead of 10 s). Same
  defensive timer, slightly less likely to fire, still no scenario
  where firing helps the user.
- **"Reconnecting…" + retry UX.** Adds surface area for a failure mode
  that, on inspection, isn't actionable.

## Investigation evidence trail

- Firestore session/turn/events read via REST with
  `gcloud auth print-access-token --scopes=cloud-platform`.
- `agentstream` Cloud Run request logs filtered to 2026-05-06
  21:25–21:55 — confirms the 9.7 s cold start at 21:29:45 and 5 s warm
  request at 21:30:16.
- Vertex AI Reasoning Engine logs grouped by
  `gen_ai.conversation.id` — confirms parallel runs of `se-b3507255`
  and `se-0db2323e` for the same UID with identical place context.
- Watchdog logs show `stuck=0 flipped=0` for every 2-minute scan during
  the incident window — rules out watchdog interference.
- Deploy timing from `gh run list --workflow=deploy.yml` — d3e4efd
  shipped at 21:21:22Z.
- Code paths cross-referenced in
  `src/lib/chat-state.svelte.ts`,
  `src/routes/agent/chat/+page.svelte`,
  `src/lib/components/agent/LiveActivity.svelte`,
  `src/lib/firebase.ts`,
  `functions/index.js`,
  `functions/gear-handoff.js`,
  `firestore.rules`.
