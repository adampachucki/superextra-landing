# Writing Agent Instructions

Read this before writing or modifying any instruction file in this directory.

## Architecture

```
Router -> research_pipeline
           ├── Context Enricher (fetches Google Places data)
           └── Research Lead (reconnaissance, coverage planning, specialist tool calls, final report)
```

The router classifies messages and either transfers to `research_pipeline`, transfers to `follow_up`, or asks for clarification.

**Key state keys:**

- `places_context` - Google Places data. Written by the enricher, read by the research lead, specialists, and follow-up agent.
- Specialist result keys (`market_result`, `pricing_result`, etc.) - written by specialists when the research lead calls them as tools.
- `final_report` - written by the research lead. Read by the frontend and follow-up agent.
- `final_report_followup` - written by the follow-up agent for terminal follow-up replies without overwriting the original report.

**Agent roles:**

- **Router** detects conversation state and routes.
- **Research Lead** audits assumptions, does reconnaissance, identifies evidence surfaces, calls specialists directly as tools with specific `request` briefs, checks sufficiency, and writes the final report.
- **Specialists** are directed researchers. They see their `request` brief and Places context, not each other's output.
- **Follow-up** answers narrow follow-up questions from the existing report and Places context.

## Base template system

Specialist instructions use a two-file composition:

1. **`specialist_base.md`** - shared boilerplate (role line, date awareness, assignment preamble, how-to-answer, tone, boundaries)
2. **`{specialist_name}.md`** - unique body (scope, methodology, places guidance, answer specifics)

`_make_instruction()` in `specialists.py` assembles: base template with `{specialist_body}` replaced by the specialist's body, `{role_title}` replaced from `ROLE_TITLES`. Then `{places_context}` is substituted at runtime and source guidance is appended. The brief itself arrives as the AgentTool `request` user message.

## Rules

These exist because we hit each problem at least once.

1. **Agents take the path of least resistance.** If a specialist has Google Places data and isn't told to go beyond it, it will reformat that data and call it research. Every specialist body must say: Places data is your starting point, not your output.

2. **Agents don't coordinate.** If scopes overlap, they produce identical output. The research lead must call specialists with non-overlapping briefs and explicit boundaries. The lead also defines a shared competitive set so all specialists analyze the same restaurants.

3. **LLMs default to summarizing.** The research lead writes the final report directly, so depth preservation must be explicit in `research_lead.md`: preserve tables, quotes, numbers, and citations when they are central to the answer.

4. **Specialists can't infer what they can't see.** Each specialist `request` must relay: response language, date, competitive set, what other specialists are covering, and what not to cover.

5. **Relevance filtering is the research lead's job.** Specialists don't self-filter. The lead only calls specialists whose domain fits a material evidence surface.

6. **"Be thorough" is not an instruction.** "Try at least 3 different search queries" is. Make methodology concrete.

7. **Don't copy-paste across specialist body files without customizing.** Shared structure lives in `specialist_base.md`. Body files contain only domain-specific content.

8. **Domain boundaries live in the research lead prompt.** When a topic could go to multiple specialists, add ownership rules to `research_lead.md`.

9. **Agents are sycophantic by default.** Two structural checkpoints enforce objectivity:
   - **Research Lead:** Must audit assumptions, test the most important premise during reconnaissance, and translate findings into a final report that leads with data even when it contradicts the user's framing.
   - **Specialists:** Must end every response with a "Brief alignment" statement.

## Instruction structure

**Specialist body files** contain only domain-specific content:

1. Your scope (domain knowledge reference)
2. How to research (domain-specific search strategies)
3. Restaurant context from Google Places (`{places_context}` template)
4. Answer specifics (optional - domain-specific format requirements beyond the base)

The base template provides: role description, date awareness, assignment preamble, how-to-answer checklist, tone, boundaries, brief alignment requirement.

## Template variables

Specialist body files use `{places_context}`, injected at runtime by `_make_instruction()` in `specialists.py`. The base template uses `{role_title}` and `{specialist_body}`, resolved at import time via `str.replace()`.

The research lead prompt uses `{places_context}`. The follow-up prompt uses `{final_report}` and `{places_context}`. Both are resolved at runtime by instruction providers in `agent.py`.

Templates use Python's `str.format()` for runtime variables. Never add literal curly braces to `.md` files - use doubled braces (`{{`, `}}`) to escape them.

## Modification checklist

**Adding a specialist:**

1. Create the body `.md` file (scope + methodology + Places guidance only)
2. Add a specialist entry to `specialist_catalog.py`
3. Add a tool override in `specialists.py` only if the specialist needs non-default tools

**Adding a template variable:**

1. Add `{variable_name}` to the `.md` file
2. Update the instruction provider to resolve it from `ctx.state`
3. Ensure an upstream agent writes to that state key

**Adding an ambiguous domain topic:**

1. Add ownership rules to "Domain boundaries" in `research_lead.md`
