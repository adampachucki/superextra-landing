# Writing Agent Instructions

Read this before writing or modifying any instruction file in this directory.

## Architecture

The agent uses a single pipeline for all messages:

```
Router → research_pipeline
           ├── Context Enricher (fetches Google Places data)
           ├── Research Orchestrator (reconnaissance, plans, dispatches specialists)
           └── Synthesizer (produces final report)
```

The router classifies the message (ready to research, too vague, or follow-up) and either transfers to `research_pipeline` or asks a clarifying question.

**Key state keys:**

- `research_plan` — orchestrator's summary (core question, premise assessment, specialists called). Read by synthesizer.
- `places_context` — Google Places data. Written by enricher, read by orchestrator and synthesizer.

**Agent roles:**

- The **router** detects conversation state and routes: researchable → pipeline, vague → clarify, follow-up → pipeline.
- The **orchestrator** does reconnaissance via google_search, audits assumptions, identifies research angles, writes detailed specialist briefs, and dispatches all specialists in parallel. It always runs after the enricher, so Places data is available.
- **Specialists** are directed researchers. They only see their brief, not the user's question, the session state, or each other's output.
- The **synthesizer** reads all specialist outputs from state and produces the user-facing answer. It does not research.

## Rules

These exist because we hit each problem at least once.

1. **Agents take the path of least resistance.** If a specialist has Google Places data and isn't told to go beyond it, it will reformat that data and call it research. Every specialist instruction must say: the Places context is your starting point, not your output.

2. **Agents don't coordinate.** If scopes overlap, they will produce identical output. The orchestrator must assign non-overlapping briefs with explicit "do not research X" boundaries.

3. **LLMs default to summarizing.** The synthesizer was compressing 25K chars to 2.2K (91% loss). "Preserve depth" must be an explicit instruction — preserve tables, quotes, numbers, source citations.

4. **Specialists can't infer what they can't see.** The orchestrator must relay: response language, date (`[Date: ...]` format), what other specialists are covering. When you add new context that specialists need, the fix is always in the orchestrator's instructions.

5. **Relevance filtering is the orchestrator's job.** Specialists should not self-filter with "NOT_RELEVANT" logic. The orchestrator only calls specialists whose domain fits.

6. **"Be thorough" is not an instruction.** "Try at least 3 different search queries, check multiple platforms, and quantify patterns" is. Make methodology concrete.

7. **Don't copy-paste across specialist files without customizing.** Shared structure is fine, but examples and methodology must be domain-specific. A menu pricing agent shouldn't have "new restaurants Mokotow 2026" as its search example.

8. **Domain boundaries live in the orchestrator.** When a topic could go to multiple specialists (rent, delivery platforms, reviews), add explicit ownership rules to the orchestrator's "Domain boundaries" section.

9. **Agents are sycophantic by default.** LLMs agree with the user's framing unless explicitly told not to. Permission alone is not enough — you need structural forcing functions that make objectivity a mandatory output, not an optional behavior. Three checkpoints enforce this:
   - **Orchestrator:** Must list each assumption in the question with a verdict (SUPPORTED / QUESTIONABLE / CONTRADICTED / UNTESTED) in its plan summary. This forces conscious evaluation before research begins.
   - **Specialists:** Must end every response with a "Brief alignment" statement — one sentence stating whether findings SUPPORT, PARTIALLY SUPPORT, CONTRADICT, or are INDEPENDENT OF the brief's framing. This prevents silent confirmation.
   - **Synthesizer:** Must read orchestrator verdicts and specialist alignment signals, but translate them into natural analyst language — never echo the internal labels (SUPPORTED, CONTRADICTED, etc.) in the user-facing report. Leads with what the data shows when it differs from the question's assumptions. Must also evaluate independently — even if upstream layers flagged no concerns.
     Without these structural checkpoints, each layer defaults to confirming whatever it received from the layer above.

## Instruction structure

Every specialist instruction follows this structure:

1. Role description (1-2 sentences)
2. Date awareness (`[Date: ...]` prefix)
3. Your assignment (follow the orchestrator's brief)
4. Your scope (domain knowledge reference, not task instruction)
5. How to research (domain-specific search strategies)
6. Restaurant context from Google Places (`{places_context}` template)
7. How to answer (format, specificity, citations)
8. Tone
9. Boundaries

The "Your assignment" section is critical — without it, agents revert to interpreting broadly.

## Template variables

Specialist instructions use `{places_context}`, injected at runtime by `_make_instruction()` in `specialists.py`. The synthesizer has many variables (`{places_context}`, `{research_plan}`, `{market_result}`, etc.) resolved by `_synthesizer_instruction()` in `agent.py`.

Templates use Python's `str.format()`. Never add literal curly braces to `.md` files — use doubled braces (`{{`, `}}`) to escape them.

## Modification checklist

**Adding or removing a specialist:**

1. Create/delete the instruction `.md` file
2. Add/remove the `LlmAgent` in `specialists.py`
3. Add/remove the `AgentTool` wrapper in `SPECIALIST_TOOLS`
4. Update "Available specialist agents" in `research_orchestrator.md`
5. Add/remove `output_key` from `_SYNTHESIZER_KEYS` in `agent.py`
6. Add/remove `{result_key}` in `synthesizer.md`

**Adding a new template variable:**

1. Add `{variable_name}` to the `.md` file
2. Update `_make_instruction()` to resolve it from `ctx.state`
3. Ensure an upstream agent writes to that state key

**Adding an ambiguous domain topic:**

1. Add ownership rules to "Domain boundaries" in `research_orchestrator.md`
2. Clarify scope in relevant specialist `.md` files if needed
