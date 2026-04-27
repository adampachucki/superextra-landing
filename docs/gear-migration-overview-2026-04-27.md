# Agent infrastructure migration — leadership overview

**Date:** 2026-04-27
**Audience:** product, leadership, anyone who needs the shape without the implementation details
**Companion technical plan:** [`gear-migration-implementation-plan-2026-04-26.md`](./gear-migration-implementation-plan-2026-04-26.md)

---

## In two minutes

We're moving the engine that runs Superextra's research agent from infrastructure we built and maintain ourselves onto Google's managed equivalent. The chat experience for users — what they see, type, and read — stays exactly the same. What changes is _who is responsible for keeping the engine running:_ today it's us, after the migration it's Google. We've spent the last week running careful tests against the managed platform to confirm it actually handles our specific workload (long-running, multi-step research that takes 7–15 minutes per question). It does. The migration takes about two weeks of focused build, then about three weeks of safe rollout where the old and new systems run in parallel before we turn off the old one. The headline benefit is removing a class of work we shouldn't be doing — running our own agent runtime — and freeing that engineering capacity for actual product work.

---

## What we have today, and why it's a problem

Superextra's chat agent runs a research pipeline that takes between 2 and 15 minutes per question, depending on how deep the user asked. That's an unusually long-running workload — a typical chatbot replies in 10 to 30 seconds. To make a 15-minute pipeline survive everyday user behaviour (closing the laptop, switching to mobile, network drops, refreshing the tab), we've built a custom system that keeps the work running on the server even when the browser disappears, and shows progress through a separate channel that survives reconnection.

That custom system has been rewritten three times in the last twelve months. Each rewrite was driven by a real failure mode that surfaced in production: the original version dropped work when Safari backgrounded the tab; the second version we shipped in March solved that but introduced its own complexity around dispatching and retrying long jobs; the third version in April reshaped how chats are stored so they can be opened from a different device. Each rewrite was carefully planned, tested, and reviewed — none of them were sloppy work — but the underlying problem is _genuinely hard_, and we keep paying engineering time to maintain machinery that isn't directly part of our product.

The agent code itself — the actual research logic, the specialists, the synthesis — is about 600 lines. The custom infrastructure around it that handles dispatching, retrying, watching for stuck runs, recovering from disconnections is about 3,400 lines. We've spent significantly more code maintaining the _delivery_ of the agent than building the agent.

## What we're moving to

In April 2026, at Google's Cloud Next conference, Google announced that their managed AI agent platform now supports the kinds of workloads we run: long-running, multi-step, with rich progress reporting. Specifically, they shipped support for runs that survive caller disconnection, custom session identifiers, and a pricing model that fits our usage. The platform is called Gemini Enterprise Agent Platform (we shorten it to "GEAR"). It's the natural successor to the Vertex AI Agent Engine product we already use parts of — specifically, we already store chat session history there.

The migration moves the agent's _execution_ onto GEAR. Specifically, when a user asks a question:

- **Before:** their browser sends the question to our Cloud Function, which queues the work, which is picked up by a Cloud Run server we manage, which loads our agent code, runs it for 7–15 minutes, and writes progress to a database the browser is reading from.
- **After:** their browser sends the question to our Cloud Function, which hands the work directly to GEAR. GEAR loads our agent code (same code), runs it for 7–15 minutes, and writes progress to the same database the browser is reading from.

The agent's behaviour, the chat UI, the progress UI, the chat history, the data we store — none of those change for the user.

What disappears is the entire middle layer: the Cloud Run server we maintain, the queue we manage, the retry logic we wrote, the dispatch monitoring we built. Google handles all of that for us as part of running the platform.

## How we got confident this would actually work

Cloud platforms make claims about their products that don't always survive contact with real workloads. Before committing to this migration, we ran three rounds of focused testing against the live GEAR platform.

**Round 1** verified the load-bearing question: does the platform actually keep running our agent if the browser disconnects? We deployed a five-minute test agent, started it, then forcibly killed the calling process. The agent kept running and wrote its terminal state to the database four minutes later. The platform behaves as advertised.

**Round 2** tested the operational details. Does outbound network access work for our third-party integrations (TripAdvisor, Apify, Google Places)? Yes. Do the platform's secret-storage and credential-handling features work for our API keys? Yes, with one caveat (a documented platform feature didn't work as advertised; we found a clean workaround). Does our specific agent shape — the multi-stage research pipeline with parallel specialists — actually run on the platform? Yes.

**Round 3** addressed two specific concerns from our internal reviewer: can we update agent state per-conversation-turn (needed for follow-up questions to work correctly), and can our Cloud Function hand off the work cleanly to GEAR without leaving runaway processes behind? Both work. The first required a small REST API call we hadn't initially planned; the second required a small piece of cleanup code we now have.

Across all three rounds we found four documented platform features that didn't quite match the docs. None of them were dealbreakers. Each had either a verified workaround or doesn't apply to our use case. We kept a careful log of every test, every failure, every retry, every fix — that record is what gives us confidence the migration is grounded in reality, not optimism.

