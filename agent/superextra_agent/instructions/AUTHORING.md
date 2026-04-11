# Writing Agent Instructions

Read this before writing or modifying any instruction file in this directory.

## Architecture

```
Router → research_pipeline
           ├── Context Enricher (fetches Google Places data)
           ├── Research Orchestrator (reconnaissance, plans, dispatches specialists)
           ├── Specialist Pool (parallel execution of assigned specialists)
           ├── Gap Researcher (audits Phase 1 outputs, fills gaps)
           └── Synthesizer (produces final report)
```

The router classifies messages and either transfers to `research_pipeline` or asks for clarification.

**Key state keys:**

- `research_plan` — orchestrator's summary (core question, premise assessment, competitive set, specialists called). Read by gap researcher and synthesizer.
- `places_context` — Google Places data. Written by enricher, read by orchestrator, specialists, gap researcher, and synthesizer.
- `specialist_briefs` — dict mapping specialist names to brief text. Written by orchestrator, read by specialist instruction providers.

**Agent roles:**

- **Router** detects conversation state and routes.
- **Orchestrator** does reconnaissance, audits assumptions, defines the competitive set, writes specialist briefs, dispatches.
- **Specialists** are directed researchers. They only see their brief and Places context, not the user's question or each other's output.
- **Gap researcher** reads all Phase 1 outputs, identifies gaps and contradictions, fills top 1-2 gaps.
- **Synthesizer** reads all outputs. Uses the orchestrator's premise assessment as its starting framework, verifies against specialist evidence, produces the user-facing report.

## Base template system

Specialist instructions use a two-file composition:

1. **`specialist_base.md`** — shared boilerplate (role line, date awareness, assignment preamble, how-to-answer, tone, boundaries)
2. **`{specialist_name}.md`** — unique body (scope, methodology, places guidance, answer specifics)

`_make_instruction()` in `specialists.py` assembles: base template with `{specialist_body}` replaced by the specialist's body, `{role_title}` replaced from `_ROLE_TITLES` dict. Then `{places_context}` is substituted at runtime, source guidance is appended, and the brief is appended if assigned.

Exceptions: `gap_researcher` uses its own standalone template (different structure, reads all specialist outputs).

## Rules

These exist because we hit each problem at least once.

1. **Agents take the path of least resistance.** If a specialist has Google Places data and isn't told to go beyond it, it will reformat that data and call it research. Every specialist body must say: Places data is your starting point, not your output.

2. **Agents don't coordinate.** If scopes overlap, they produce identical output. The orchestrator must assign non-overlapping briefs with explicit boundaries. The orchestrator also defines a shared competitive set so all specialists analyze the same restaurants.

3. **LLMs default to summarizing.** The synthesizer was compressing 25K chars to 2.2K (91% loss). "Preserve depth" must be explicit — preserve tables, quotes, numbers, citations.

4. **Specialists can't infer what they can't see.** The orchestrator must relay: response language, date, competitive set, what other specialists are covering.

5. **Relevance filtering is the orchestrator's job.** Specialists don't self-filter. The orchestrator only calls specialists whose domain fits.

6. **"Be thorough" is not an instruction.** "Try at least 3 different search queries" is. Make methodology concrete.

7. **Don't copy-paste across specialist body files without customizing.** Shared structure lives in `specialist_base.md`. Body files contain only domain-specific content.

8. **Domain boundaries live in the orchestrator.** When a topic could go to multiple specialists, add ownership rules to the orchestrator's "Domain boundaries" section.

9. **Agents are sycophantic by default.** Three structural checkpoints enforce objectivity:
   - **Orchestrator:** Must list each assumption with a verdict (SUPPORTED / QUESTIONABLE / CONTRADICTED / UNTESTED) and define the competitive set in its plan summary.
   - **Specialists:** Must end every response with a "Brief alignment" statement.
   - **Synthesizer:** Must use the orchestrator's premise assessment as its starting framework, then verify against specialist evidence. Translates internal labels into natural analyst language. Leads with what data shows when it differs from assumptions.
     Without these checkpoints, each layer defaults to confirming whatever it received from above.

## Instruction structure

**Specialist body files** contain only domain-specific content:

1. Your scope (domain knowledge reference)
2. How to research (domain-specific search strategies)
3. Restaurant context from Google Places (`{places_context}` template)
4. Answer specifics (optional — domain-specific format requirements beyond the base)

The base template provides: role description, date awareness, assignment preamble, how-to-answer checklist, tone, boundaries, brief alignment requirement.

## Template variables

Specialist body files use `{places_context}`, injected at runtime by `_make_instruction()` in `specialists.py`. The base template uses `{role_title}` and `{specialist_body}`, resolved at import time via `str.replace()`.

The synthesizer and gap researcher have many variables (`{places_context}`, `{research_plan}`, `{market_result}`, etc.) resolved at runtime by their instruction providers in `agent.py` / `specialists.py`.

Templates use Python's `str.format()` for runtime variables. Never add literal curly braces to `.md` files — use doubled braces (`{{`, `}}`) to escape them.

## Modification checklist

**Adding a specialist:**

1. Create the body `.md` file (scope + methodology + places guidance only)
2. Add role title to `_ROLE_TITLES` dict in `specialists.py`
3. Add the `LlmAgent` via `_make_specialist()` in `specialists.py`
4. Add to `ALL_SPECIALISTS` list
5. Update "Available specialists" in `research_orchestrator.md`
6. Add `output_key` to `_SYNTHESIZER_KEYS` in `agent.py`
7. Add `{result_key}` in `synthesizer.md`

**Adding a template variable:**

1. Add `{variable_name}` to the `.md` file
2. Update the instruction provider to resolve it from `ctx.state`
3. Ensure an upstream agent writes to that state key

**Adding an ambiguous domain topic:**

1. Add ownership rules to "Domain boundaries" in `research_orchestrator.md`
