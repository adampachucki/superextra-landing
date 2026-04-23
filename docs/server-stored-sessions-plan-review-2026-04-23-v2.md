# Review of `server-stored-sessions-plan.md` (v2)

Reviewed on 2026-04-23 against:

- the current codebase (client in `src/lib/`, server in `functions/`, worker in `agent/worker_main.py`, rules/indexes)
- the previous review notes at `docs/server-stored-sessions-plan-review-2026-04-23.md`
- Firebase/Firestore SDK behavior
- ADK Vertex Agent Engine session semantics

This is a source review plus external-behavior verification, not a full test run.

---

## Verdict

**The architecture is the right direction and the plan is ~85% implementation‑ready.** The data model, security model, and deletion story are coherent, the capability-URL framing matches the product goal, and the code reductions claimed are real. The previous reviewer's two P1 findings were folded in correctly (sidebar semantics, file inventory).

**Two things regressed between the prior review response and the current plan** and need a conscious decision before implementation:

1. The plan drops `agentCheck` entirely, but the only mitigation for the cold-cache + blocked-network case is "show `Couldn't load this chat` after 10 seconds." The plan's own Appendix C Test 2 documents that failure mode — and it is exactly the cross-device-shared-link case the plan is selling.
2. The rollout bridge the plan author agreed to in the prior response was silently replaced by "accepted as-is." During a 1–3 minute window, any open tab's in-flight turn is undeliverable. That's fine pre-launch; it should be stated explicitly as a pre-launch-only decision so it doesn't carry forward silently.

There are also several root-cause / simplification calls worth making, listed below.

---

## Findings

Each finding is labeled with:

- **[P1]** — blocks implementation until decided
- **[P2]** — non-blocking but should be resolved before coding starts
- **[P3]** — polish / post-implementation cleanup

### [P1] The cold-cache + blocked-network case is a regression that contradicts a headline product goal

Plan sections:

- §7 "Cold cache on a blocked network"
- §8 "`agentCheck` Cloud Function — DELETED"
- §16 risk #5
- Appendix C Test 2

Verified against current code:

- The current client has a REST fallback at `src/lib/chat-recovery.ts:76–128` that is triggered when `onSnapshot` hits `permission-denied` or the 10‑second first-snapshot timeout (`src/lib/firestore-stream.ts:107,144–154`, `src/lib/chat-state.svelte.ts:647–706`).
- `agentCheck` (`functions/index.js:463–545`) reads `reply/sources/title/turnSummary` from the session doc — the REST fallback works on restrictive networks because `agent.superextra.ai/api/agent/check` is a distinct hostname from `firestore.googleapis.com` (often blocked by corporate proxies and content blockers).
- Appendix C Test 2 in the plan itself confirms the failure mode: on a cold cache with backend unreachable, `onSnapshot` emits one immediate `fromCache:true`, `exists():false` snapshot and hangs indefinitely.

Why this matters:

The plan's own product story (§3) and success criteria (§2) claim "a URL is genuinely a chat" and "opening a chat URL on any device shows the full conversation history." The scenarios where this is most valuable — corporate laptops, restrictive mobile carriers, stricter content blockers — are exactly the ones that most often block `*.googleapis.com`. On those networks, after this plan ships, a shared URL renders "Couldn't load this chat" within 10 seconds. Today it renders the chat.

The prior review already surfaced this and the plan author agreed to replace `agentCheck` with a smaller read-only `agentRead(sid)` endpoint. The current draft silently dropped that agreement without explanation.

**Recommendation — root-cause fix, not defensive design.**

Restore a minimal, purpose-built read endpoint. The previous REST fallback is excessive (60 poll attempts, 3‑second intervals, 3‑minute window, terminal-reason mapping, `isDuplicateReply` callback) because it was built as a _durable_ fallback. What's needed after this rearchitecture is a _cold-cache one-shot_, because the listener IS the resume mechanism.

Concretely:

- `agentRead(sid)`: GET, requires Firebase ID token, returns `{ session: {...}, turns: [...latest N] }`. ~30–40 lines.
- Frontend calls it exactly once, from the 10‑second cache-only timeout branch in §7, then continues to trust the listener.
- Kill `chat-recovery.ts` (128 lines) outright — its polling loop is what goes away; the fallback itself becomes a single `fetch`.

