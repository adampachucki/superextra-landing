# Agent Routing Cleanup Status

**Date:** 2026-04-29

## Done

- Removed the dead gap-researcher `"Agent did not produce output."` check.
- Removed the test that only existed for that impossible state.
- Kept the old `specialist_briefs` parser branch only for historical eval files, with a clearer comment.
- Updated the rearchitecture plan doc so it no longer says this is pre-execution or that the B-with-floors eval is a required gate.
- Kept sub-agent descriptions. They are not the duplicate. The duplicate was the old prompt-side specialist list. Descriptions are still used by ADK/AgentTool metadata.

## Validation

- Agent tests: `168 passed, 17 skipped`
- Frontend/unit tests: `59 passed`
- Functions tests: `63 passed`
- Lint: passes, existing warnings only
- Cloudpickle smoke: passes
- `git diff --check`: passes
- Firestore rules test still blocked because Java is missing locally.

## Remaining

- Staging/full-plugin smoke.
- Chrome UI progress verification.
- Agent Engine deploy.
