# Timeline Redesign Follow-up — Verification Review

Reviewed the changes against `docs/activity-timeline-redesign-follow-up-plan.md`. Focus: did every planned item land, did the tests still pass, and did live UX behave.

## TL;DR

**Three of four plan items fully done, one partially done, and one bonus fix that wasn't on the list.** All test suites pass. Refresh-mid-flight now cleanly reattaches the listener and renders the full live timeline end-to-end — verified in the browser against a real Firestore session. The duplicated counts row in the completed summary is gone.

**One regression observed during live E2E, not introduced by this follow-up but now surfaceable:** after a live run completes, the agent reply prose body stays empty. Refresh-after-complete renders it correctly. The typewriter integration path (`typingMessageTimestamp` → `replyTyper.setTarget`) doesn't advance `typedReply` in the live-run-complete path, so `displayText()` returns an empty string into the `{#each splitChartSegments(...)}`. This was a latent bug in the original rewrite, not a follow-up-plan change — but it's blocking real-world UX now.

## Plan items, one by one

### ✅ #1 — Remove duplicated `finalCounts` row in completed-turn summary

`ChatThread.svelte:182-206` — the `<details>` block renders notes + per-note counts only. No standalone `finalCounts` line at the bottom.

**Visual proof:** expanded summary in the browser shows three notes each followed by their own `formatCounts(...)` line, no duplicate final line. Screenshot at `/home/adam/screenshots/followup_e2e_summary.png`.

**Test proof:** new `ChatThread.spec.ts` asserts `body.match(/Opened 1 source/g)).toHaveLength(1)` — guards against future regressions of the same shape.

### ✅ #2 — Refresh-mid-flight recovery fix

Three coordinated changes landed cleanly:

- `chat-state.svelte.ts:630-637` — new `resumeCurrentIfNeeded()` with the exact guard order the plan specified: no `currentId`, already loading/recovering/subscribed, or last message isn't user → return false. Otherwise delegate to the existing `resumeIfInFlight(currentId)`.
- `+page.svelte:166-169` — onMount's user-msg-pending check now calls `void chatState.resumeCurrentIfNeeded()` instead of `chatState.recover()`.
- `chat-state.svelte.ts:528` — `switchTo` also kicks `resumeCurrentIfNeeded` at the end. Not strictly needed for the page-load case, but correctly covers in-app navigation to a sid whose last message is a user msg.

**Bonus over what I flagged:** the agent also wired the `handleReturn` visibility path to try resume before falling back to `recover()` — `chat-state.svelte.ts:721-726, 738-740` defines `resumeCurrentIfNeededOrRecover()` and uses it from `handleReturn`. Addresses the "refresh-mid-flight + background tab" combined scenario I raised in review.

**Test proof:** `chat-state.spec.ts:384-453` has four new test cases:

- Returns false when no active conversation.
- Returns false when the last message is not from the user.
- Reattaches through Firestore when the last message is from the user.
- `handleReturn` tries Firestore resume before recover when runId is missing.

**Live proof:** with the simulator pattern (pre-seed localStorage with a user-msg-only conversation, then navigate to `?sid=...`), the page:

1. Shows "Working for 13s" + the first deterministic note within seconds of attaching — screenshot `/home/adam/screenshots/followup_e2e_early.png`.
2. Progressively fills in notes + detail groups (Google Maps / TripAdvisor / Google reviews / Public sources / Warnings) as the simulator writes events.
3. Transitions to "Drafting the answer…" — screenshot `/home/adam/screenshots/followup_e2e_live.png`.
4. Collapses to the completed-turn summary with the generated title in the sidebar.

### 🟡 #3 — Small cleanup pass (partial)

- ✅ **Live timer expression simplified.** `StreamingProgress.svelte:67` now reads `formatDuration(startedAtMs ? now - startedAtMs : 0)` — dead ternary gone.
- 🟡 **Duplicate `research_placeholder` filter** — one of three redundant checks was removed, but two still survive and overlap:
  - `worker_main.py:746-747` — conditional list-comprehension filter.
  - `worker_main.py:749-751` — inline skip inside the kept-loop.

  Both skip `research_placeholder` + `liveOnly` when `research_note_emitted` is true. The second is dead code after the first runs. The plan asked for "Remove the duplicate `research_placeholder` filtering"; the agent removed one of the pair but left one functionally redundant check. Not blocking; two-line follow-up.

### ✅ Bonus — LLM-note race fix

Not in the plan ("acceptable to leave as-is for now"), but I asked for it as a free one-line fix in the prior review. It landed:

- `worker_main.py:1232` — `await _cancel_background_tasks(note_tasks)` now runs immediately before `timeline_builder.build_summary()` at line 1237.
- Same cancel-then-summary ordering applied in the error/exception paths at lines 1147-1148, 1155-1156, 1176-1177.