## What changes for users

Nothing visible. A user who chats with the agent today and a user who chats after the migration would not be able to tell which version they're on.

- The chat panel renders the same way and at the same speed.
- Progress messages ("Researching restaurants near you...") appear with the same cadence.
- The final report has the same shape, same charts, same sources.
- Chat history loads the same way; old chats remain accessible.
- Sharing a chat by URL still works.
- Mobile, tab refresh, switching devices — all unchanged.

There's one subtle UX improvement: when a user starts a new chat, the chat panel will now appear immediately rather than after a brief wait while the question is dispatched. This is a side benefit of restructuring how the dispatch flows; it isn't a feature we set out to build.

## What changes under the hood

Less code we maintain. Specifically:

- The Cloud Run service that runs our agent disappears entirely after the rollout window.
- The queue that dispatches work disappears.
- About 700 lines of custom dispatch, retry, and stuck-job-detection logic gets deleted.
- About 250 lines of new code is added to wire up GEAR.
- Net: ~450 fewer lines of operational code to maintain forever.

The chat UI, the chat database structure, the progress display, the watchdog that catches genuinely stuck runs — all stay. Those are real products and real safety nets, not infrastructure plumbing.

We also gain some things we couldn't easily build ourselves: Google handles platform-level monitoring of the agent execution, scales the underlying compute automatically, and stays current with the latest underlying frameworks without us having to manage upgrades.

## The rollout plan in plain English

We don't switch users over all at once. Instead:

1. **Build phase (about two weeks):** code changes, test coverage, deploy infrastructure side-by-side. Nothing user-visible during this phase. The old system continues serving 100% of traffic.
2. **Allowlist soak (about one week):** the new system is deployed and live, but only the developer's own account routes to it. We use it ourselves, watch closely, find issues users wouldn't see. If anything regresses, we remove the developer from the allowlist and we're back to today's system instantly.
3. **Default flip (about one week):** new chats from any user start using GEAR. Existing chats continue on the old system. We watch for any regressions; if something appears, we flip the default back. Sticky-per-chat means no in-flight conversation gets rerouted mid-conversation.
4. **Soak and drain (about one week):** the old system continues running for any chats started before the flip. Most chats are short-lived — within a day or two, very few sessions are still on the old system. The old system scales itself down to zero idle.
5. **Cutover:** with the old system serving zero new traffic for a week, we delete it. The migration is complete.

Total calendar time: about five weeks from start to finish. Most of that is safe parallel running and observation, not active engineering work. The active build is about two weeks; the rest is rollout discipline.

If anything goes wrong at any stage, we can roll back in under a minute by flipping the default back to the old system. The old system stays fully deployed and tested through the entire rollout — it isn't decommissioned until we've had clean traffic on the new system for a full week.

## Risks, honestly

**The platform turns out to have a regression we didn't catch.** We've tested every load-bearing mechanic with timestamps and concrete evidence, but managed platforms can change. Mitigation: parallel rollout with instant rollback. The first sign of trouble, we revert; the cost of reverting is hours of investigation, not lost work or unhappy users.

**A user starts a chat right at the moment we cut over.** They might experience one error in their first reply. Mitigation: the cutover happens after a week of clean 100% traffic on the new system; this scenario requires multiple things going wrong at once. If it happens, the user sees an error and retries; we've designed every code path around the assumption that retries are normal.

**Vendor lock-in deepens.** Today, we could move our agent to any Python host with a couple of days of work. After the migration, we'd need to rebuild the dispatch layer to leave Google. This is a real tradeoff, but the upside (deleting maintenance work we shouldn't be doing in the first place) outweighs it for now. If we ever need to leave Google, we still own the agent code itself — only the deployment harness becomes Google-specific.

**Cost surprises.** The platform charges based on compute time, similar to our current Cloud Run setup. We expect the bill to be roughly the same; not investigated to the dollar yet. If costs come in materially higher, we'd reassess — but the platform is priced like the underlying compute, so a large surprise is unlikely.

## What this migration will _not_ fix

This is not a feature project. It does not:

- Add new chat capabilities for users.
- Make the agent faster (the 7–15 minute response time is the agent doing real research; that doesn't change).
- Improve the quality of the agent's answers.
- Introduce new pricing tiers or user-facing controls.

The reason we're doing it is exactly that it doesn't change the product. The product is fine; the infrastructure under the product was eating engineering time.

## Bottom line

The migration is an infrastructure-only change that removes about 700 lines of code we shouldn't be writing in the first place, while preserving everything users see and rely on. Three rounds of careful testing have confirmed the platform handles our specific workload reliably. The rollout is gradual, reversible at every stage, and finishes within five weeks. The most realistic risk profile is "a small bug surfaces during rollout, we catch it within hours, and either fix it or roll back." The upside is permanent: future engineering time goes to building product features instead of maintaining a custom agent runtime.

For the technical execution detail, see the companion plan at [`gear-migration-implementation-plan-2026-04-26.md`](./gear-migration-implementation-plan-2026-04-26.md).