Net: still a significant simplification vs. today (128 → ~40 lines, polling → one-shot, two code paths → one), while preserving the product promise.

Alternative that _is_ acceptable: keep the plan as-is, but weaken §2 success criteria and §3 product copy to stop claiming "URL works on any device." It's a legitimate product call to drop the promise. What's not acceptable is keeping the promise while removing the mechanism and papering over it with a 10‑second timeout UI.

### [P1] The rollout section silently walked back the dual-write bridge

Plan sections:

- §14 Rollout sequence, "Accepted behavior … This mixed window is accepted as-is. There is no compatibility write layer for it."
- Previous review response (`docs/server-stored-sessions-plan-review-2026-04-23.md:165–174`)

Verified against current code:

- `src/lib/firestore-stream.ts:170–224` reads terminal `status/reply/sources/title/turnSummary` from the session doc. An old tab between worker-deploy and hosting-deploy sees a completed session doc with `reply: null` because the worker now writes terminal content to the turn doc (plan §8 worker change #5).
- `.github/workflows/deploy.yml` is designed as a staged deploy: `deploy-worker` → `deploy-hosting`. The mixed window is inherent to the workflow, not a one-off. Typical duration is 1–3 minutes.

The prior response committed to a ~5‑line dual-write bridge (worker writes terminal state to both the turn doc and the legacy session-level fields for one deploy cycle, then removed). The current plan replaces that with "accepted as-is." Nothing in the §14 text explains why the position changed.

Why this matters:

- Accepting the breakage is a reasonable decision **given the pre-launch user base**. It is not obviously correct, and it becomes less correct as usage grows. Silently dropping the bridge means this trade-off isn't recorded for future-us.
- The new rollout has a subtler teeth: §14 step 1 is "add the new Firestore composite index and wait for it to become ACTIVE." Index builds on a small dataset are fast, but this step is a human blocker before the GitHub Actions deploy can run. Today's workflow doesn't separate index deploy from hosting deploy. The plan should say who runs step 1 and how step 2/3 know it completed.

**Recommendation:**

Make the decision explicit. One paragraph in §14 saying:

- "Pre-launch user base is small enough that a 1–3 minute breakage of open tabs is acceptable. A dual-write bridge was considered and rejected as unnecessary overhead at current scale. If this plan is re-applied post-launch, revisit and implement the bridge first."
- Plus: explicitly call out step 1 as a pre-workflow operator step, and verify the index-ACTIVE state is what gates step 3.

If pre-launch is not a shared assumption, adopt the 5‑line bridge. It is genuinely cheap and removes the rollout risk entirely.

### [P1] The mixed-window recovery path has an unstated coupling to the Cloud Tasks payload

Plan section:

- §8 worker change #3: "That mixed-window recovery cannot rely on session state alone, because the old session doc does not store the raw user message. The worker must reconstruct `userMessage` from the task payload, stripping the server-added prefixes from `queryText`."

Verified against current code:

- `agentStream` today adds `[Date: ...]` and on first-message also `[Context: ...]` prefixes to `queryText` before enqueuing the Cloud Task (`functions/index.js:301–309`).
- `_strip_query_prefixes` at `agent/worker_main.py:397–409` already peels both prefix types. Good, the utility is reusable.

Two gaps:

1. The new-shape task body in §8 agentStream change #7 should include an explicit `turnIdx` field. Otherwise the worker has two ways to find the turn doc — by `runId` field scan or by `lastTurnIndex` read — and both are worse than passing the index directly in the task payload that the agentStream transaction already has.
2. The "mixed-window missing-turn creation" depends on the worker knowing (a) whether the enqueued task is old-shape or new-shape, and (b) how to derive `turnIdx` in the old-shape case. The plan doesn't specify either. The simplest rule: if the task body has `turnIdx`, trust it; otherwise derive from `session.lastTurnIndex` (which the old agentStream didn't write either — so the worker would need to allocate `0001` as a best-effort recovery, which is wrong for follow-ups).

**Recommendation:**

Keep the mixed-window recovery as simple as possible:

- New task body always includes `turnIdx` (plus the existing `runId`, `userId`, `queryText`, `isFirstMessage`).
- Old-shape-task recovery is only needed for tasks enqueued between "old worker stops" and "new agentStream starts." Given the plan already accepts a 1–3 minute breakage of open tabs, the right call is **don't implement mixed-window recovery at all**. The worker rejects old-shape tasks with a clean error, and any affected request is lost (user refreshes and re-submits).

