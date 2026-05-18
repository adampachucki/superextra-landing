# Vertex Tool Combination Flag Investigation

Date: 2026-05-18

## Summary

`include_server_side_tool_invocations` failed because the current Vertex AI path
does not support it in the installed Google GenAI Python SDK. The failure occurs
before any HTTP request reaches Vertex.

This does not mean native Google Search and native URL Context can never produce
grounding on Vertex. It means the specific flag needed for exposed server-side
tool invocation history and built-in/custom tool context circulation is not
available through the Vertex AI / Agent Engine SDK path we use.

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

## What This Means

Native Google Search grounding itself is separate. When grounding succeeds,
responses can include `groundingMetadata` with web queries, web results, and
citations.

Native URL Context is also separate. It can retrieve content from supplied URLs,
and its response includes URL retrieval metadata that must be checked.

The blocked flag is specifically about exposing server-side built-in tool calls
and responses in the content history so they can be circulated alongside custom
function calls.

That matters for Superextra because the desired single-specialist loop would be:

1. native Google Search discovers sources;
2. the same agent sees/circulates those source details;
3. the same agent calls a custom reader/read-queue function;
4. the final answer can be audited against both search grounding and page reads.

Our current Vertex path cannot rely on that flag to make this loop clean.

## Conclusion

Do not make native Google Search + native URL Context + custom function tools the
main specialist research loop yet. Keep the explicit custom loop:

- `search_public_web` for source discovery and snippets;
- `read_discovered_sources` for explicit page reads through Jina;
- source funnel logging for observability.

The practical next step is to improve the custom discovery tool and specialist
workflow, rather than wait for Vertex tool-combination support to catch up.
