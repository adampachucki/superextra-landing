# Vertex Tool Combination Flag Investigation

Date: 2026-05-18

## Summary

`include_server_side_tool_invocations` is a Gemini Developer API / AI Studio
(`generativelanguage.googleapis.com`) option, not a Vertex AI
(`aiplatform.googleapis.com`) option. When the flag is sent through the GenAI
SDK in Vertex mode, the SDK rejects it before dispatch; when sent directly to
Vertex REST, Vertex rejects it as an unknown `tool_config` field.

This does not block the tool-combination path we tested on Vertex. Gemini 3 on
Vertex accepted built-in tools such as `google_search` and `url_context` with
custom function declarations in the same turn without that flag. The correct
porting behavior is to drop the flag on Vertex, not search for a Vertex
equivalent.

## Local Verification

Installed versions:

- `google-genai`: `1.72.0`
- `google-adk`: `1.28.0`

Schema check:

- `types.ToolConfig` has `include_server_side_tool_invocations`.
- `types.GenerateContentConfig` does not have `include_server_side_tool_invocations`.

SDK conversion check:

```text
mldev conversion: {'includeServerSideToolInvocations': True}
ValueError: include_server_side_tool_invocations parameter is not supported in Vertex AI.
```

The local converter maps the flag for the Gemini Developer API path, but the
Vertex converter raises:

```python
if getv(from_object, ["include_server_side_tool_invocations"]) is not None:
    raise ValueError(
        "include_server_side_tool_invocations parameter is not supported in"
        " Vertex AI."
    )
```

The same rejection still exists in the current upstream `python-genai` source,
with updated wording that the parameter is supported only in Gemini Developer API
mode, not Gemini Enterprise Agent Platform mode.

External cross-check:

- The Gemini API tool-combination docs show
  `include_server_side_tool_invocations=True` in AI Studio / Gemini Developer API
  examples.
- Vercel AI SDK issue `vercel/ai#13911` documents the backend split: AI Studio
  needs the flag for server-side tool invocation parts, while Vertex tool
  combination works without it and rejects the field if it is sent.
- I did not find one official Vertex page that documents the exact
  built-ins-plus-custom-functions/no-flag combination in a single example; the
  official docs cover the pieces separately.

## What This Means

Native Google Search grounding itself is separate. When grounding succeeds,
responses can include `groundingMetadata` with web queries, web results, and
citations.

Native URL Context is also separate. It can retrieve content from supplied URLs,
and its response includes URL retrieval metadata that must be checked.

In the Vertex Gemini 3 path we tested, server-side built-in tool parts and
custom function-call parts were available without setting the flag. The
requirement is that subsequent turns keep the full model `Content` object
intact, including `toolCall`, `toolResponse`, `functionCall`,
`functionResponse`, and thought signatures. Manual history reconstruction is
the risky path.

That matters for Superextra because the desired single-specialist loop would be:

1. native Google Search discovers sources;
2. the same agent sees/circulates those source details;
3. the same agent calls a custom reader/read-queue function;
4. the final answer can be audited against both search grounding and page reads.

Our current Vertex path should not set that flag. It can still run the native
tool-combination loop, but ADK currently drops `candidate.url_context_metadata`
when converting GenAI responses to ADK `LlmResponse`, so per-URL URL Context
read observability remains weaker than the explicit custom read path.

## Conclusion

The earlier conclusion was too pessimistic. Vertex tool combination is viable
without `include_server_side_tool_invocations`.

The practical constraint is observability, not basic support:

- native search + URL Context can run inside the specialist turn;
- `record_research_sources` can capture selected sources cleanly;
- ADK does not currently expose URL Context read metadata in the events we use;
- an explicit custom read step is still the cleaner path when audited
  attempted/read/failed page-read funnels are required.