That removes worker change #3 entirely. It removes the reconstruction-from-prefix coupling. It removes the "allocate turn 0001 as best effort" ambiguity. It matches the plan's already-accepted position that the mixed window is a known 1–3 minute breakage.

If you adopt the dual-write bridge from the previous finding, drop this one too — the bridge removes the need for mixed-window recovery because old and new clients both see terminal state.

### [P2] Capability-URL delete is a genuine collaborative foot-gun

Plan sections:

- §6 "Delete — Chats are hard-deleted by capability URL"
- §16 risk #4
- §17 "Soft-delete / undo window for deletion" — deferred

Verified against current code:

- No existing delete endpoint (confirmed in `functions/index.js`).
- Today's `deleteConversation` is local-only (`src/lib/chat-state.svelte.ts:764–821` public API), so today there is no shared-state destruction risk. This plan introduces that risk.

Why this matters:

The plan's threat model for **read** leverages the capability-URL argument well: 122 bits of entropy, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`. That model correctly handles the asymmetry that leaked URLs give read access, not write access in the broader sense. But for the narrow write of `delete`, the plan allows any URL holder to hard-delete. In a shared-URL-with-a-colleague flow (the central product scenario!), that means:

- A colleague clicking delete by accident nukes the chat for the creator and everyone else.
- A malicious recipient destroys a research thread the creator needed.
- There is no undo.

This is the plan's only **destructive** operation and it's available to everyone who holds the URL. That is asymmetric to the read/write-follow-up model which is additive-only (new turns, new participants) and therefore safe.

Two options, either acceptable:

**Option A (root-cause fix, simpler model):** creator-only delete.

- `sessions/{sid}.userId` already stores the creator's anon UID.
- `agentDelete` checks `request.auth.uid === session.userId`, otherwise returns 403.
- This keeps "URL = read + continue" for everyone and "URL + creator identity = delete" for the creator.
- Cost: creators in incognito who lose their anon auth can no longer delete their own chats (this is the same problem as today). That's acceptable.

**Option B (deferred but documented):** keep capability-URL delete, add a 30‑day soft-delete with `deletedAt` and a trash view.

- More scope. Probably overkill at current scale.

I'd lean Option A. It matches the "writes are server-only and scoped" invariant. It's a ~3‑line change to `agentDelete`. It preserves the plan's simplicity without introducing a destructive foot-gun.

The plan explicitly says no to Option B. It should explicitly say yes or no to Option A. Currently it does neither and lands on the weaker position by default.

### [P2] `userId` and `adkSessionId` leak to anyone with the URL

Plan section:

- §6 security rules (`allow get: if request.auth != null`)
- §12 Privacy implications

Verified:

- Under the plan's rules, any signed-in visitor can `get` the session doc. That doc contains `userId` (the creator's anon UID) and `adkSessionId` (Vertex Agent Engine session ID). Both are opaque identifiers, neither is personally identifying on its own.

`userId` exposure is acknowledged in §12 — fine. `adkSessionId` is not mentioned. It's not a capability (Vertex doesn't grant direct caller access — only the worker can read it via its service account), but it is a stable identifier the client doesn't need to know. Leaving it on the client-readable session doc is harmless but also pointless.

**Recommendation (minor, post-launch polish):**

- Split into `sessions/{sid}` (client-visible metadata) and `sessions_private/{sid}` (server-only with `adkSessionId`, `currentWorkerId`, `currentAttempt`, heartbeat fields).
- This also removes a bunch of operational state from the client-readable doc, which is currently triggering client-side listener updates on every heartbeat tick (see [P2] below on listener cost).

Not blocking. Worth scheduling as a small follow-up.

### [P2] The sidebar listener is noisier than necessary because operational fields live on the same doc

Plan sections:

- §4 "active session listener"
- §7 "Firestore SDK configuration" (persistent cache)
- §16 risk #2 "Sidebar listener cost"

Verified against current code:

