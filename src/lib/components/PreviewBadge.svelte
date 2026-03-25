<script lang="ts">
	let { tooltipBelow = false }: { tooltipBelow?: boolean } = $props();
	let showTooltip = $state(false);
</script>

<div class="relative">
	<button
		onmouseenter={() => (showTooltip = true)}
		onmouseleave={() => (showTooltip = false)}
		onfocus={() => (showTooltip = true)}
		onblur={() => (showTooltip = false)}
		class="flex items-center gap-1.5 rounded-full border-[0.5px] border-black/10 dark:border-white/10 bg-white dark:bg-cream-100 py-1.5 pr-2.5 pl-3 text-xs font-medium text-black/60 dark:text-white/60 transition-colors hover:text-black dark:hover:text-white"
	>
		<span class="inline-flex h-1.5 w-1.5 rounded-full bg-amber-500 preview-dot"></span>
		Preview
	</button>

	{#if showTooltip}
		<div
			class="absolute w-56 rounded-xl border-[0.5px] border-black/5 dark:border-white/5 bg-white dark:bg-cream-100 p-3 text-xs leading-relaxed text-black/60 dark:text-white/60 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.08)] {tooltipBelow ? 'top-full right-0 mt-2' : 'bottom-full left-0 mb-2'}"
		>
			This page is in demo mode. Content and features shown here are for preview purposes and may change before launch.
		</div>
	{/if}
</div>

<style>
	.preview-dot {
		animation: glow 2s ease-in-out infinite;
	}

	@keyframes glow {
		0%, 100% {
			background-color: var(--color-amber-300);
		}
		50% {
			background-color: var(--color-amber-500);
		}
	}
</style>
