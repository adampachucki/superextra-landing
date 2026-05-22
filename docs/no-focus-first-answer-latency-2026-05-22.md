# No-Focus First Answer Latency

Date: 2026-05-22

## Context

We tested three first-turn prompt shapes against the local app on port 5199 using the real `agentStream` and deployed Agent Engine path:

- Selected venue: Joe's Pizza, 7 Carmine St, New York.
- No selected focus, location in prompt: Williamsburg, Brooklyn market shifts.
- No selected focus and no location: "How am I doing compared to competitors?"

The first two produced full reports. The no-focus/no-location case correctly clarified with:

> What restaurant or area are you interested in?

## Measured Timing

The smoke harness observed the clarification at about 10 seconds because it polled the page every 10 seconds. Firestore timestamps show the backend completed sooner:

- Session queued: `2026-05-22T08:46:34.587Z`
- Agent Engine run-start event: `2026-05-22T08:46:38.240Z`
- Turn complete: `2026-05-22T08:46:41.076Z`

Backend elapsed time was about 6.49 seconds.

Approximate split:

- Agent Stream transaction to Agent Engine run-start: about 3.65 seconds.
- Router, plugin finalize, and terminal Firestore write: about 2.91 seconds.

The direct router prompt through Vertex `generateContent` was faster in a quick shell test:

- `gemini-2.5-flash`: about 0.6-1.2 seconds.
- `gemini-2.5-flash-lite`: about 0.7-1.4 seconds.

Follow-up direct Vertex probes from the VM, using structured JSON output and `thinkingBudget: 0`, were stronger:

- `gemini-2.5-flash` on the exact vague prompt: 0.59-1.46 seconds wall time across 5 runs, 0 thought tokens.
- `gemini-2.5-flash` on six boundary cases: 0.41-1.36 seconds wall time, 0 thought tokens, all expected decisions.
- `gemini-2.5-flash-lite` was similarly fast but misrouted "What are chef salaries?" as research in the small probe, so do not choose Lite without a broader eval.

This suggests most latency is not the wording of the clarification. It is the full Agent Engine handoff, session creation, stream startup, ADK run, plugin lifecycle, and Firestore terminal write.

## Production Failure Case

Session `d7e7deba-d2a1-4220-b5b4-ec8474b933e0` showed the failure mode this fix must cover.

- User message: "What has opened or closed in my area recently?"
- Stored `placeContext`: `null`
- Backend turn elapsed: 31,397 ms
- Router model response: 1.45 seconds, then `transfer_to_agent` -> `research_pipeline`
- Pipeline then ran `context_enricher`, `research_lead`, and `report_writer`
- Final reply was a polished non-answer asking for location context

That means the bad experience was not only slow clarification. The production router misclassified a no-place, self-referential first turn as research-ready. Once that happened, `SequentialAgent` ran the configured pipeline in order. The context enricher recognized that location was missing, but there is no current pipeline halt between the context packet and the writer, so research lead and report writer still spent model time turning the missing-context state into a report.

This is also why visible thought summaries looked strange. `include_thoughts=True` intentionally surfaces compact Gemini thought summaries for the research pipeline, but in this case the pipeline should never have started.

## Current Architecture Cost

Today every first-turn prompt follows the same path:

1. Browser posts to `agentStream`.
2. Cloud Function writes a queued session and turn.
3. Cloud Function creates or resumes the Agent Engine session.
4. Cloud Function appends state for `runId` and `turnIdx`.
5. Cloud Function calls `streamQuery` and waits for the first stream line.
6. Agent Engine runs the router.
7. Router either transfers to research or returns a clarification.
8. Firestore plugin writes the terminal turn.
9. Browser sees the completed turn through Firestore listeners.

That path is appropriate for real research. It is expensive for a simple clarification.

## Non-Goals

Do not add deterministic logic that says "no selected venue/location means clarify." That would be wrong for the future account model, where the user may have a saved venue and location even when no focus is selected in the composer.

Do not move vague-prompt handling into the client as a hard UI rule. The server must remain the authority because it will eventually combine prompt text, selected focus, account venue, saved area, and prior session context.

## Recommended Fix

Add a small server-side pre-router before Agent Engine handoff, but gate it narrowly.

The pre-router should be an LLM decision, not a deterministic venue-missing rule. It should run in `agentStream` before creating or invoking the Agent Engine session only when the first turn is ambiguous enough that a clarification is plausible.

