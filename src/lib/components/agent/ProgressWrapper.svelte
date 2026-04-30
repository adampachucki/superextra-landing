<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		stepCount,
		isStreaming,
		shouldMinimize,
		summaryLabel,
		children
	}: {
		stepCount: number;
		isStreaming: boolean;
		shouldMinimize: boolean;
		summaryLabel?: string;
		children: Snippet;
	} = $props();

	let userToggled = $state(false);
	let userOpenChoice = $state(true);
	let everMinimized = $state(false);

	$effect(() => {
		if (shouldMinimize) everMinimized = true;
	});

	let isOpen = $derived(
		userToggled ? userOpenChoice : !shouldMinimize && !everMinimized
	);

	let label = $derived(
		isStreaming
			? 'Working'
			: (summaryLabel ?? `Completed in ${stepCount} step${stepCount === 1 ? '' : 's'}`)
	);
</script>

<div
	class="rounded-2xl border border-black/8 bg-white/40 px-4 py-3 dark:border-white/10 dark:bg-white/[0.02]"
>
	<button
		type="button"
		onclick={() => {
			userOpenChoice = !isOpen;
			userToggled = true;
		}}
		class="flex w-full cursor-pointer items-center justify-between gap-2 text-[13px] text-black/55 transition-colors hover:text-black/80 dark:text-white/55 dark:hover:text-white/80"
	>
		<span class="flex items-baseline gap-1">
			<span class="truncate">{label}</span>
			{#if isStreaming}
				<span class="ml-1 inline-flex shrink-0 items-baseline gap-[2px]">
					<span class="dot dot-1"></span>
					<span class="dot dot-2"></span>
					<span class="dot dot-3"></span>
				</span>
			{/if}
		</span>
		<svg
			width="11"
			height="11"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="2.4"
			stroke-linecap="round"
			stroke-linejoin="round"
			class="shrink-0 transition-transform duration-200"
			class:rotate--90={!isOpen}
			aria-hidden="true"
		>
			<polyline points="6 9 12 15 18 9"></polyline>
		</svg>
	</button>

	{#if isOpen}
		<div class="mt-3 flex flex-col gap-3">
			{@render children()}
		</div>
	{/if}
</div>

<style>
	.dot {
		display: inline-block;
		width: 3px;
		height: 3px;
		border-radius: 9999px;
		background-color: currentColor;
		opacity: 0.45;
		animation: dot-bounce 1.2s infinite ease-in-out;
	}
	.dot-1 {
		animation-delay: 0s;
	}
	.dot-2 {
		animation-delay: 0.18s;
	}
	.dot-3 {
		animation-delay: 0.36s;
	}
	@keyframes dot-bounce {
		0%,
		60%,
		100% {
			transform: translateY(0);
			opacity: 0.35;
		}
		30% {
			transform: translateY(-2px);
			opacity: 0.85;
		}
	}
	.rotate--90 {
		transform: rotate(-90deg);
	}
</style>
