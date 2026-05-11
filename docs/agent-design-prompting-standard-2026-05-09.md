# Agent Design and Prompting Standard for Superextra

Date: 2026-05-09  
Purpose: independent external-research baseline for later review of current agent prompts.

## Scope and Method

This report defines a standard for designing and prompting agents for Superextra. It is intentionally not a justification of the current setup. No current agent prompt or instruction files were opened for this task. Internal context was limited to product-facing UI and project guidance sufficient to understand that Superextra provides restaurant market intelligence, competitor benchmarking, hyper-local context, multi-source data, AI research, chat/report output, citations, and human expert support.[^internal-product]

The research basis is external-first. The strongest evidence comes from current official Google ADK, Gemini API, and Gemini Enterprise Agent Platform documentation. Those sources define the stack's actual primitives: LLM agents, workflow agents, multi-agent composition, tools, sessions, state, memory, callbacks, grounding, safety, evaluation, managed runtime, Sessions, and Memory Bank.[^adk-llm][^adk-workflow][^adk-multi][^adk-tools][^adk-sessions][^adk-state][^adk-memory][^adk-callbacks][^adk-grounding][^adk-safety][^adk-eval][^adk-eval-criteria][^agent-platform] Gemini API documentation supplies prompt-design, function-calling, Google Search grounding, and structured-output guidance.[^gemini-prompt][^gemini-function][^gemini-search][^gemini-structured] Serious engineering writeups and research papers are used where they add portable design evidence, especially for agent workflow simplicity, retrieval, tool-use loops, long-context failure modes, and evaluation limits.[^anthropic-agents][^react][^self-rag][^crag][^lost-middle][^prompt-report][^llm-judge]

Where sources are vendor-specific, this report treats them as strong evidence for the Google-based stack but not as universal proof that a design will perform well in Superextra. Product quality must still be measured with Superextra-specific evals and production traces.

## Product Quality Bar

Superextra's agent output is not casual chat. It supports business decisions by restaurant operators, chains, investors, suppliers, agencies, and platforms. The UI promises local market context, competitor benchmarking, pricing, reviews, demand, expansion, financial planning, labor, marketing, and source-backed analysis.[^internal-product] That means the agent standard is:

- Answers must be decision-grade: clear enough to support pricing, expansion, marketing, staffing, diligence, or competitive response.
- Claims must be evidence-linked. If a claim affects a recommendation, it needs a source, a calculation trace, or an explicit "inference" label.
- The agent must distinguish facts, estimates, comparisons, and recommendations.
- Sparse or conflicting evidence must be surfaced, not hidden.
- Locality, time period, venue identity, and comparison set are first-class context, not optional decoration.
- The final answer must be useful at the user's decision level: not a raw source dump, not a generic strategy essay, and not a dashboard description.

## Core Standard

The agent system should be designed as a product subsystem, not as a collection of long prompts. Prompts define behavioral contracts; code, tools, schemas, state, memory, callbacks, and evals enforce the rest. ADK explicitly separates LLM agents, deterministic workflow agents, tools, callbacks, session/state/memory services, and evaluation, which is the right design vocabulary for this product.[^adk-llm][^adk-workflow][^adk-tools][^adk-callbacks][^adk-sessions][^adk-eval]

Good design starts with the task boundary:

- Use LLM agents where interpretation, synthesis, and judgment are needed.
- Use workflow agents or ordinary code where the process order is known.
- Use tools for external data, calculations, source retrieval, normalization, and actions.
- Use callbacks/plugins for logging, policy checks, caching, output validation, and intervention.
- Use evals for claims about quality. Do not encode every observed failure as more prose in a prompt.

This aligns with both ADK's split between nondeterministic LLM agents and deterministic workflow agents, and Anthropic's practical guidance to favor the simplest agentic pattern that works before adding orchestration complexity.[^adk-llm][^adk-workflow][^anthropic-agents]

## Architecture Principles

### 1. Prefer a small number of clear agent roles

