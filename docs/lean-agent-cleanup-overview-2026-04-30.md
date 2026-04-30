# What's next for the Superextra agent — a small, focused cleanup

**Date:** 2026-04-30
**Audience:** product, founders, anyone curious about where the agent goes next.
**Companion doc:** the engineering implementation plan lives at `docs/lean-agent-cleanup-plan-2026-04-30.md` for whoever picks the work up.

## The short version

After two big pieces of work this month — the V2.3 source-diversity ship that doubled how broadly the agent reads, and the routing collapse that simplified the pipeline from five steps to two — the next move is deliberately small. Three targeted changes, all chosen so that the codebase ends up **smaller and simpler** when they land. No new pipeline stages, no new agents, no new infrastructure to maintain.

One is a one-line prompt edit. One is a deploy-time config flip that turns on a built-in Google Cloud feature and gives us full agent-internals visibility for free. The third deletes ~180 lines of custom code that exists only because we weren't using a feature ADK provides natively.

Total estimated effort: a few days of engineering time. Visible-to-user change: the agent stops occasionally citing sources it didn't actually read.

## Where we are now

If you've been close to the agent work, skip this section. If not — quick orientation.

The Superextra agent is a Google ADK pipeline running on Vertex AI Agent Engine. When an operator asks a question, a fast routing model decides whether to run a full research pipeline or answer a quick follow-up. The research pipeline is now a single "research lead" agent (Gemini Pro with thinking enabled) that plans the work, dispatches up to nine specialist agents in parallel as tools, and writes the user-facing report. Specialists like `menu_pricing`, `review_analyst`, `marketing_digital`, and `market_landscape` each own a slice of the evidence space.

V2.3 (shipped late April) introduced source-type priors and a self-audit step inside the specialists, doubling source diversity and cutting single-source dominance. The routing collapse a few days later merged the orchestrator and synthesizer into one agent, removing two whole pipeline stages without losing any quality.

So the agent is in good shape — and now in lean shape too. The three changes below extend that direction rather than reversing it.

## The three changes

### 1 · Turn on Cloud Trace

**What changes for users:** nothing visible. This is purely engineering observability.

**Why we want it:** today, when a research run takes longer than expected, our only debug surface is reading Firestore events and log lines after the fact. We can see _that_ a run was slow; we can't easily see _where_ it spent the time, which specialist was waiting on what, or how many tokens each LLM call cost.

ADK emits structured trace data automatically — we just haven't turned the export on. Flipping one environment variable at deploy time gives us Cloud Trace's full waterfall view: every agent invocation, every tool call, every Gemini call, with timing and token usage attached. AgentTool nesting shows up correctly, so we can see the lead's calls _and_ the specialists' internal calls in the same view.

This is the cleanest answer to a longstanding question — "did the agent's iterative behaviour actually happen on this run?" — without writing custom instrumentation. Cost is well inside Cloud Trace's free tier at our volume.

**Effort:** half a day, mostly verification of the right environment variable name against the ADK version we have pinned.

### 2 · Delete custom code we don't need anymore

**What changes for users:** nothing visible — same progress pills, same UX.

**Why we want it:** the file that turns ADK's events into the user-facing progress pills (the "Searching the web", "Google Maps", "TripAdvisor" rows the operator sees while a run is in flight) is currently 438 lines, of which roughly 180 lines exist solely to _reverse-engineer_ ADK's event objects to figure out what kind of thing just happened.

ADK provides a typed plugin API that hands us the same information directly with structured arguments. Subscribing to that API lets us delete the reverse-engineering layer entirely. The file's purpose stays the same; it just sources its information from the right place.

This is the kind of cleanup where the codebase ends up clearly better and noticeably smaller. The risk is contained — same pill output, same UI rendering, same tests — and we control the rollback (one revert).

**Effort:** roughly two days, including writing the new tests and validating against a few production runs after deploy.

### 3 · One prompt rule to stop fabricated citations

**What changes for users:** the agent stops citing sources it didn't actually read.

