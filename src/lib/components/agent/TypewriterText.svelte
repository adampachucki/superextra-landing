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

{#if enabled}
	{@render children(displayed)}
{:else}
	{@render children(text)}
{/if}