A scalable system should not create one prompt per use case. It should define a small set of durable roles with clean interfaces. For Superextra, the durable roles are likely:

- A context interpreter that extracts venue, geography, timeframe, decision type, metrics, and missing constraints.
- Research specialists organized by data modality or source family, not by every possible user question.
- A synthesis agent that combines evidence, compares options, states uncertainty, and writes the user-facing answer.
- Optional human expert handoff for high-impact, ambiguous, or evidence-poor cases.

ADK's multi-agent guidance supports this direction: multi-agent systems improve modularity, specialization, reusability, maintainability, and structured control flows when the application becomes too complex for a monolithic agent.[^adk-multi] Agent descriptions should be specific enough for routing, because ADK uses agent descriptions as part of LLM-driven delegation.[^adk-llm]

### 2. Use deterministic workflow for predictable control flow

Restaurant intelligence has a recurring shape even when the user question varies:

1. Interpret the decision context.
2. Identify required evidence.
3. Retrieve or compute evidence.
4. Check evidence quality.
5. Synthesize an answer with citations and caveats.

That outer shape should be workflow or product logic where possible. ADK workflow agents exist specifically to control sub-agent execution in predictable sequences, parallel branches, or bounded loops without asking an LLM to decide the orchestration itself.[^adk-workflow] Use an LLM for ambiguous interpretation and synthesis, not for basic control flow that code can own.

### 3. Tool-use loops must be bounded and observable

External research loops are appropriate for this product, but they need explicit stop conditions. ReAct-style systems show the value of interleaving reasoning and external actions, and modern RAG work shows that agents benefit from retrieving, evaluating, and correcting evidence rather than answering from static model knowledge.[^react][^self-rag][^crag] The practical standard is not "let the model research until satisfied"; it is:

- Define a source plan.
- Run independent retrievals in parallel when possible.
- Evaluate whether evidence is sufficient, stale, contradictory, or missing.
- Retry or broaden search only under a bounded budget.
- Stop with a clear no-data or low-confidence answer when the evidence does not support the requested conclusion.

Loop agents should have explicit termination conditions. Reflection or critique loops should be triggered by evidence gaps or failed checks, not by generic instructions to "think harder."[^adk-workflow][^adk-eval]

### 4. Build citation and verification into data flow

The agent should not be trusted to invent citation mapping from prose. Gemini Google Search grounding returns structured grounding metadata: search queries, grounding chunks, and support spans that connect text segments to sources.[^gemini-search] Custom tools should return equivalent structured source metadata: title, URL, provider, retrieved date, observed date if known, entity identity, metric, units, and confidence or error state. The synthesizer can then cite from structured evidence rather than fabricate source labels.

### 5. Treat every external source as untrusted input

Prompt injection risk does not come only from users; it can also arrive through web pages, reviews, listings, scraped menus, or any retrieved text. ADK's safety guidance names vague instructions, hallucination, jailbreaks, user prompt injection, and indirect prompt injection through tools as sources of risk.[^adk-safety] The agent must treat source text as data, not instructions. Tool outputs should be sanitized, source excerpts should be quoted or summarized under strict limits, and tools should enforce policy in code.

## Prompt Engineering Standard

### Prompt content

Each agent prompt should be short enough to inspect and stable enough to test. A good prompt contains only the behavioral contract that must be interpreted by the model:

- Role and scope: what the agent is responsible for and what it must not do.
- Inputs: what context fields it receives and what each field means.
- Operating principles: source-backed, local, time-aware, uncertainty-aware, concise.
- Tool policy: when and why to use each tool class.
- Verification policy: what must be checked before final output.
- Output contract: structure, tone, required fields, citation behavior, and failure format.
- Escalation behavior: when to ask for clarification, return insufficient evidence, or hand off.

ADK's LLM-agent documentation describes instructions as the place for core task, persona, constraints, tool-use guidance, and output format.[^adk-llm] Gemini prompt-design guidance similarly emphasizes clear, specific instructions, constraints, context, response format, examples, and iterative refinement.[^gemini-prompt]