- The worker writes `lastHeartbeat` every 30 seconds (`agent/worker_main.py:361`), `lastEventAt` on every ADK runner event (`agent/worker_main.py:1049`), `currentAttempt`/`currentWorkerId` on takeover (`agent/worker_main.py:285–291`).
- Today these writes are invisible to the client (rules block session doc reads except to the creator), so they have no listener cost.
- Under the new plan:
  - Every chat in the sidebar that is currently `running` will fire `onSnapshot` on the sidebar listener roughly every 30 seconds (heartbeat) and potentially more often on `lastEventAt` bumps.
  - The active session listener fires on the same writes.
  - For a user with many running chats at once (today: 1 in-flight cap per chat, but multiple chats each in-flight is possible from different tabs/devices), this is tens of snapshot events per minute per chat.

This is **real** client-side noise: each snapshot triggers Svelte reactivity, potentially re-sorting the sidebar, and burns mobile battery.

**Root-cause fix:** move heartbeat/attempt/worker fields off the client-readable doc. This is the same `sessions_private/{sid}` split as the previous finding.

**Alternative if you don't split docs:** use a `snapshotListenOptions` filter on the sidebar listener so heartbeat-only changes don't trigger re-renders. Firestore doesn't support field-level filtering on snapshots, so this would need client-side diffing (compare new/old doc, skip if only liveness fields changed). That's defensive code. The doc split is cleaner.

Do the split. It's the simpler end state.

### [P2] Watchdog turn-doc writes need fencing, not just "for UI consistency"

Plan section:

- §8 watchdog change: "flips the in-flight turn doc to `status='error'` for UI consistency"

Verified against current code:

- `functions/watchdog.js:152–169` today performs transactional flips with race-safe verification: re-reads session doc, checks status/currentRunId/threshold-field, only then updates. This prevents a live worker from having its status clobbered.
- The plan adds a second write target (the turn doc) without specifying the same verification.

Why this matters:

If the watchdog flips session + turn doc to error based on stale data (worker heartbeat delayed due to GC, then recovered), the worker's subsequent terminal write via `_fenced_update` is blocked on session — good — but the turn doc is already marked error. The worker never touches the turn doc after that because its fenced transaction fails first and it re-raises. Result: session status disagrees with turn status (session back to running, turn stuck at error).

**Recommendation:**

The turn-doc flip belongs _inside_ the same transaction as the session-doc flip. The transaction reads both docs, verifies the session's (currentAttempt, currentWorkerId, lastHeartbeat) just like today, and if verified, writes both docs. If either write conflicts with a concurrent worker transaction, the whole flip aborts. This is equivalent to today's race-safe watchdog, just widened to a second doc.

Plan text should be: "the watchdog's transactional flip includes the in-flight turn doc in the same transaction; same race-safe verification applies." That's a one-line plan edit and a small implementation change to batch both writes inside `runTransaction`.

### [P2] The 10-turn cap transaction and `lastTurnIndex` allocation need to be one atomic unit

Plan section:

- §5 data model: "`lastTurnIndex` | number | Highest appended turn index."
- §8 agentStream change #4: "Create `sessions/{sid}/turns/{turnIdx}` in the same transaction that updates the session doc."

Verified against current code:

- Today there is no turn doc and no `lastTurnIndex`. New.

Edge cases the plan doesn't address explicitly:

