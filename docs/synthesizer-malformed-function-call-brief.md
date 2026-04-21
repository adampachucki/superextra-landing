# Synthesizer `MALFORMED_FUNCTION_CALL` — Investigation Brief

**Status:** open investigation, not started
**Owner:** TBD (targeted agent)
**Severity:** P2 — functional (users get a durable reply) but user-visible (disclaimer appears on most prod runs)
**Relation to other work:** independent of `docs/pipeline-decoupling-implementation-review-2026-04-21.md` PRs (P1 safety net is already merged and shipping as of 2026-04-21)

---

## Problem in one paragraph

The synthesizer agent (the final LlmAgent in our research pipeline) is configured to call
Gemini's **built-in `code_execution` tool** to generate matplotlib charts inline with its
written report. On a significant fraction of real user turns Gemini returns with
`error_code = "MALFORMED_FUNCTION_CALL"` instead of a normal response, the pre-existing
`_embed_chart_images` `after_model_callback` substitutes a text-only fallback report built
from specialist outputs (`_build_fallback_report`), and the user sees a disclaimer banner at
the top of the reply:

> _Note: final synthesis hit a model-level error (MALFORMED_FUNCTION_CALL) — typically
> during chart generation. The detailed specialist findings below are the raw research
> captured before synthesis failed._

The underlying specialist research is solid and the reply lands durably — but the disclaimer
signals to users that "the system broke," and no charts appear. Over time this erodes trust
in the product even when the content is strong.

This is **not** a regression from the pipeline-decoupling refactor. The fallback path has
existed since chart generation was introduced (see git blame on `_build_fallback_report`).
What changed is that the prod E2E validation of the P1 fix (2026-04-21) surfaced how often
it fires in practice — on the very first live run after deploy, on a plausible prompt
(Noma Copenhagen pricing + service issues).

---

## Evidence from the 2026-04-21 prod run

- **Session:** `sid=07a071be-106d-4e6d-9de6-5f830721eb84`, `runId=242c86da-d58b-45a2-98f2-cbfc4c7ee5ef`
- **User prompt:** "What are the biggest pricing and menu-positioning themes that set Noma apart from other high-end Copenhagen restaurants, and what service issues come up in reviews?" — placeContext=Noma Copenhagen
- **Result:** `status=complete`, `reply_len=26131`, `sources_n=29`, `title="Noma Pricing Service Reviews"`
- **Worker log at 2026-04-21 12:38:40 UTC (during this run):**
  > `WARNING  Synthesizer emitted MALFORMED_FUNCTION_CALL — falling back to text-only report`
- **UI rendered:** the fallback report with the "final synthesis hit a model-level error"
  disclaimer, then four specialist sections (Menu & Pricing, Guest Intelligence, Review
  Analysis, Gap Research) — no charts.
- **Events:** 10 events written to Firestore (`activity: 7`, `progress: 2`, `complete: 1`) —
  the `complete` event was the fallback report, not a synthesizer-authored one.

Pull similar data for the last ~50 prod runs via Cloud Logging query:

```
resource.type="cloud_run_revision"
resource.labels.service_name="superextra-worker"
severity=WARNING
textPayload=~"MALFORMED_FUNCTION_CALL" OR jsonPayload.message=~"MALFORMED_FUNCTION_CALL"
```

Bucket by `trace`/`runId` to get unique-run frequency. Target number to capture before
proposing a structural fix: what percentage of completed turns carry this warning?

---

## Technical context — exact code paths

### Synthesizer wiring

[`agent/superextra_agent/agent.py:267-278`](../agent/superextra_agent/agent.py)

```python
def _make_synthesizer(name="synthesizer"):
    return LlmAgent(
        name=name,
        model=MODEL_GEMINI,                    # gemini-3.1-pro-preview
        instruction=_synthesizer_instruction,  # loaded from instructions/synthesizer.md
        description="Synthesizes findings from all specialist agents ...",
        output_key="final_report",             # ADK writes response text into state.final_report
        generate_content_config=THINKING_CONFIG,
        before_model_callback=_inject_code_execution,
        after_model_callback=_embed_chart_images,
    )
```

Model: `gemini-3.1-pro-preview`
([`agent/superextra_agent/specialists.py:95-113`](../agent/superextra_agent/specialists.py))
with `thinking_config.thinking_level="HIGH"`.

### `code_execution` tool injection

[`agent/superextra_agent/agent.py:109-122`](../agent/superextra_agent/agent.py)