### Keep prompts lean

Prompts should not contain large data catalogs, long policy manuals, repeated use-case recipes, source lists that belong in configuration, or JSON schemas that can be enforced by structured output. Long-context research shows that models can fail to use relevant information buried in the middle of long contexts, so dumping everything into a prompt is not a robust design pattern.[^lost-middle] Gemini documentation also recommends structured output for complex JSON rather than relying only on prose format instructions.[^gemini-structured]

Use dynamic context injection only for compact, relevant fields. ADK supports instruction templating and `InstructionProvider` for dynamic instructions; this should be used deliberately, with missing-key behavior and literal brace handling understood.[^adk-state]

### Use examples sparingly and deliberately

Few-shot examples are valuable when they define a format, judgment boundary, or failure pattern that prose cannot express compactly. Gemini documentation recommends examples but warns that too many examples can cause overfitting to those examples.[^gemini-prompt] For this product, examples should be:

- Few: normally 1 to 3 per agent.
- Varied: include a normal case, a sparse-evidence case, and a conflicting-evidence case when relevant.
- Synthetic and evergreen: avoid stale restaurant facts or source-specific facts in stable prompts.
- Covered by evals: every example should correspond to a testable behavior.

### Avoid brittle recipes

Bad prompt shape:

> If the user asks about pricing, do steps A1-A9. If reviews, do B1-B12. If expansion, do C1-C14. If competitor tracking, do D1-D10.

Better prompt shape:

> Identify decision type, venue/geography/timeframe/comparison set, evidence needed, source priority, sufficiency threshold, and output structure. Use the tools required to fill the evidence plan. If evidence is insufficient, say so and give the best supported next step.

The second form scales because it defines reusable dimensions rather than memorized branches. Use-case recipes belong in eval scenarios and tool tests. If a branch is deterministic, implement it in code or workflow.

### Avoid vague breadth

The opposite failure is a prompt that says "be a strategic restaurant consultant" or "answer comprehensively" without evidence rules, source rules, or output limits. For Superextra, every broad instruction should be converted into an observable requirement:

- "Be strategic" becomes "state the decision implication and one practical next move."
- "Be accurate" becomes "do not make unsupported numeric claims; cite source-backed claims; label estimates."
- "Be comprehensive" becomes "cover the requested metrics and the highest-impact caveat; avoid unrelated background."
- "Use sources" becomes "use tool-returned source metadata; cite each business-critical claim."

## Scalable Behavior Across User Questions

The agent should handle many user questions through a stable operating loop:

1. Parse the request: venue, location, market, timeframe, competitors, decision, metric, requested format.
2. Decide whether to proceed, ask one clarification, or state assumptions.
3. Build an evidence plan: source families, freshness needs, comparison set, metrics, known risks.
4. Retrieve with tools: structured APIs first, web/grounding where current or public data is needed, internal data where licensed and indexed.
5. Normalize: entity resolution, units, date ranges, currency, source provenance, deduplication.
6. Verify: source quality, conflict checks, arithmetic, citation support, and missing-data flags.
7. Synthesize: direct answer, key evidence, implication, recommendation, caveats, and sources.
8. Persist only appropriate session state or memory.

This loop is consistent with ReAct's action-observation pattern, ADK tool and workflow primitives, and ADK evaluation's emphasis on both final response and tool trajectory.[^react][^adk-tools][^adk-workflow][^adk-eval]

For restaurant-market questions, the default evidence plan should consider:

- Entity: exact venue/place identity, chain/brand relation, neighborhood, city, country.
- Geography: radius, trade area, neighborhood, comparable markets.
- Time: current snapshot, last month, season, year-over-year, event period.
- Competitor set: direct cuisine/price/category competitors, delivery competitors, nearby substitutes.
- Metric type: factual listing data, prices, reviews, sentiment, foot traffic, openings/closures, labor, rent, revenue estimate, promotion, channel mix.
- Decision type: explain, benchmark, diagnose, forecast, choose, monitor, or recommend.

