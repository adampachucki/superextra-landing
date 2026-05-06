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
	// Reuse one soft-reveal controller across text changes. `setTarget`
	// preserves position when the new target extends the displayed prefix, so
	// growing thought buffers keep revealing from where they left off.
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
	<div class="soft-reveal">
		{@render children(displayed)}
	</div>
{:else}
	{@render children(text)}
{/if}

<style>
	.soft-reveal {
		animation: softReveal 180ms ease-out both;
	}

	@keyframes softReveal {
		from {
			opacity: 0.72;
			transform: translateY(1px);
			filter: blur(0.4px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
			filter: blur(0);
		}
	}
</style>
