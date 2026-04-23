# Review of `server-stored-sessions-plan.md`

Reviewed on 2026-04-23 against the current repo state, the existing chat transport/frontend/deploy wiring, and Firebase/Firestore documentation. This was a source review, not a full test run.

## Verdict

The direction is strong, but the current plan is not implementation-ready yet.

Two revisions should happen before execution:

- the rollout/cutover story needs to be made actually compatible with the current split deploy workflow
- the sidebar semantics need to be made internally consistent

After that, there are two important but non-blocking scope misses to fold into the plan.

## Findings

### [P1] The rollout sequence is not backward-compatible with the current client

Plan sections:

- `docs/server-stored-sessions-plan.md:559-564`
- `docs/server-stored-sessions-plan.md:566-571`

Verified locally:

- The current frontend still treats the session doc as the sole terminal source: `src/lib/firestore-stream.ts:8-18`, `:176-223`.
- The current frontend still falls back to `agentCheck` on Firestore `permission-denied` and first-snapshot timeout: `src/lib/chat-state.svelte.ts:340-372`, `:647-706`.
- `agentCheck` still reads `reply`, `sources`, `title`, and `turnSummary` from the session doc: `functions/index.js:449-540`.
- The current deploy topology is explicitly split: worker/functions ship separately from hosting. `docs/deployment-gotchas.md` already treats that ordering as load-bearing, and `.github/workflows/deploy.yml` is designed around it.

Why this matters:

- Step 2 says the worker moves terminal state to turn docs and removes `agentCheck`.
- The old client cannot read turn docs yet and still expects `agentCheck` to exist.
- So the statement that step 2 is "backwards-compatible with the old client for the brief window before step 4" is false in the current repo.

This is not theoretical. In the current codebase, a worker/functions-first deploy would break two things during the real deploy window:

- terminal reply delivery for the old Firestore observer path
- REST recovery / cold-start fallback for the old client

What to change in the plan:

1. Either keep a temporary compatibility bridge:
   - continue writing session-level terminal fields until hosting is live
   - keep `agentCheck` until the frontend no longer depends on it
2. Or describe a true atomic cutover / maintenance-window deployment instead of a staged deploy.
3. Remove the "backwards-compatible with the old client" claim unless one of those bridges is explicitly added.

### [P1] The sidebar promise contradicts the proposed data model

Plan sections:

- `docs/server-stored-sessions-plan.md:94`
- `docs/server-stored-sessions-plan.md:171`
- `docs/server-stored-sessions-plan.md:275`
- `docs/server-stored-sessions-plan.md:589-590`
- `docs/server-stored-sessions-plan.md:710-716`

Verified locally:

- The plan says the sidebar should show "every chat you've touched", including one "viewed via a shared link from a colleague".
- The proposed data model only adds UIDs to `participants` when they submit a turn via `agentStream`.
- The manual test section then says a pure cross-device read leaves the sidebar empty until the incognito user contributes.

Those three statements do not describe the same product.

Under the proposed implementation, the sidebar means:

- every chat this browser has contributed to

It does **not** mean:

- every chat this browser has merely opened

Because client writes are explicitly blocked, "show viewed chats too" is not a free follow-on. It would require a new server-side "touch/open" write path or a broader rules change.

What to change in the plan:

1. Decide which product promise is actually intended.
2. If the intent is "contributed to", rewrite the product story, test plan, and decision table accordingly.
3. If the intent is "opened or contributed to", add the required server-side touch-on-open mechanism to the architecture and scope.

### [P2] The file inventory understates the actual integration surface

Plan sections:

- `docs/server-stored-sessions-plan.md:381-390`
- `docs/server-stored-sessions-plan.md:470-498`
- `docs/server-stored-sessions-plan.md:646-690`

Verified locally:

- `firebase.json` currently rewrites `/api/agent/check` and `/api/agent/stream`, but there is no route for a new delete endpoint.
- `vite.config.ts` proxies the same two endpoints in dev, and also has no delete route.
- `src/lib/components/Navbar.svelte:22-47` still reads `chatState.conversations.length` on `/agent`, not only inside `/agent/chat`.

Why this matters:

- `agentDelete` will not work in either dev or production without updating both `vite.config.ts` and `firebase.json`.
- The chat-count badge on the agent landing page will drift or stay zero if chat-list state is only initialized from the chat page after localStorage is removed.

The plan's current file tables omit those required changes, which makes the implementation look smaller and more isolated than it really is.

What to change in the plan:

1. Add `firebase.json` to the touched-file list.
2. Add `vite.config.ts` to the touched-file list.
3. Add `src/lib/components/Navbar.svelte` to the touched-file list.
4. Decide whether other chat-list consumers should be updated, removed, or left intentionally stale.

### [P2] Deleting `agentCheck` entirely gives up the exact cold-start/shared-link case this plan is trying to improve

Plan sections:

- `docs/server-stored-sessions-plan.md:377-379`
- `docs/server-stored-sessions-plan.md:619-623`

Verified locally:

- The current client explicitly falls back to `agentCheck` when Firestore snapshots fail or never arrive: `src/lib/chat-state.svelte.ts:364-372`, `:647-706`.
- The plan itself already acknowledges the new failure mode: first visit on a network blocking `*.googleapis.com` leaves the page blank because there is no cache yet.
- Firebase's offline-data docs note that when there is no cached document and no network path, a specific document fetch errors rather than returning usable data: [Access data offline](https://firebase.google.com/docs/firestore/manage-data/enable-offline).

Why this matters:

- This is not just an obscure offline edge case.
- It is most painful on a **new device / shared link / first open**, which is one of the plan's headline goals.

If the product wants "URL works on any device" to remain a strong claim, a small read-only backend fallback still earns its keep.

What to change in the plan:

1. Either keep a minimal read-only fetch endpoint for cold-start failures on empty-cache devices.
2. Or explicitly weaken the success criteria and product story so they no longer imply that a shared URL is expected to load in those environments.

## Smaller Notes

- `updatedAt` is only described as bumping on completion (`docs/server-stored-sessions-plan.md:181`). If the sidebar orders by `updatedAt`, a newly submitted follow-up may not sort as "just touched" until the answer lands. Decide whether submit-time recency matters enough to move `updatedAt` on enqueue or to add a separate `lastTouchedAt`.
- The privacy-update section should mention stored anonymous Firebase identifiers too, not only `placeContext` and internal session IDs. Under the proposed model, `userId` and `participants` are both readable to any URL holder.

## Bottom Line

The architecture is coherent, but the current draft still overclaims in two places:

- deploy compatibility
- sidebar behavior

Fix those first. Then fold in the omitted routing/bootstrap files and make an explicit decision on whether the cold-start REST fallback is intentionally being abandoned or should stay in a smaller form.

---

# Plan-author response — 2026-04-23

I verified each finding against the current code. Reviewer is right on all four. Below is my assessment per finding and what I will change in the plan.

## [P1] Rollout backwards-compat — confirmed broken

Verified at `src/lib/firestore-stream.ts:200-218`: the existing client reads terminal `status, reply, sources, title, turnSummary` directly from the session doc. Under the proposed model the worker stops writing those fields at the session level (they move to per-turn docs). During any worker-deployed-before-hosting window — which is what `.github/workflows/deploy.yml` produces by design — old browser tabs would never see terminal state, and their `agentCheck` REST fallback would also return null because `agentCheck` reads the same session-level fields (`functions/index.js:512-519`).

My "backwards-compatible with the old client for the brief window before step 4" claim was wrong.

**What to change in the plan (§14 Rollout):**

Adopt a small **dual-write bridge during transition**:

- Worker writes terminal state to BOTH the new turn doc AND the legacy session-level fields (`reply`, `sources`, `title`, `turnSummary`) for one deploy cycle.
- After hosting is confirmed live and stale tabs have refreshed (12–24 hours of natural traffic), a follow-up commit removes the legacy session-level writes.
- Cost: ~5 lines of additional worker writes during transition. Removed in a small follow-up commit.

Alternative considered and rejected: maintenance-window atomic deploy. Heavier than the bridge for our user base, and the bridge is genuinely small. Going with the bridge.

The "backwards-compatible" claim in the plan should be removed; it's replaced by a real bridge.

## [P1] Sidebar promise contradicts model — confirmed

Reviewer correctly identifies that the plan promises "every chat you've touched, including ones viewed via a shared link" but the implementation only updates `participants` on `agentStream` writes (which only fire on contribute/follow-up, not on read). A pure read-only viewer never enters the participants array.

**What to change in the plan:**

Drop the read-only-viewed promise. The new sidebar contract becomes:

> **Sidebar = chats you've contributed to (created or replied in).**

If you want a chat you only viewed in your sidebar, ask one follow-up — or bookmark the URL.

Reasoning for not adding "touch on open" instead:

- A new server-side touch endpoint adds one network round-trip per chat open and a server write on every read (more cost, surprising side effect, harder to reason about).
- Allowing client direct-writes to the participants array breaks the "all writes server-only" invariant that keeps the security model simple.
- The product win is small (you can re-find a chat you only glanced at via the sidebar instead of via bookmark/history).

Files to update in the plan:

- §3 Product story — remove the "viewed via a shared link from a colleague — they all show up" sentence.
- §4 Architecture overview — clarify the `participants` semantics.
- §15 Test plan, scenario 2 (cross-device read) — explicitly say the sidebar stays empty until the visitor contributes a turn. That's the correct expected behavior, not a bug.
- §20 Open questions / decisions captured — update the "Sidebar scope" decision row to reflect "contributed to" rather than ambiguously "every chat I've touched."

## [P2] File inventory understates — confirmed

Verified each:

- `firebase.json:80,84` declares rewrites for `/api/agent/check` and `/api/agent/stream` only — needs new entry for `/api/agent/delete` (and `/api/agent/read` per [P2] below).
- `vite.config.ts:29,34` mirrors those rewrites in dev — same gap.
- `src/lib/components/Navbar.svelte:22` reads `chatState.conversations.length` for the chat-count badge on the agent landing — needs to switch to `chatState.sessionsList.length`.

There may be additional stale references; a project-wide grep for `chatState.conversations` is part of the pre-implementation audit.

**What to change in the plan (§18 Files affected):**

Add to the Frontend section:

- `src/lib/components/Navbar.svelte` — modify (one line: `chatState.conversations.length` → new equivalent).

Add to the Backend section (under the routing layer):

- `firebase.json` — modify (add rewrites for `/api/agent/delete` and `/api/agent/read`).
- `vite.config.ts` — modify (same rewrites for the dev proxy).

Also add a pre-implementation audit step: grep the repo for any other `chatState.conversations` reads and update them in the same change.

## [P2] Deleting `agentCheck` loses cold-start case — has merit, partially adopt

Reviewer is right that this directly contradicts a headline goal. The first-visit-on-blocked-network case is the worst version of the cold-start problem AND the cross-device-shared-link scenario the plan is selling.

The Firebase SDK's listener uses gRPC over a long-lived connection that some corporate proxies and ad-blockers (`*.googleapis.com`) block. The Cloud Function at `agent.superextra.ai/api/agent/*` is at a different domain and may still work in those environments. Today's `agentCheck` REST fallback exists precisely to cover this case.

**What to change in the plan:**

Replace "delete `agentCheck` entirely" with "replace `agentCheck` with a small read-only `agentRead(sid)` endpoint":

- `agentRead(sid)`: returns session metadata + the latest N (say 10) turns. Used only when the listener fails or never delivers within a timeout. ~30 lines.
- The frontend keeps a one-shot REST fetch as the cold-start fallback, but loses the heavier `chat-recovery.ts` polling loop (the listener IS the resume path; we only need a one-shot fallback for the no-cache-no-listener edge case).
- Net: still a significant simplification vs today's REST polling, while preserving the cold-start guarantee.

Specific plan-section updates:

- §8 Backend changes: replace "agentCheck — DELETED" with "agentCheck — REPLACED by smaller `agentRead`".
- §9 Frontend changes: keep a small fallback path in chat-state for the no-cache + listener-failure case. `chat-recovery.ts` still goes away (it's the polling loop, not the fallback itself).
- §16 Risks: the "First visit on a fully-blocked network shows blank" risk is now substantially mitigated.

## Smaller notes — both adopted

- **`updatedAt` on enqueue, not just complete**: agreed. Otherwise the sidebar lags by 1–6 minutes after a follow-up. The fix: `agentStream` sets `updatedAt: serverTimestamp()` in the same transaction that creates the turn doc. One line. Add to §8 backend changes (agentStream changes list).

- **Privacy copy must mention `userId` and `participants`**: agreed. Both are anonymous identifiers but both are durably stored and readable to any URL holder. Add to §12 Privacy implications: "Stored identifiers include the original creator's anonymous browser identifier (`userId`) and a list of every browser identifier that contributed to the chat (`participants`). These are not personally identifying but are accessible to anyone with the chat URL."

## Net effect on the plan

Six concrete revisions:

1. §14 Rollout — replace the false "backwards-compatible" claim with the dual-write bridge.
2. §3, §4, §15, §20 — change sidebar scope to "contributed to" and align all references.
3. §18 — add `firebase.json`, `vite.config.ts`, `src/lib/components/Navbar.svelte` to the file inventory.
4. §8, §9, §16 — replace "delete agentCheck" with "replace with small agentRead", keep one-shot REST fallback.
5. §8 — bump `updatedAt` on enqueue in agentStream's turn-creation transaction.
6. §12 — privacy copy mentions `userId` and `participants` durability.

Estimated impact on plan scope: roughly the same overall (the `agentRead` endpoint adds back ~30 lines I had cut; the sidebar narrowing removes nothing material in scope; the file inventory adds three files but each is a one-line edit). The net effort estimate in §Appendix B (12-15 working days) doesn't move meaningfully.

## What I am NOT changing

- The product story for "URL = the chat" stays as-is — anyone with the URL can read, continue, delete. The reviewer didn't push back on this and the model is intentional.
- The data shape (sessions / turns / events as three layers, `participants` array on the session) stays.
- The 10-turn-per-session cap and existing per-IP rate limit stay as the abuse defenses.
- The decision to clean-slate existing data on cutover stays.
- The decision to keep chats forever (no expiry) stays.

## Bottom line

Reviewer's two P1 findings are correct and load-bearing — they need to be in the plan before implementation starts. The two P2 findings are smaller but real and easy to address. After folding all six revisions in, the plan is implementation-ready.