These are not prompt recipes. They are product-level context dimensions that can be extracted, validated, and passed through tools.

## Tools, Sources, Citations, and Verification

### Tool design

Tools should be narrow, typed, observable, and defensive. Gemini function calling describes the model as selecting a function and arguments, while the application is responsible for executing the function and returning results.[^gemini-function] ADK tools execute developer-defined logic and can access `ToolContext` for state, actions, memory, and flow control.[^adk-tools] Therefore:

- Tool names and docstrings must describe what the tool does and what inputs mean.
- Tool schemas must make invalid calls hard: enum values, required fields, units, date formats, and entity IDs.
- Tool outputs must be structured, not just prose.
- Tool errors must be structured: `no_data`, `ambiguous_entity`, `rate_limited`, `auth_error`, `source_unavailable`, `retryable_error`.
- Tools must enforce authorization, source access, policy, rate limits, and data boundaries in code.
- Tools must return provenance: source, retrieved time, observed time, entity ID, and transformation notes.

The prompt should say when and why to use a tool. The tool implementation should decide what is allowed, how retries work, how data is normalized, and what counts as a valid result.

### Source policy

For Superextra, source quality should be handled as product logic plus agent instruction. A practical hierarchy:

1. Licensed/internal structured data with known provenance.
2. Official business, registry, platform, or API sources.
3. Reputable third-party datasets or publications.
4. Public web pages and user-generated content, with stronger uncertainty labels.

The agent should not average incompatible data or treat scraped pages as equivalent to official APIs. If sources disagree, the answer should say what differs, which source is preferred, why, and what remains unresolved. CRAG's core warning is relevant: RAG systems depend heavily on retrieval relevance, and generation becomes fragile when retrieval goes wrong.[^crag]

### Citation policy

Citations are required for:

- Business-critical factual claims.
- Current facts likely to change.
- Numeric values, rankings, price points, estimates, and trend claims.
- Competitive comparisons.
- Recommendations whose reasoning depends on external evidence.

Citations are not required for:

- General product navigation.
- Reasonable framing or definitions that do not affect the decision.
- Clearly marked inference, as long as the supporting facts are cited.

The answer should connect citations to claims, not place an undifferentiated source pile at the end. Gemini grounding metadata's `groundingSupports` is the right model: source links should attach to supported text spans.[^gemini-search]

### Verification policy

Before final synthesis, the system should check:

- Identity: the venue and competitors refer to the intended places.
- Freshness: current questions use current data.
- Completeness: the evidence plan covers the user's requested dimensions.
- Conflict: material contradictions are resolved or disclosed.
- Math: calculations, units, currencies, and date ranges are consistent.
- Support: every material claim has source metadata or is labeled as inference.
- Sufficiency: if evidence is too thin, the answer says so.

The verification step can be prompt-guided, but important checks should move into code, callbacks, validators, or evals wherever possible.

## Sessions, State, and Memory

ADK separates current conversation (`Session`), data within that conversation (`State`), and searchable cross-session information (`Memory`).[^adk-sessions] This distinction should govern product design:

- Session history: what the user and agent said and did in this conversation.
- Session state: current venue, selected place, active comparison set, pending clarification, temporary evidence, and run-specific flags.
- User memory: stable preferences or business context that should carry across sessions.
- App memory/config: shared product settings, source policies, schema versions, and tool metadata.

Do not store raw market conclusions as long-term memory without source, date, and expiry. A remembered statement like "Restaurant X is expensive" becomes stale and dangerous. A better memory item is "User often compares casual Italian venues in Warsaw using delivery price benchmarks," because it improves context without freezing market facts.

Memory Bank and ADK memory services are appropriate for personalization and cross-session continuity, but the product must decide what is safe, useful, and allowed to remember.[^adk-memory][^agent-platform] Memory retrieval should be visible to the agent as evidence about user context, not as market truth.

## Callbacks, Guardrails, and Product Logic