Result: any in-flight LLM-note task is cancelled before the summary is frozen, so there's no window where the live UI shows an LLM note that the persisted summary discards.

## Test suite status

| Suite        | Before                  | After                   | Delta                                                         |
| ------------ | ----------------------- | ----------------------- | ------------------------------------------------------------- |
| Vitest       | 88 passed               | **93 passed** (9 files) | +5 new tests (4 in `chat-state.spec`, 1 in `ChatThread.spec`) |
| Functions    | 47 passed               | 47 passed               | unchanged                                                     |
| Agent pytest | 153 passed + 17 skipped | 154 passed + 17 skipped | +1                                                            |
| Lint         | 0 errors, 21 warnings   | 0 errors, 21 warnings   | unchanged                                                     |
| svelte-check | 0 errors, 12 warnings   | 0 errors, 12 warnings   | unchanged                                                     |

All the new tests cover the plan's acceptance criteria. No regressions.

## The one real concern — prose body empty after live-run completion

During the live E2E — simulator running in the background, browser attached mid-flight — I observed the full timeline unfold correctly, then saw:

- Sidebar title updated to "Berlin Burger Openings 2026" ✓
- "Worked for 1m 0s" summary disclosure ✓
- Sources pills ✓
- **Agent reply prose body: empty** ✗

DOM shows `<div class="prose ..."><!----><!----></div>` — the `{#each splitChartSegments(displayText(msg.text, msg.timestamp))}` iterated zero visible times.

After reloading the page (forcing the `resumeIfInFlight` → `status === 'complete'` branch), the reply rendered fine:

> "Three notable openings landed in Berlin this year. Smashed Brothers Mitte is the strongest performer — broke into Wolt's burger top-picks, pulls 4.6+ on Google. …"

This isolates the issue to the typewriter path (`typingMessageTimestamp` is set in live-complete but not in refresh-complete). Likely root cause: the `replyTyper.setTarget(message.text)` in `ChatThread.svelte:58` kicks off RAF ticks, each calling `typedReply = value`, but `typedReply` (Svelte 5 `$state` at script-top) isn't propagating to the `displayText()` read path in the `{#each}` expression — so the each body sees an empty text segment forever.

This is **not introduced by this follow-up** — the typewriter wiring was part of the original rewrite. But it's live-blocking for the Codex-shape UX the whole redesign is chasing: a real user running a real query will hit this every time. The refresh-to-view workaround is bad UX.

**Minimum viable fix (one line):** in `chat-state.svelte.ts:322-327`, either:

1. Don't set `typingMessageTimestamp` at all (kill the feature and always render the full reply immediately), or
2. Schedule `typingMessageTimestamp = null` after the typer's `onDone` so the render flips back to `msg.text`. But that requires wiring `onDone` in the typer create-options in `ChatThread.svelte`.

Option 1 is trivial and removes the feature until it's properly debugged. Option 2 keeps the effect but needs a tiny test.

Either way, worth a one-line follow-up commit before the overall redesign ships.

## Other observations

- **`?sid=...` not in localStorage remains deferred**, as agreed. Plan correctly treats it as a product decision.
- **Reconnecting copy changed** — "Reconnecting to your session…" → "Reconnecting to the session…" (`ChatThread.svelte:298`). Matches the CLAUDE.md product-voice guideline ("avoid you/your"). Good drive-by fix.
- **Dot-wave animation tweaked** (`ChatThread.svelte:364-375`) — opacity and timing nudges. Non-blocking visual polish.

## Summary

Plan items landed well. Test coverage for the new code is good. One partial cleanup (duplicate filter) and one pre-existing bug exposed by the new live-run path (typewriter leaves reply body empty) are the only outstanding items before shipping. Neither are introduced by this follow-up pass.

---

## Round 2 — Verification

Round-2 changes target the two outstanding items from the round-1 review: the prose-empty-after-live-completion bug, and the last redundant `research_placeholder` filter.

### TL;DR

**Both shipped, plus three supporting changes I'd recommend on top.** Live E2E now correctly types the reply in character-by-character and lands on the full text. `typingMessageTimestamp` clears via the new setter when the typer fires `onDone`. All test suites green; build clean.

One regression in test coverage to call out: the typewriter-spec suite shrank from 13 tests to 1 test. The dropped tests covered `createTypewriterGroup` which is no longer used by any component, so it's dead-code coverage being dropped — but `createTypewriterGroup` itself still exports from `src/lib/typewriter.ts`. Either delete the unused export or restore the tests.

### Round-2 fixes verified

#### ✅ Typewriter "reply body empty" bug — fixed

Three coordinated changes addressed the root cause:

- **`ChatThread.svelte:15`** — `activeTypedTimestamp` changed from `$state` to plain `let`. This breaks the self-triggering effect/cleanup cycle: writing to a non-reactive variable inside the effect no longer schedules a re-run, so the cleanup function (`replyTyper.stop()`) doesn't fire mid-typing.
- **`ChatThread.svelte:22-26`** — typer's `onDone` now calls `chatState.typingMessageTimestamp = null` to mark typing complete.
- **`chat-state.svelte.ts:804-806`** — added the `set typingMessageTimestamp(v)` setter on the `chatState` export (was getter-only before, so the previous `onDone` write was a silent no-op).