Do not add an unconditional pre-router tax to every first turn. If a selected focus exists, or future account context provides a saved venue or saved market, route directly to Agent Engine. Those cases are already research-ready.

Run the pre-router when all of these are true:

- this is the first Firestore turn for the chat;
- no selected focus was submitted;
- no saved account venue, saved area, or equivalent durable context is available.

Input:

- raw user message;
- selected focus, if any;
- first-turn versus follow-up;
- future account context: saved venue, saved location, known competitors;
- possibly a compact prior-session flag when relevant.

Output should be a small structured decision:

- `research`: create or resume Agent Engine and continue with the current path.
- `clarify`: write a completed Firestore turn directly, with one short clarification question.

Do not implement `blocked` in the first pass. There is no observed unsupported-request failure that needs that branch yet.

The pre-router must be stricter than the current ADK router. In particular, these are not usable geography by themselves:

- "my area"
- "near me"
- "near us"
- "nearby"
- "local"
- "my competitors"
- "our competitors"

Requests about openings, closures, local momentum, wages, rent, regulation, saturation, nearby competitors, delivery competition, or venue-specific pricing should clarify unless a usable venue, address, area, market, city, neighborhood, or country is present. Broad industry questions can still route to research when they are genuinely answerable without local geography.

Direct Vertex probes with a stricter clarification-gate prompt and `gemini-2.5-flash` / `thinkingBudget: 0` classified the production prompt correctly:

- "What has opened or closed in my area recently?" -> `clarify`, about 1.0 second
- "What has opened or closed in Williamsburg recently?" -> `research`, about 0.75 seconds
- "What format shifts are happening in fast casual dining?" -> `research`, about 1.1 seconds
- "How saturated is the ramen market?" -> `clarify`, about 0.66 seconds
- "How saturated is the ramen market in Brooklyn?" -> `research`, about 0.25 seconds
- "What are chef salaries?" -> `clarify`, about 1.1 seconds
- "What are restaurants in Denver paying chefs?" -> `research`, about 0.92 seconds
- "Which restaurants near us are quietly losing momentum?" -> `clarify`, about 1.3 seconds

Expected latency improvement:

- Clarification can avoid Agent Engine session creation, `appendEvent`, `streamQuery`, ADK router startup, and plugin finalization.
- The remaining path is Firebase auth, Cloud Function, one fast LLM call, and Firestore writes.
- Based on direct Vertex calls, the LLM part should be around 1 second in a warm path. End-to-end target should be materially below the current 6.5 second backend path.

## Turn 2 After Clarification

A directly clarified first turn creates a Firestore chat, but it does not create an Agent Engine session. The next user reply must therefore be treated as the first Engine handoff even though it is Firestore turn 2.

Required state:

- `engineSessionStarted: false` on sessions that were clarified directly.
- `awaitingClarificationAnswer: true` on sessions waiting for the user to answer a direct clarification.
- `engineSessionStarted: true` after Agent Engine accepts the first real research handoff.
- `awaitingClarificationAnswer: false` after Agent Engine accepts the first real research handoff.

When the user answers the clarification, for example:

1. User: "How am I doing compared to competitors?"
2. Superextra: "What restaurant or area are you interested in?"
3. User: "Joe's Pizza, 7 Carmine St."

`agentStream` should create the Agent Engine session on turn 2 and send a synthesized first Engine message that preserves the original intent:

```text
[Date: May 22, 2026]
[Context: The user is answering a clarification. Original question: "How am I doing compared to competitors?" Clarified focus: "Joe's Pizza, 7 Carmine St."]
Answer the original question using the clarified focus.
```

Do not hand the Engine only `"Joe's Pizza, 7 Carmine St."`; that loses the business question. The prior Firestore turn already contains the original `userMessage`, so the implementation can read the previous direct-clarification turn instead of duplicating that text onto the session doc.

Rename the handoff concept in code from `isFirstMessage` to something like `isEngineFirstMessage`. Firestore turn 2 can be Engine turn 1.

After `gearHandoff` succeeds, update the session to `engineSessionStarted: true`. If the function crashes after Agent Engine accepted the session but before that flag is written, the existing `ALREADY_EXISTS` handling in `gearHandoff` keeps the next attempt idempotent.

The current active chat follow-up composer accepts text only; the immediate path is for the user to type the restaurant, address, neighborhood, or market. A future follow-up focus picker can reuse the same server behavior by sending `placeContext` on the follow-up.