Callbacks are the right place to observe, customize, or control execution at agent, model, and tool boundaries. ADK callbacks can inspect or override model calls, tool calls, and agent outputs, making them suitable for logging, caching, guardrails, policy checks, and output sanitation.[^adk-callbacks]

Use callbacks and product logic for:

- Prompt/version logging.
- Tool-call argument validation.
- Source allowlist/blocklist enforcement.
- Citation presence checks.
- PII and sensitive-data handling.
- Budget and latency enforcement.
- Fallbacks when a tool fails.
- Refusal or escalation for disallowed actions.

Do not rely on a prompt instruction to enforce access control, source licensing, or security policy. ADK safety guidance is explicit that identity, authorization, tool guardrails, callbacks/plugins, sandboxing, evaluation, tracing, and network controls all matter.[^adk-safety]

## Evaluation Standard

Agent changes should ship only with eval evidence. ADK states that agent evaluation must assess both final output and trajectory/tool use, because traditional pass/fail tests are not enough for probabilistic systems.[^adk-eval] ADK provides criteria for exact/in-order/any-order tool trajectory, response match, LLM-judged semantic match, rubric-based final response quality, rubric-based tool-use quality, hallucination, safety, and multi-turn task success.[^adk-eval-criteria]

Superextra should maintain at least these eval sets:

- Intent and context extraction: venue, geography, timeframe, comparison set, and decision type.
- Tool trajectory: correct source family selection and no unnecessary tools.
- Entity ambiguity: multiple venues with similar names, missing city, wrong country, chain vs location.
- Sparse evidence: answer admits limits instead of inventing.
- Conflicting evidence: answer surfaces disagreement and explains preference.
- Citation support: material claims map to source metadata.
- Quantitative reasoning: currency, percent change, ranking, benchmark, and time-window calculations.
- Domain output quality: clear decision implication, caveat, and next action.
- Multi-turn continuity: follow-up questions reuse session context without overusing long-term memory.
- Safety and prompt injection: retrieved source text cannot change agent instructions.

LLM-as-judge evals are useful but not sufficient. Research has documented biases in LLM judging, including position and preference biases, so judge-based metrics should be calibrated against human expert review for high-impact product claims.[^llm-judge] Microsoft's agent-evaluation guidance similarly frames evaluation as a development and deployment baseline with acceptance thresholds, quality/safety evaluators, and workflow integration.[^microsoft-eval]

Every prompt change should include:

- The behavioral hypothesis.
- The evals expected to improve.
- The evals expected not to regress.
- A small production-log sample if available.
- The prompt diff.
- Rollback criteria.

If a prompt change cannot be evaluated, it should be treated as experimental.

## What Belongs Where

| Concern                      | Prompt        | Code/workflow | Tool                  | Eval | Product logic |
| ---------------------------- | ------------- | ------------- | --------------------- | ---- | ------------- |
| Agent mission and scope      | Yes           | Maybe         | No                    | Yes  | Yes           |
| Deterministic routing rules  | Minimal       | Yes           | No                    | Yes  | Yes           |
| Source priority policy       | Brief summary | Yes           | Yes                   | Yes  | Yes           |
| API calls and data access    | No            | Yes           | Yes                   | Yes  | Yes           |
| Auth, licensing, permissions | No            | Yes           | Yes                   | Yes  | Yes           |
| Retry, timeout, rate limit   | No            | Yes           | Yes                   | Yes  | Yes           |
| Citation formatting          | Yes           | Yes           | Tool returns metadata | Yes  | Yes           |
| JSON/schema validity         | Minimal       | Yes           | Yes                   | Yes  | Yes           |
| Arithmetic and normalization | No            | Yes           | Yes                   | Yes  | Yes           |
| Tone and final answer shape  | Yes           | Maybe         | No                    | Yes  | Yes           |
| Source conflict handling     | Yes           | Yes           | Yes                   | Yes  | Yes           |
| Long-term memory rules       | Brief         | Yes           | Maybe                 | Yes  | Yes           |
| Guardrails and refusals      | Brief         | Yes           | Yes                   | Yes  | Yes           |

