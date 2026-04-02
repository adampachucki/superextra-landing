# Agent Architecture Review

Analysis of the Superextra agent system against current best practices for production multi-agent systems. Written April 2026.

---

## What's genuinely well-built

Before getting to gaps, it's worth naming what's architecturally strong — not to be diplomatic but because it informs where the real risks actually are.

**The anti-sycophancy architecture is unusually sophisticated.** Most agent systems never solve the confirmation bias problem at all. Ours has three structural checkpoints that make objectivity a mandatory output rather than an optional behavior: the Planner's assumption audit with SUPPORTED/QUESTIONABLE/CONTRADICTED/UNTESTED verdicts, the specialist "Brief alignment statement" that every specialist must append, and the Synthesizer instruction that requires cross-checking both upstream layers and explicitly leading with corrections when anything is contradicted. The AUTHORING.md articulates why this exists: "LLMs agree with the user's framing unless explicitly told not to. Permission alone is not enough — you need structural forcing functions." The implementation reflects that lesson.

**The context engineering is largely right.** Places data is injected dynamically into each specialist at invocation time via instruction providers, not dumped into a shared conversation thread. The Synthesizer gets all specialist outputs as named template variables — it reads structured slots, not a long conversation thread. The `[Date: ...]` prefix pattern is a clean solution to the staleness problem that propagates cleanly through the pipeline. The "agents can't see each other" architecture is correctly accounted for in the brief-writing instructions.

**The AUTHORING.md is real institutional knowledge.** The rules aren't obvious — "Agents take the path of least resistance", "LLMs default to summarizing", "Agents are sycophantic by default" — and each one cites a real failure. The instructions were written in response to observed behavior, not guesses about what might go wrong.

---

## The biggest gap: no behavioral evaluation

The tests cover template string injection, the `_append_sources` callback, and Places API tool functions. What they don't cover: **does the system actually behave correctly?**

The Router is the most critical agent in the pipeline — every conversation routes through it, and a wrong routing decision corrupts the entire turn. Six routing rules, real edge cases. What happens if a user says "sure, let's do it" but there's no prior plan in the conversation? What if a follow-up question arrives right after a long scoper plan that looks like a report — does the Router misidentify it as completed research? None of this is tested.

The most actionable recommendation from the literature is **single-step trajectory evals for routing decisions**. These are the easiest evals to write, they run fast, and they catch the most common failure mode. A routing eval doesn't require running the full pipeline — given a specific conversation history, does the Router call `transfer_to_agent(agent_name="research_scoper")` or the wrong one? ADK has a built-in eval system (`.test.json` files + `adk eval`) that scores both tool call trajectory and final response. It's already in the toolchain and unused.

Beyond routing, there's no way to know whether the Planner calls the right specialists for a given question, whether brief quality degrades as instructions evolve, or whether the Synthesizer is actually preserving depth. AUTHORING rule 3 documents that the Synthesizer once compressed 91% of content — how would we know if it started doing that again? These don't all need to be automated immediately, but there should be a process of manually reviewing real traces and building an error taxonomy, which then feeds into what automated evals to write. Without this, instruction changes are pure hope.

**Priority actions:**
1. Start reviewing real traces manually — even 10–15 traces would surface a failure taxonomy. This is the foundation that makes all other improvements targeted instead of speculative.
2. Write routing evals first. Six rules with real edge cases, most critical decision in the pipeline, easiest place to write deterministic tests.

---

## Instruction duplication and maintenance risk

The specialist menu, domain boundary rules, and brief-quality principles are duplicated across three files: `research_planner.md`, `research_executor.md`, and `research_scoper.md`. The AUTHORING.md checklist acknowledges this — adding a specialist requires updating all three files.

This isn't just a maintenance inconvenience. The three files will drift. Right now both the planner and executor have the same specialist descriptions, the same domain boundary rules for rent/delivery/reviews, and the same brief quality examples. When you update domain boundaries in the planner, you have to remember to update the executor. When it diverges, the Scoper presents one specialist menu to the user and the Executor expands the confirmed plan with a different set of capabilities.

The natural fix: a single shared specialist registry injected via the same `_make_instruction` pattern already used for `{places_context}`. A `{specialist_menu}` variable and a `{domain_boundaries}` variable resolved from a single source would mean one file to update when the specialist roster changes.

---

## The two-turn flow and its asymmetry

The first-message flow is: Scoper (no tools, no Places data) → user confirms → Executor (reads plan, dispatches specialists). Good UX — the user sees a readable plan and can modify it before anything expensive happens.

But it creates a meaningful quality asymmetry:

**For follow-ups**, the Planner has `google_search` and does reconnaissance before writing briefs. It tests premises, checks whether data exists before assigning specialists, and discovers non-obvious angles. This is the richer path.

