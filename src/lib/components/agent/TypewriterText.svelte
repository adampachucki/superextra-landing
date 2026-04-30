<script lang="ts">
	import type { Snippet } from 'svelte';
	import { createTypewriter } from '$lib/typewriter';

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

	$effect(() => {
		if (!enabled || !text) {
			displayed = text;
			return;
		}

		const typer = createTypewriter({
			charsPerFrame,
			onUpdate: (value) => {
				displayed = value;
			},
			onDone: () => {
				displayed = text;
				onDone?.();
			}
		});

		displayed = '';
		typer.setTarget(text);
		return () => typer.stop();
	});
</script>

{@render children(enabled ? displayed : text)}
