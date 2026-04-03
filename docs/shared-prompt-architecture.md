# Shared Prompt Architecture: /agent and /chat

Two sister pages with identical prompt mechanics but completely different visual styling.

## Approach: Shared Logic Module + Separate Presentation

Extract all prompt behavior into a reactive `.svelte.ts` module (following the existing `formState` / `theme` singleton pattern). Each page imports the shared logic and renders its own independent UI.

## Structure

```
src/
  lib/
    prompt-state.svelte.ts    # shared logic — state, submission, streaming, history
  routes/
    agent/
      +page.svelte            # agent-specific UI, imports prompt-state
    chat/
      +page.svelte            # chat-specific UI, imports prompt-state
```

## Shared Logic Module (`prompt-state.svelte.ts`)

Encapsulates:

- Message state (input text, conversation history)
- Submission handler (send, stream response)
- Loading/streaming state
- Clear/reset actions

```ts
export function createPromptState() {
	let message = $state('');
	let loading = $state(false);
	let history = $state<Message[]>([]);

	async function submit() {
		/* shared send/stream logic */
	}
	function clear() {
		/* ... */
	}

	return {
		/* expose reactive state + actions */
	};
}
```

Each page calls `createPromptState()` to get its own instance, or a shared singleton can be exported if state should persist across navigation.

## Page Components

Each page owns 100% of its markup and styling. No shared visual components, no variant props, no conditional class logic.

- `/agent/+page.svelte` — agent-branded styling, layout, animations
- `/chat/+page.svelte` — chat-branded styling, layout, animations

Both import `createPromptState()` and wire the same reactive state/actions to their own inputs, buttons, and message displays.

## Why This Pattern

| Alternative                          | Problem                                                               |
| ------------------------------------ | --------------------------------------------------------------------- |
| Single component with `variant` prop | Couples two unrelated designs; becomes a mess of conditionals         |
| `{#snippet}` render props            | Awkward when everything visual differs — entire UI passed as snippets |
| Duplicated logic in each page        | Logic drift, bugs fixed in one place but not the other                |
| **Shared `.svelte.ts` module**       | Clean separation. Logic stays DRY. Each page has full visual control. |

## Precedent in This Codebase

- `form-state.svelte.ts` — singleton managing access form modal state
- `theme.svelte.ts` — singleton managing dark/light mode

Same pattern, applied to prompt interaction.