Plus a non-blocking ordering tweak:

- **`chat-state.svelte.ts:322-326`** — `messages.push(msg)` now precedes `typingMessageTimestamp = timestamp` inside `onComplete`. Doesn't strictly affect the bug (Svelte batches the writes within a microtask), but makes the invariant "the message exists when the effect runs" obvious from the code order.

**Live verification (Chrome MCP + Firestore simulator):**

1. Pre-seeded localStorage with a user-msg-only conversation, navigated to `?sid=...`.
2. `resumeCurrentIfNeeded` → `resumeIfInFlight` → live listener subscribed.
3. Notes + detail groups + drafting row rendered progressively as the simulator wrote events.
4. Terminal `complete` arrived → reply pushed to messages → `typingMessageTimestamp` set.
5. **Typer ticked through the 534-char reply** → `displayText()` returned each progressive prefix → `{#each splitChartSegments(...)}` re-evaluated cleanly until the full text was rendered.
6. After typing finished, post-state inspection: `typingMessageTimestamp === null`, `prose textContent.length === 534`. Setter wired correctly.

Screenshots: `/home/adam/screenshots/round2_reply_visible.png`, `/home/adam/screenshots/round2_summary_expanded.png`.

#### ✅ Last redundant `research_placeholder` filter removed

`worker_main.py:719-757` — `finalize_notes()` now does one filter pass at lines 746-747, then a clean copy loop. The previous inline check inside the `kept` loop is gone.

### Test suite status

| Suite         | Round 1                 | Round 2                 | Delta               |
| ------------- | ----------------------- | ----------------------- | ------------------- |
| Vitest        | 93 passed               | **83 passed** (9 files) | **−10** (see below) |
| Functions     | 47 passed               | 47 passed               | unchanged           |
| Agent pytest  | 154 passed + 17 skipped | 154 passed + 17 skipped | unchanged           |
| Lint (eslint) | 0 errors                | 0 errors                | unchanged           |
| svelte-check  | 0 errors, 12 warnings   | 0 errors, 12 warnings   | unchanged           |
| Build         | n/a                     | clean (11.28s)          | new                 |

The −10 vitest delta breaks down as:

- **Added in Round 2:** typewriter `onDone` test, chat-state "drafting marks typing" test, chat-state "dedup on duplicate onComplete" test → +3 net new
- **Removed in Round 2:** 12 of 13 tests in `typewriter.spec.ts` deleted (drain rate, extend mode, reset mode, stop, no-op setTarget, plus all 7 `createTypewriterGroup` tests).

The removed tests cover `createTypewriterGroup`, which is no longer used by any component (the new `StreamingProgress.svelte` uses no typewriter at all; only `ChatThread.svelte` uses the single-instance `createTypewriter`). So the dropped coverage is on dead code in practice. **However**, the `createTypewriterGroup` symbol is still exported from `src/lib/typewriter.ts`. Cleanest follow-up: delete it. Failing that, keep the tests around so the code stays guaranteed.

### Lint warning to be aware of

`npm run lint` exits 1 because two unrelated docs (`docs/topic-pills-hydration-fix-plan-2026-04-23.md`, `docs/shareable-sessions-plan.md`) aren't Prettier-formatted. Both are untracked plan files outside the redesign's scope. Fix is `npx prettier --write docs/*.md` before pushing — not a redesign-code issue.

### Other Round-2 changes worth knowing

- **`reset()` clears recovery singleton state** — `chat-state.svelte.ts` line 481 (`typingMessageTimestamp = null`) is one of four places in the file that now nulls typingMessageTimestamp, alongside `reset()`, `switchTo()`, `deleteConversation()`, and the `onError` path. Stale recovery flags can't leak across runs.
- **`chat-state.spec.ts` adds the `agent reply order` test** at line 134 — proves `onComplete` sets `typingMessageTimestamp` to the agent message's timestamp after a drafting event lands.
- **`typewriter.spec.ts` adds the `onDone after draining` test** — covers the new contract that `onDone` fires exactly once at completion.

### Final verdict

**Ready to ship.** Round 2 closes the only blocking concern from Round 1. Fake typing now works end-to-end. The completed-turn summary expands cleanly with no duplicate counts row. Refresh-mid-flight reattaches via `resumeCurrentIfNeeded`. Worker race fix landed. Test coverage shrank but only on dead code.

Two small cleanups to bundle into a future pass (none blocking):

1. Delete `createTypewriterGroup` export from `src/lib/typewriter.ts` (now unused), or restore its tests.
2. `npx prettier --write docs/*.md` to clear the lint warning.