The governing rule: prompts express intent and judgment criteria; code and tools enforce deterministic behavior; evals decide whether the system actually works.

## Review Checklist for Current Prompts

Use this checklist in the next task:

- Does each agent have a single clear responsibility?
- Is any prompt trying to be a router, data catalog, policy engine, and writer at the same time?
- Are agent descriptions specific enough for delegation?
- Are deterministic flows handled outside the LLM where possible?
- Is tool use described by when/why, while schemas/docstrings describe what/how?
- Do tools return structured data with source metadata?
- Does the prompt require citations for business-critical claims?
- Can citations be generated from structured provenance instead of model memory?
- Does the agent have a clear insufficient-evidence behavior?
- Does the prompt avoid long use-case branches that should be evals or code?
- Does the prompt avoid vague "be comprehensive" language without measurable requirements?
- Are examples few, varied, and covered by evals?
- Is session state separated from long-term memory?
- Are stale market facts prevented from becoming durable memory?
- Are prompt injection risks from retrieved text handled outside the prompt?
- Are there evals for tool trajectory, answer quality, hallucination, safety, and multi-turn behavior?

## Evidence Strength and Uncertainties

Strong evidence:

- Google/ADK docs are authoritative for how this stack expects agents, tools, state, memory, callbacks, grounding, and evaluation to work.
- Gemini API docs are authoritative for prompt-design, function-calling, structured output, and Google Search grounding behavior.
- Agent Platform docs are authoritative for managed runtime, Sessions, Memory Bank, governance, and observability surfaces.

Moderate evidence:

- Anthropic's "Building effective agents" is high-quality practitioner guidance and agrees with the Google stack's workflow-vs-agent separation, but it is not a controlled study.
- Microsoft Foundry evaluation guidance is useful cross-vendor confirmation that agent evals need quality, safety, behavior, and acceptance thresholds.
- ReAct, Self-RAG, CRAG, and Lost in the Middle support the general principles of tool-use loops, retrieval self-checking, and avoiding overloaded context, but they do not prove a specific Superextra architecture will outperform another without product evals.

Uncertain or model-dependent:

- There is no universal optimal prompt length, number of examples, or agent count. Gemini guidance recommends examples, while also warning that too many can overfit.[^gemini-prompt]
- LLM-as-judge metrics are useful but biased; they should not be the sole gate for decision-grade restaurant intelligence.[^llm-judge]
- RAG and grounding reduce hallucination risk but do not eliminate it. Retrieval quality, source reliability, citation mapping, and synthesis checks remain necessary.[^gemini-search][^crag]

## References

[^internal-product]: Internal product context inspected only from product-facing files and project guidance: `AGENTS.md`, `src/lib/components/Hero.svelte`, `src/routes/agent/+page.svelte`, `src/lib/components/UseCases.svelte`, `src/lib/components/PlatformCards.svelte`, `src/lib/components/DataSources.svelte`, `src/lib/components/restaurants/RestaurantHero.svelte`, `src/lib/components/restaurants/ChatThread.svelte`, and `src/lib/chat-types.ts`. Current agent prompt/instruction files were not opened.

[^adk-llm]: Google Agent Development Kit, "LLM Agent", https://adk.dev/agents/llm-agents/ (accessed 2026-05-09).

[^adk-workflow]: Google Agent Development Kit, "Workflow Agents", https://adk.dev/agents/workflow-agents/ (accessed 2026-05-09).

[^adk-multi]: Google Agent Development Kit, "Multi-Agent Systems in ADK", https://adk.dev/agents/multi-agents/ (accessed 2026-05-09).

[^adk-tools]: Google Agent Development Kit, "Custom Tools for ADK", https://adk.dev/tools-custom/ (accessed 2026-05-09).

[^adk-sessions]: Google Agent Development Kit, "Introduction to Conversational Context: Session, State, and Memory", https://adk.dev/sessions/ (accessed 2026-05-09).