1. **Initial value**: what is `lastTurnIndex` on a brand-new session? The plan needs to commit: either `undefined`/missing → treat as -1, first turn becomes `0000`; or `-1` → first turn becomes `0000`; or `0` → first turn becomes `0001`. I'd suggest: `lastTurnIndex` is not written until the first turn is created, and the first turn is index `0001` (1-based, matches the plan's example `0001`, `0002`). That keeps the doc clean.
2. **10-turn cap atomicity**: the transaction must read `lastTurnIndex`, check `< 10`, then write turn N+1 and update `lastTurnIndex`. All three in the same transaction. The plan says this (§8 agentStream change #2+#4+#5). The test coverage list in §15 mentions this. Good. Add an explicit test that two concurrent submissions don't both succeed at the cap boundary — today's transactional retry will handle it, but test pins it.
3. **`one in-flight turn per chat`**: where is this enforced? Today (`functions/index.js:248–250`) it's an in-transaction check on the session doc's `status`. Plan doesn't explicitly restate this but the check carries over. Restate in §8 agentStream change list for clarity.

Not blocking, but the plan should nail the numbering convention and the cap test before coding starts.

### [P2] The `events` TTL value is underspecified

Plan section:

- §11 "keep a short Firestore TTL of 1–3 days"
- §16 risk #6 (implicit operational impact)

Verified against current code:

- Current TTL is 30 days (`firestore.indexes.json` fieldOverrides for `events.expiresAt`).
- `agent/superextra_agent/firestore_events.py:14` sets `EVENT_TTL_DAYS = 30`.
- Events are written with `expiresAt = now + 30 days` on every worker event.

Two issues:

1. "1–3 days" is a range, not a decision. Firestore TTL is set via `fieldOverrides` and operates on an absolute timestamp. The decision needs to be one number that the worker writes.
2. Shortening the TTL means post-completion users who open an old chat see the timeline events disappear after N days. The plan's §10 says "shared visitors see the same live timeline as the creator" — but only while the run is active. After completion, events are operational artifacts. The `turnSummary` on the turn doc is the durable record. Confirm this intent in §11 and pick a number — 3 days is a safe default that handles re-runs and debugging.

One-line fix in the plan. Keep as P2 only because it's a config value, not an architectural issue.

### [P2] Typewriter / drafting handoff when loading an in-flight chat on a new device

Plan section:

- §10 "the drafting → typewriter handoff" is unchanged

Verified against current code:

- Today the typewriter animation state is tied to the current run's reply arriving. On a fresh device opening an in-flight chat, there is no running typewriter — the reply hasn't arrived yet. When it arrives, the typewriter animates. OK.
- But consider: device A starts a chat, gets the reply, closes the tab. Device B opens the URL. The turn doc already has `status='complete'` and the full `reply`. Should device B see the typewriter animation (it feels "just delivered") or plain text (it's historical)?

The plan doesn't specify. The current code has no equivalent case because local-storage-based chats always have full history pre-rendered.

**Recommendation:**

- Plain text rendering for turns that are already `complete` on initial load. Typewriter only for the status-transition `running → complete` that happens while the current browser session has the chat open.
- Detect this by tracking "did I observe this turn's `running` state before its `complete` state?" If yes, animate. If no, plain render.
- One sentence in §10 and a Vitest case.

Not blocking the architecture; will save a UI-review cycle later.

### [P3] Simplification: fold the 10‑second cache-only timeout into the listener itself

Plan section:

- §7 "The UI rule is: render 'Couldn't load this chat' only after either a `fromCache: false` snapshot confirms missing, or 10 seconds have elapsed with only cache-only snapshots"

This is the only new load-state logic the plan adds. It's described as three states (cache-only unconfirmed / server-confirmed missing / loaded) plus a timer. Implementation in Svelte 5 runes is ~20 lines.

If you keep the `agentRead` cold-cache fallback from [P1] #1, the 10-second timer becomes "after 10 seconds of no server confirmation, one-shot `agentRead(sid)`, then resolve." That collapses the three states into two (loading / loaded-or-error) and removes the UI rule entirely — because `agentRead` either returns data (loaded) or confirms missing (missing).

This is the same observation that made [P1] #1 cheap: the fallback endpoint doesn't add complexity, it _removes_ a three-state load model that the plan currently has to introduce to cover the hole.

### [P3] Simplification: `chat-recovery.ts` becomes ~10 lines inlined, not a separate file

Plan section:

- §9 "`src/lib/chat-recovery.ts` — DELETE"

Agreed the current 128‑line polling module goes. If you keep a one-shot cold-cache `agentRead` fetch, it lives as a private helper in `chat-state.svelte.ts` (~10 lines: `async function coldCacheFetch(sid) { ... }`), not a separate file. The plan can stay with "delete `chat-recovery.ts`" — just note that the replacement is inlined rather than a new file.

### [P3] Simplification opportunity: `runId` dedup scaffolding removal gets easier with the turn-doc listener

Plan section:

- §9 "runId-based reply deduplication layer" — deleted

Current `appendedReplyForRunId` dedup in `src/lib/chat-state.svelte.ts:65–70,305–347` exists because two sources can deliver the same terminal (Firestore observer + REST recovery). Under the new model there is exactly one source per turn (the turn doc), and its state is idempotent — rendering from "whatever the turn doc currently says" is a no-op on duplicate snapshots.

Confirm the plan intends this: the UI should render from `turn.status`, `turn.reply`, `turn.sources`, `turn.turnSummary` as derived state with no special "first delivery" flag. No dedup, no "terminal once" guard, no `appendedReplyForRunId`. Good.

### [P3] Polish: specify `participants` initialization on first submit

Plan section:

- §5 data model, §8 agentStream change #3

The plan uses `FieldValue.arrayUnion(uid)` which correctly handles the "doesn't exist yet" case by creating the array. Fine — worth confirming the agentStream transaction uses `set(..., { merge: true })` or an `update` after a `get`-miss check, because `update()` on a non-existent doc fails.

For first-message: `t.set(ref, { ..., participants: [uid] })`. For follow-up: `t.update(ref, { participants: FieldValue.arrayUnion(uid), ... })`. Plan implies this but doesn't spell it out.

### [P3] Polish: test for rules-query alignment

Plan section:

- §6 rules, §15 rules tests

The `allow list: ... && request.auth.uid in resource.data.participants` rule requires the client query to include `where('participants', 'array-contains', uid)`. If the client forgets, the list is denied. Add a rules-emulator test that:

- with the correct `array-contains`, returns expected results
- without the `array-contains`, returns `permission-denied`

This pins the client's sidebar query shape into the test suite.

---

## Summary of Recommended Changes

**Blocking (must resolve before implementation):**

1. **Restore a minimal `agentRead(sid)` endpoint** (~30 lines) to cover the cold-cache + blocked-network case, or explicitly weaken §2/§3 product claims. Current "10‑second timeout then error" is a real regression on the cross-device-shared-link promise.
2. **Decide on the rollout bridge explicitly.** Either adopt the previously-agreed 5‑line dual-write bridge, or document in §14 that the 1–3 minute breakage is an accepted pre-launch-only trade-off with a revisit trigger. Also call out §14 step 1 (index build) as a human-gated pre-deploy step.
3. **Drop mixed-window recovery in the worker.** With the accepted 1–3 minute breakage already in the plan, the worker's "create missing turn doc at takeover" path adds complexity for a case the plan is already accepting breaks. Include `turnIdx` in new task payloads; reject old-shape tasks cleanly.

**Strongly recommended:**

4. **Creator-only delete** (swap `request.auth != null` → `request.auth.uid === session.userId` on `agentDelete`). Removes the only destructive capability that currently rides along with URL possession.
5. **Split `sessions/{sid}` into public metadata + `sessions_private/{sid}` for operational state.** Keeps heartbeat/attempt/worker-id writes from spamming the sidebar listener; keeps `adkSessionId` off the client-readable surface.
6. **Include the turn doc in the watchdog's race-safe transaction.** Currently the plan treats it as a secondary write, which creates a state-disagreement race with a live worker.

**Polish (can land with implementation):**

7. Pin the `events` TTL to one concrete number (3 days recommended).
8. Decide the `lastTurnIndex` convention (1-based, not written until first turn).
9. Specify the typewriter rule for pre-completed turns on initial load.
10. Add a rules-emulator test that pins the sidebar query's `array-contains` requirement.
11. Add explicit `set` vs `update` guidance for the agentStream transaction's first-submit vs follow-up branches.

---

## What the plan got right

For the record, these parts hold up under review and should not change:

- The three-layer data model (`sessions/{sid}` + `turns/{turnIdx}` + `events/{eventId}`). Maps cleanly to the product story and to the existing worker + watchdog scaffolding.
- The capability-URL framing for read/continue. Entropy, `Referrer-Policy`, `X-Robots-Tag` are the right mitigations.
- The `participants` field purpose and the "contributed to, not merely opened" sidebar semantics. Correctly resolved from the prior review.
- The deletion of `ios-sse-workaround.ts`. Listener resumption across offline→online is documented and verified in Appendix C Test 4.
- The turn-doc as the terminal source for rendering. Removes the session-doc listener from the terminal path and makes state rendering idempotent.
- The `updatedAt` bump on enqueue AND on terminal write. Correct fix from the prior review.
- The file inventory now including `firebase.json`, `vite.config.ts`, and `Navbar.svelte`. Correct fix from the prior review.
- Keeping existing worker fencing / takeover / heartbeat / watchdog scaffolding. Core reliability primitives are preserved.
- Clean-slate data cutover. Pre-launch, this is the right call.

---

## Bottom line

Fix #1, #2, #3. Decide #4–#6. Land the polish items with implementation. After those, the plan is implementation-ready and the architecture is sound.

The two critical gaps are not design flaws — they're walkbacks from an earlier, better position that were not justified in the current draft. Restoring them costs ~35 lines of code total and removes two product regressions.