```python
def _inject_code_execution(*, callback_context, llm_request):
    """Add code execution tool to the synthesizer's request.

    We inject the tool manually instead of using BuiltInCodeExecutor so that
    ADK's code execution post-processor doesn't strip inline_data images and
    save them to an artifact service.  This lets _embed_chart_images convert
    them to base64 data URIs that flow through as regular text.
    """
    llm_request.config = llm_request.config or types.GenerateContentConfig()
    llm_request.config.tools = llm_request.config.tools or []
    llm_request.config.tools.append(
        types.Tool(code_execution=types.ToolCodeExecution())
    )
    return None
```

Note: this is Gemini's **native built-in tool**
(`types.ToolCodeExecution()`), not a Python callable we wrote. The model generates Python
code, Gemini's sandbox executes it, images come back as `inline_data` parts.

### Synth instruction around charts

[`agent/superextra_agent/instructions/synthesizer.md:46-50`](../agent/superextra_agent/instructions/synthesizer.md)

```
When findings include numerical data for comparison, generate charts using matplotlib via
code execution. This is a core deliverable.

Place each chart inline where it supports the narrative — generate immediately when
presenting the finding, not batched at end. Bar charts for comparisons, pie charts for
market share, line charts for trends.

Keep charts clean: labeled axes, clear title, `seaborn.set_style("whitegrid")`,
`fig.patch.set_facecolor('#fefdf9')`, `ax.set_facecolor('#fefdf9')`, `plt.tight_layout()`,
`plt.show()`. Skip only if genuinely no numerical data exists.
```

### The fallback path that currently hides the problem

[`agent/superextra_agent/agent.py:139-189`](../agent/superextra_agent/agent.py)

`_build_fallback_report(state, error_code)` concatenates whatever is in
`_FALLBACK_SECTIONS` (the canonical specialist keys — `market_result`, `pricing_result`,
..., `dynamic_result_2`) and prepends the disclaimer banner.

`_embed_chart_images` is the `after_model_callback`. Its relevant branch:

```python
error_code = getattr(llm_response, "error_code", None)
if error_code:
    logger.warning(
        "Synthesizer emitted %s — falling back to text-only report",
        error_code,
    )
    fallback = _build_fallback_report(callback_context.state, error_code)
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=fallback)])
    )
```

The returned `LlmResponse.content.parts[0].text` becomes the value ADK writes to
`state.final_report` (because the agent has `output_key="final_report"`). That value then
flows through `_map_synthesizer` in
[`agent/superextra_agent/firestore_events.py:289-334`](../agent/superextra_agent/firestore_events.py)
as the `complete` event's `reply`.

So when `MALFORMED_FUNCTION_CALL` fires, the whole downstream chain is the fallback path —
the actual synth-written narrative never exists.

### How the P1 fix relates (already shipped — do not re-do)

