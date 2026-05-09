# `narrate()` Tool Retirement

**Date:** 2026-05-08
**Status:** Retired in `d5ac1a1`

`narrate(text)` was removed because it duplicated Gemini's native thought summaries in the activity timeline. Both appeared as adjacent progress prose, with the same visual weight, and `narrate()` had no structural role in step titles, grouping, terminal state, or source handling.

Progress is now carried by:

- `kind: 'thought'` rows from Gemini `include_thoughts=True` summaries.
- `kind: 'detail'` rows from typed tool-call/result hooks.

Removed surface area:

- `agent/superextra_agent/narrate_tool.py`
- `narrate` registrations in `agent/superextra_agent/agent.py`
- `narrate` mapping to `kind: 'note'` in `agent/superextra_agent/firestore_events.py`
- Narrate-first instruction blocks in the context enricher and research lead prompts
- `kind: 'note'` from the frontend `TimelineEvent` union and activity renderer
- Narrate-specific Python tests and note fixtures in frontend tests

Verification performed before deploy:

- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v`
- `npm run lint && npm run check && npm run test`
- `cd functions && npm test`
- `npm run test:rules`
- `rg -n 'narrate|narration' agent/superextra_agent agent/tests src functions` returned no hits.

Deploy verification:

- GitHub Actions deploy for `d5ac1a1` succeeded.
- Agent Engine staleness check reported runtime SHA `d5ac1a1`.
- Public hosting returned `200` for `landing.superextra.ai`, `agent.superextra.ai`, and `agent.superextra.ai/chat`.
- `landing.superextra.ai/agent` returned the expected `301` to `agent.superextra.ai`.
- Deployed agent JS assets contained no stale `narrate` or `narration` strings and no live note renderer.

Backward compatibility: old Firestore event documents expire after 3 days. During that window, the frontend may still encounter legacy note payloads from completed turns created before this deploy; they remain display-only progress text and are not restored as a live event type.