This does not eliminate the Agent Engine cold path for the eventual research answer. It removes that cost from the clarification answer. If the user then provides a place, the first real research run still pays session creation, `appendEvent`, `streamQuery`, ADK startup, and any Agent Engine cold start. That is acceptable because research is the expensive path and can show live progress; it is not acceptable for a one-line clarification.

## Required Design Guardrails

1. Keep the production router as the source of truth for full research.

   The pre-router should only decide whether an ambiguous first turn needs clarification before expensive research infrastructure starts. It should not plan research, choose specialists, or answer substantive questions.

2. Store whether an Agent Engine session exists.

   A directly clarified first turn creates a Firestore chat but no Agent Engine session. A later user answer creates the Agent Engine session on turn 2. The data model needs an explicit flag such as `engineSessionStarted`.

3. Preserve future account context.

   When onboarding exists, the pre-router must receive saved venue and location context. A prompt like "How am I doing compared to competitors?" should become research-ready when account context is available.

4. Keep clarification turns normal in the UI.

   The direct-write turn should use the same `turns/0001` shape as Agent Engine output:
   - `status: complete`
   - `reply`
   - `sources: []`
   - `completedAt`
   - no activity events required
   - `turnSummary` can be omitted initially

5. Avoid dual-router drift.

   The pre-router prompt should be short and explicitly scoped. Add tests for the important boundaries:
   - selected focus routes to research;
   - area in prompt routes to research;
   - saved account venue routes to research;
   - "my competitors" without any context clarifies;
   - "my area", "near me", "near us", and "nearby" without context clarify;
   - local openings/closures without context clarify;
   - local wages, rent, regulation, saturation, delivery competition, and nearby momentum without context clarify;
   - broad industry questions that do not need geography route to research.

6. Do not hide the research cold path.

   This change solves clarification latency. It does not solve first research-run latency. Track those separately so the improvement is not misread as an Agent Engine warmup fix.

7. Tighten the in-engine router as a backstop.

   The normal browser path should be protected by the pre-router, but the ADK router should still learn the same boundary. Add the production prompt to router evals as a no-context clarification case, and update router wording so self-referential geography terms are explicitly not usable context.

   Do not add a second heavy halt mechanism inside the sequential research pipeline in the first pass. A pipeline-level halt would require changing agent orchestration for a case the server gate can prevent before Agent Engine starts. If the pre-router and tightened router still allow no-context pipeline runs in logs, then revisit a small pipeline guard with observed failures in hand.

## Implemented Result

The implemented change follows the recommended narrow pre-router approach:

- `agentStream` now runs a Gemini clarification gate only for the first Engine turn when no selected focus is present.
- Direct clarifications write the normal Firestore turn shape and do not create an Agent Engine session.
- Sessions now track `engineSessionStarted` and `awaitingClarificationAnswer` so a follow-up after direct clarification can be Firestore turn 2 but Engine turn 1, without confusing an ordinary marker-write recovery with a clarification answer.
- When the user answers a clarification, `agentStream` sends the Engine a synthesized first message containing both the original question and the clarified focus.
- The Agent Engine router wording and router evals now include the same self-referential geography boundary as a backstop.

Final live direct Vertex probes from the VM against the clarification-gate prompt passed the scenario matrix:

- "What has opened or closed in my area recently?" -> `clarify`, 1,002 ms
- "What has opened or closed in Williamsburg recently?" -> `research`, 436 ms
- "What format shifts are happening in fast casual dining?" -> `research`, 528 ms
- "How saturated is the ramen market?" -> `clarify`, 730 ms
- "How saturated is the ramen market in Brooklyn?" -> `research`, 698 ms
- "What are chef salaries?" -> `clarify`, 636 ms
- "What are restaurants in Denver paying chefs?" -> `research`, 596 ms
- "Which restaurants near us are quietly losing momentum?" -> `clarify`, 931 ms
- Clarification answer after the production-failure prompt, latest "Williamsburg, Brooklyn" -> `research`, 484 ms
- Bad clarification answer after the production-failure prompt, latest "near me" -> `clarify`, 1,052 ms

Average gate latency across those ten probes was 709 ms, with a 1,052 ms max. That is the model-call portion only; end-to-end app latency also includes auth, Cloud Function execution, and Firestore writes. It is still materially below the observed 6.49 second backend clarification path through Agent Engine, and it prevents the 31.4 second misrouted research-pipeline failure from starting.