[^adk-state]: Google Agent Development Kit, "State: The Session's Scratchpad", https://adk.dev/sessions/state/ (accessed 2026-05-09).

[^adk-memory]: Google Agent Development Kit, "Memory: Long-Term Knowledge with MemoryService", https://adk.dev/sessions/memory/ (accessed 2026-05-09).

[^adk-callbacks]: Google Agent Development Kit, "Callbacks: Observe, Customize, and Control Agent Behavior", https://adk.dev/callbacks/ (accessed 2026-05-09).

[^adk-grounding]: Google Agent Development Kit, "Grounding agents with data", https://adk.dev/grounding/ (accessed 2026-05-09).

[^adk-safety]: Google Agent Development Kit, "Safety and Security for AI Agents", https://adk.dev/safety/ (accessed 2026-05-09).

[^adk-eval]: Google Agent Development Kit, "Why Evaluate Agents", https://adk.dev/evaluate/ (accessed 2026-05-09).

[^adk-eval-criteria]: Google Agent Development Kit, "Evaluation Criteria", https://adk.dev/evaluate/criteria/ (accessed 2026-05-09).

[^gemini-prompt]: Google AI for Developers, "Prompt design strategies", https://ai.google.dev/gemini-api/docs/prompting-strategies (accessed 2026-05-09).

[^gemini-function]: Google AI for Developers, "Function calling with the Gemini API", https://ai.google.dev/gemini-api/docs/function-calling (accessed 2026-05-09).

[^gemini-search]: Google AI for Developers, "Grounding with Google Search", https://ai.google.dev/gemini-api/docs/google-search (accessed 2026-05-09).

[^gemini-structured]: Google AI for Developers, "Structured outputs", https://ai.google.dev/gemini-api/docs/structured-output (accessed 2026-05-09).

[^agent-platform]: Google Cloud, "Agents overview", Gemini Enterprise Agent Platform, https://docs.cloud.google.com/gemini-enterprise-agent-platform/agents/overview (accessed 2026-05-09). See also "Agent Platform overview", https://docs.cloud.google.com/gemini-enterprise-agent-platform/overview, "Scale your agents", https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale, "Agent Platform Sessions overview", https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sessions, and "Agent Platform Memory Bank", https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank.

[^anthropic-agents]: Anthropic, "Building effective agents", https://www.anthropic.com/engineering/building-effective-agents (accessed 2026-05-09).

[^microsoft-eval]: Microsoft Learn, "Evaluate your AI agents - Microsoft Foundry", https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluate-agent (accessed 2026-05-09).

[^react]: Shunyu Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models", International Conference on Learning Representations, 2023, https://openreview.net/forum?id=WE_vluYUL-X.

[^self-rag]: Akari Asai et al., "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection", International Conference on Learning Representations, 2024, https://openreview.net/forum?id=hSyW5go0v8.

[^crag]: Shi-Qi Yan et al., "Corrective Retrieval Augmented Generation", https://openreview.net/forum?id=JnWJbrnaUE.

[^lost-middle]: Nelson F. Liu et al., "Lost in the Middle: How Language Models Use Long Contexts", Transactions of the Association for Computational Linguistics, 2024, https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00638/119630/Lost-in-the-Middle-How-Language-Models-Use-Long.

[^prompt-report]: Sander Schulhoff et al., "The Prompt Report: A Systematic Survey of Prompting Techniques", 2024, https://arxiv.org/abs/2406.06608.

[^llm-judge]: Lianmin Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena", NeurIPS 2023, https://proceedings.neurips.cc/paper_files/paper/2023/hash/91f18a1287b398d378ef22505bf41832-Abstract-Datasets_and_Benchmarks.html. See also Xuanhao Wu and Rachel A. Bittner, "Judging the Judges: A Systematic Investigation of Position Bias in Pairwise Comparative Assessments by LLMs", 2024, https://arxiv.org/abs/2410.23826.