**Why we want it:** in the V2.3 retrospective, the smoking gun was a Gdynia restaurant query where the agent's report name-checked two real-estate sites — Domiporta and Gratka — that it had never actually fetched. The model had recognized the names from training data and woven them in as if they were sources. This is rare but real, and it's the single failure mode that most undermines the product's "we cross-checked breadth of sources" promise.

The instinct was a structural fix: replace our custom web-fetcher with Google's built-in URL grounding feature, which would force the model to ground its citations in actually-retrieved content. We took that idea seriously and looked at the docs. The Gemini 3 documentation says the combination with custom function tools is supported model-side, so on the model layer the answer is probably "it works for us." But the Vertex AI Agent Engine documentation doesn't address the question at all, and ADK has known limitations around how it wires built-in tools alongside the multi-agent setup we use. So the practical question — does this actually work end-to-end for our specific setup of nine specialist agents, custom narration tool, and Places tools — is unproven. Verifying it is a behavioural spike, not a one-line config change. That's a separate piece of work with its own design decisions, not something to fold into a lean cleanup.

The lean fix is one rule, added to the specialist instructions: _"Cite only sources you actually fetched via tools. If a source isn't in your tool results, do not cite it — even if you can recall the URL or domain from training data."_ This addresses the cause directly. It's the kind of rule that's both surprisingly effective on modern models and trivially reversible if it underperforms.

We did not build a separate verification agent that re-reads the report and checks each citation. That was the alternative: bigger, slower, more code, and treats the symptom rather than the cause. Worth revisiting later if the prompt rule isn't enough, but not as a first move.

**Effort:** a few hours, mostly validation against existing test queries.

## What we're explicitly not doing

A short list, because the negative space matters and most of these came up as serious options:

- **No claim-verification agent.** Symptom treatment. Change #3 fixes the root cause.
- **No intent-shaped prompting for "give me one decision" questions.** This came up as a candidate change ("operator asks for the ONE thing, agent gives them five"). It was framed in the V2.3 retrospective as a _risk to watch_, not a confirmed problem — and we don't have production evidence operators are unhappy with the current behaviour on decision-shaped questions. Adding conditional output-shape logic to the prompt now would be design-for-hypothetical-future. Revisit if Cloud Trace data (post-change #1) plus production observation surfaces a real complaint.
- **No replacement of our web-fetcher with Google's URL grounding.** Gemini 3 supports the combination model-side, but Vertex Agent Engine and ADK behavior for our specific multi-agent setup is unproven; verifying it is its own spike, not a lean cleanup item.
- **No follow-up-turn evaluation harness.** Still on the V2.3 open list, but no production failure since the routing collapse justifies it. Revisit if Cloud Trace data (post-change #1) reveals a real follow-up regression.
- **No cross-market source priors variant.** Same logic — no felt need yet.

Each of these is a real option worth doing eventually. None of them belong in this small cleanup.

## Risk and verification

All three changes are reversible. Two of them (#2 and #3) by reverting a single commit; #1 by removing one environment variable from the deploy.

The verification path mirrors the change shape:

- For #1, after the deploy, open Cloud Trace and confirm a research turn shows the expected nested span structure. No user-visible regression possible (this is purely additive observability).
- For #2, run a research turn and confirm the progress pills still appear with the same shape. Existing tests cover the mapper; we add new tests for the typed-hook plugin code.
- For #3, replay a Tricity query, spot-check three random cited URLs against the actually-fetched URL set in the run state. Every cited URL should appear in the fetched set.

## Timing

Realistic ordering for a single-engineer week:

- **Day 1:** changes #3 and #1 ship together in one Agent Engine redeploy. The prompt rule (#3) is baked into the cloudpickled runtime at deploy time, so it needs a redeploy to take effect; the tracing env var (#1) needs the same redeploy. Bundling them saves a deploy cycle and they touch independent surfaces. Low risk; both are individually revertable.
- **Days 2-3:** change #2 — plugin hook refactor. New tests, separate deploy, watch the first few production runs. Cloud Trace data from #1 is available to verify the migration didn't break tool-call observation.
- **Days 4-5:** breathing room and validation.

Total: about a week of engineering, ending with a smaller, simpler codebase that's also better instrumented and produces more disciplined output. The kind of week that compounds.