**For first messages**, the Scoper has no tools and no Places data. It can flag questionable assumptions, but it's working entirely from the user's words and priors — it can't check whether an area is actually oversaturated before writing that into the plan. The Executor then expands this plan into detailed briefs and has Places data, but it's explicitly not supposed to re-plan: "Do not add specialists beyond what the approved plan specifies." By the time it does the premise assessment (step 5 of its process), the specialists have already been dispatched with briefs that may have been framed around an unchecked assumption.

First-message research is likely more susceptible to assumption contamination than follow-up research because the reconnaissance that tests premises only happens in the Planner path.

**Worth considering:** giving the Executor a lightweight reconnaissance budget before dispatching — specifically to test premises in the approved plan. The tradeoff is latency (another model call before specialists run), but it would close the quality gap between the two paths.

---

## Context size: everyone gets everything

Every specialist receives the full `places_context` regardless of whether they need it. When 7 specialists run in parallel, each with 10 competitor profiles in their context, that's 70 instances of the same data. More importantly, some specialists don't benefit from competitor data. The `operations` specialist researching salary benchmarks doesn't need competitor hours and reviews. The `revenue_sales` specialist estimating check sizes doesn't need competitor addresses.

Injecting irrelevant data into specialist context is one of the four failure modes named in Anthropic's context engineering guide — "Context Confusion: superfluous info degrades output quality."

The Enricher already decides whether to fetch competitors. It could write two separate state keys — `target_context` and `competitor_context` — and specialist instructions could request only what they need. Specialists like `market_landscape`, `menu_pricing`, and `guest_intelligence` genuinely benefit from competitor data; `operations` and `revenue_sales` mostly don't.

---

## Structured outputs: specialists return free-form markdown

Each specialist writes findings as free-form markdown to its `output_key`. This works but provides no programmatic quality signal at the pipeline level.

Consider the "Brief alignment statement" — every specialist is supposed to end with it. If a specialist omits it or writes a malformed one, the Synthesizer has to find it by parsing text. If we wanted to automatically flag when a specialist's findings CONTRADICT the brief's framing, we'd need text matching on "CONTRADICT" somewhere in the response.

ADK supports `output_schema` on `LlmAgent` — a Pydantic model that structures agent output. A lightweight schema requiring `findings` (the research), `brief_alignment_verdict` (one of four values), and `brief_alignment_reason` (one sentence) would enable validation, programmatic checking for CONTRADICTED verdicts, and cleaner injection into the synthesizer.

This is a larger change and should come after evals are in place so we can verify the schema doesn't degrade output quality.

---

## Places API: no caching

`get_restaurant_details` is called fresh every turn. If the same restaurant is researched twice in a session — first for a market question, then a follow-up about operations — the Enricher calls Places API twice for the same place.

ADK's `before_tool_callback` + `after_tool_callback` pattern handles this cleanly: a dict keyed by `place_id` in session state, checked before making the call, populated after. The Places data doesn't change minute-to-minute so any within-session cache eliminates redundant calls. A longer-lived cache with a TTL of a day or two would reduce API costs meaningfully as usage grows.

---

## Summary: priority order

**Highest impact — do these first:**
1. Review real traces manually. 10–15 traces will surface a failure taxonomy that makes all other improvements targeted. No substitute for this.
2. Write routing evals. Fast to write, fast to run, cover the most critical decision in the pipeline.

**Medium impact:**
3. Close the first-message / follow-up quality asymmetry — consider giving the Executor a reconnaissance budget before dispatching specialists.
4. Create a single source of truth for the specialist registry — eliminate the three-file duplication.

**Worth planning for:**
5. Differentiate `target_context` from `competitor_context` in state; give specialists only what they need.
6. Explore `output_schema` on specialist agents once evals are in place.
7. Implement Places API caching via `before_tool_callback`.

---

## Reference materials

- [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Anthropic Engineering — How We Built Our Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Anthropic Engineering — Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Google ADK — Multi-Agent Systems](https://google.github.io/adk-docs/agents/multi-agents/)
- [Google ADK — Sessions, State, Memory & Artifacts](https://google.github.io/adk-docs/sessions/)
- [Google ADK — Callbacks: Design Patterns](https://google.github.io/adk-docs/callbacks/design-patterns-and-best-practices/)
- [Google ADK — Evaluation](https://google.github.io/adk-docs/evaluate/)
- [OpenAI — A Practical Guide to Building Agents](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)
- [Hamel Husain — Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/)
- [LangChain — Evaluating Deep Agents](https://blog.langchain.com/evaluating-deep-agents-our-learnings/)
- [AWS — From Agent Prototype to Product](https://aws.amazon.com/blogs/devops/from-ai-agent-prototype-to-product-lessons-from-building-aws-devops-agent/)
- [Chip Huyen — Agents](https://huyenchip.com/2025/01/07/agents.html)