The P1 refactor
(`docs/pipeline-decoupling-implementation-review-2026-04-21.md`, merged in PR #6) widened
three safety nets:

1. `_map_synthesizer` now also emits `complete` when `content.parts[*].text` is populated
   but `state_delta.final_report` is missing.
2. `_embed_chart_images` extends its fallback trigger to cover empty responses (no content,
   no parts, no text) without `error_code`.
3. Worker `_build_degraded_reply` stitches a report from `accumulated_state` as a
   last-resort if neither of the above fired.

**The P1 fix is orthogonal to this investigation** — it guarantees the reply lands
durably regardless of synth shape. The problem being investigated here is the
_user-facing quality_ of that durable reply when the synth itself fails.

---

## What `MALFORMED_FUNCTION_CALL` actually means

- **Gemini source-of-truth:** the enum member of Gemini's
  [`FinishReason`](https://ai.google.dev/api/generate-content#FinishReason) — "The
  function call generated by the model is invalid."
- **Google AI Forum thread** (multiple devs hitting this with grounded code execution in
  2024–2025): https://discuss.ai.google.dev/t/malformed-function-call-with-grounded-search-and-code-execution/80094
  — common triggers reported: long tool response chains, non-UTF-8 characters in passed
  data, structured outputs that the model tries to coerce into a tool call.
- **Gemini `code_execution` docs:**
  https://ai.google.dev/gemini-api/docs/code-execution — built-in Python sandbox, returns
  `code_execution_result` + `inline_data` image parts.
- **Gemini API errors catalog:**
  https://ai.google.dev/gemini-api/docs/troubleshooting — covers rate limits and quota but
  not specifically `MALFORMED_FUNCTION_CALL`.
- **Vertex AI `code_execution` docs (we use Vertex backend, not public AI Studio):**
  https://cloud.google.com/vertex-ai/generative-ai/docs/code-execution-api
- **ADK `BuiltInCodeExecutor` docs / source** (the class we _deliberately do not use_, see
  `_inject_code_execution` docstring): https://google.github.io/adk-docs/agents/llm-agents/
  and
  https://github.com/google/adk-python/blob/main/src/google/adk/code_executors/built_in_code_executor.py
- **ADK `LlmAgent` + `output_key` semantics:**
  https://google.github.io/adk-docs/agents/llm-agents/#output-key — `output_key` writes
  the LLM's text response into session state under that key, which is what feeds our
  `state_delta.final_report` contract.

The likely mechanism in our code:

1. Synth instruction tells Gemini to generate matplotlib charts via code_execution.
2. Gemini proposes a code-execution tool call.
3. Something in the tool call is malformed — most commonly (per the AI Forum thread)
   either the code itself has an encoding issue or the tool-call envelope is invalid
   when the model tries to pass long structured data from the specialist outputs (which
   are injected into the synth instruction via `_synthesizer_instruction`).
4. Gemini returns with `finish_reason=MALFORMED_FUNCTION_CALL`, no content parts.
5. Our callback catches it and falls back.

**Open question** the investigating agent should answer before picking a fix: is the
malformation in the _emitted code_ or in the _function-call envelope_? A sample of raw
`llm_response` objects (pre-callback) pulled from Cloud Logging would settle this.

---

## Frequency — what we actually know

Unknown in absolute terms. Data points we have:

- The single prod E2E after the 2026-04-21 deploy fired it.
- Prior live E2E (`agent/tests/e2e_worker_live.py`, 2026-04-20) — the log of the passing
  run at `agent/tests/e2e_worker_live.log` shows 23 ADK events ending in `run_complete`
  with no `MALFORMED_FUNCTION_CALL` warning (that run succeeded with a real synth-authored
  report, `reply_len=336175`). So the failure is **intermittent, not deterministic**.
- Earlier session transcripts referenced a multi-turn follow-up that produced a 631-char
  follow_up agent reply — the follow_up agent (see `agent.py:283+`) does **not** use
  code_execution, so it's a cleaner surface than the first-turn synth.

**First task for the agent:** pull 7–30 days of Cloud Logging and compute:

- % of completed turns where `Synthesizer emitted MALFORMED_FUNCTION_CALL` fires
- time-series trend (has it gotten worse since any specific deploy?)
- any correlation with prompt shape (pricing queries? specific specialists in the run?)
- any correlation with specialist output size (does the synth fail more when specialists
  return long / special-char-heavy text?)

Cloud Logging query template:

```
resource.type="cloud_run_revision"
resource.labels.service_name="superextra-worker"
jsonPayload.message=~"MALFORMED_FUNCTION_CALL"
```

Cross-reference with `event="run_complete"` entries to compute rate.

---

## Three candidate fix directions

**The investigating agent should pick one after running the frequency + mechanism
diagnostic above — do not pick blind.**

### Fix A — UX patch (fast, cover while diagnosing)

Soften or drop the disclaimer banner in `_build_fallback_report`. Current wording
surfaces an internal error code to users. Candidate rewrite:

```python
# instead of:
# "_Note: final synthesis hit a model-level error (MALFORMED_FUNCTION_CALL) — typically
#  during chart generation. The detailed specialist findings below are the raw research
#  captured before synthesis failed._\n\n"

# something neutral like:
# "_Research findings below, organized by analysis area._\n\n"
# or drop the banner entirely.
```

The `error_code` label still gets logged for ops without appearing in user-facing text.
Tradeoff: hides the fact that charts are missing. If charts are normally expected and
users notice their absence, a softer but more specific banner is worth considering
(e.g. "_Charts couldn't be generated for this report. Full research findings below._").

Estimated effort: one file, one commit, one test update in
`agent/tests/test_embed_chart_images.py`.

### Fix B — Diagnose + harden (medium)

After the frequency/mechanism diagnostic, if the root cause is a specific trigger
(e.g. specialist outputs over a certain size, or specific non-UTF-8 chars), harden one
of:

- **Pre-synth scrub** of specialist outputs — normalize non-UTF-8, strip problematic
  tokens, truncate oversized sections before injection into `_synthesizer_instruction`.
- **Simplify the chart instructions** in `instructions/synthesizer.md:46-50` — the
  current instruction demands matplotlib charts for "numerical data for comparison";
  requiring `seaborn.set_style("whitegrid")` and a specific facecolor mix is a lot of
  surface area for the model to get wrong. Shortening the chart guidance reduces the
  chance of a tool-call malformation.
- **Retry once with chart generation disabled** in `_embed_chart_images` when the first
  attempt hits `MALFORMED_FUNCTION_CALL` — ADK doesn't expose a direct way to re-run
  with a different tool config from inside the callback, so this may require a
  before-model wrap rather than after-model.

Estimated effort: 1–3 days depending on what the diagnostic shows.

### Fix C — Decouple chart generation from synth (larger, structural)

If the failure rate is high enough that synth-authored narratives are the minority on
prod, the code_execution tool is structurally unreliable for our use case. Options:

- **Two-step pipeline:** synth (no tools) writes the narrative, then a separate
  post-synth agent extracts the chart-worthy data tables and generates charts in a
  scoped context where a failure only loses the charts, not the narrative.
- **Predefined chart templates:** instead of letting the model generate arbitrary
  matplotlib, have it pick from a set of templates (bar, pie, line, grouped bar) and
  provide only the data — then we render server-side, bypassing code_execution entirely.
- **Drop inline charts from synth;** surface them as an optional enrichment in the
  followup/agent flow.

Estimated effort: 3–7 days depending on choice, plus E2E re-validation.

### Recommended execution order

1. **Diagnostic first** — decide based on frequency data whether this is a cosmetic
   issue (fire Fix A only, move on) or a structural one (C needed).
2. **Fix A as cover** — land the UX patch regardless, because even if the eventual fix
   is C, that'll take a week and meanwhile every affected user sees the apology banner.
3. **Fix B or C** after diagnostic.

---

## Out of scope / constraints

- **Do not touch** the three P1 safety nets (`_map_synthesizer` widening, the
  empty-response branches in `_embed_chart_images`, the worker `_build_degraded_reply`).
  They're load-bearing for a different failure mode.
- **Do not remove** the `error_code` fallback in `_embed_chart_images`. If you replace
  it with something else, keep the contract: `LlmResponse` must always end up with
  populated `content.parts[0].text` so `output_key` writes `final_report`.
- **Don't downgrade `THINKING_CONFIG`** — the `HIGH` thinking level is not a likely
  contributor to `MALFORMED_FUNCTION_CALL` and downgrading it would regress report
  quality.
- **Don't switch models** without an eval run — `gemini-3.1-pro-preview` is the project
  standard and is coordinated with a Vertex-AI `location='global'` override in
  `specialists.py` that older models don't need.
- **Keep the 4-suite test gate green** on every change: `npm run test`, `cd functions &&
npm test`, `npm run test:rules`, `cd agent && PYTHONPATH=. .venv/bin/pytest tests/
  --ignore=tests/test_router_evals.py`.

---

## Critical files

Read-only references:

- [`agent/superextra_agent/agent.py`](../agent/superextra_agent/agent.py) — synth wiring,
  `_inject_code_execution`, `_embed_chart_images`, `_build_fallback_report`.
- [`agent/superextra_agent/specialists.py:95-113`](../agent/superextra_agent/specialists.py)
  — MODEL constants and THINKING_CONFIG.
- [`agent/superextra_agent/firestore_events.py:289-334`](../agent/superextra_agent/firestore_events.py)
  — `_map_synthesizer`, the downstream mapper.
- [`agent/worker_main.py`](../agent/worker_main.py) — event loop, `_build_degraded_reply`,
  `_extract_sources_from_state_delta`.

Likely modified:

- [`agent/superextra_agent/instructions/synthesizer.md`](../agent/superextra_agent/instructions/synthesizer.md)
  — chart instructions (Fix B) or chart removal (Fix C).
- [`agent/superextra_agent/agent.py`](../agent/superextra_agent/agent.py) — disclaimer
  text (Fix A), fallback behavior (Fix B), or synth structure (Fix C).
- [`agent/tests/test_embed_chart_images.py`](../agent/tests/test_embed_chart_images.py)
  — test updates matching behavior changes.

---

## Acceptance criteria

Ready to close the investigation when all of:

1. Frequency data captured and archived (30-day percentage, trend, prompt-shape
   correlation if any).
2. Root-cause mechanism identified to the level of "tool-call envelope" vs. "emitted
   code" vs. "input-size / encoding".
3. A chosen fix landed, with tests, and live E2E re-run demonstrates reduced
   `MALFORMED_FUNCTION_CALL` rate OR a softened user-facing failure mode (Fix A).
4. `docs/pipeline-decoupling-execution-log.md` triage section updated with what changed.
