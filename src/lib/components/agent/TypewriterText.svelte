<script lang="ts">
	import type { Snippet } from 'svelte';
	import { onDestroy } from 'svelte';
	import { createTypewriter, type TypewriterController } from '$lib/typewriter';

	let {
		text,
		enabled = true,
		charsPerFrame = 4,
		onDone,
		children
	}: {
		text: string;
		enabled?: boolean;
		charsPerFrame?: number;
		onDone?: () => void;
		children: Snippet<[string]>;
	} = $props();

	let displayed = $state('');
	// Reuse a single typewriter across text changes — `setTarget` preserves
	// position when the new target extends the displayed prefix, so growing
	// thought buffers continue typing from where they left off rather than
	// re-typing from char 0.
	let typer: TypewriterController | null = null;

	$effect(() => {
		if (!enabled || !text) {
			typer?.stop();
			typer = null;
			displayed = text;
			return;
		}
		if (!typer) {
			typer = createTypewriter({
				charsPerFrame,
				onUpdate: (value) => {
					displayed = value;
				},
				onDone: () => {
					displayed = text;
					onDone?.();
				}
			});
		}
		typer.setTarget(text);
	});

	onDestroy(() => typer?.stop());
</script>

{@render children(enabled ? displayed : text)}
