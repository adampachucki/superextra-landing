<script lang="ts">
	let showTooltip = $state(false);
</script>

<div class="fixed bottom-5 left-5 z-50">
	<button
		onmouseenter={() => (showTooltip = true)}
		onmouseleave={() => (showTooltip = false)}
		onfocus={() => (showTooltip = true)}
		onblur={() => (showTooltip = false)}
		class="flex items-center gap-1.5 rounded-full border border-black/10 bg-white/80 py-3 pr-3 pl-4 text-xs font-medium text-black/60 shadow-[0_2px_20px_-4px_rgba(0,0,0,0.06)] backdrop-blur-sm transition-colors hover:text-black/80"
	>
		<span class="relative flex h-1.5 w-1.5">
			<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75"></span>
			<span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-500"></span>
		</span>
		Preview
	</button>

	{#if showTooltip}
		<div
			class="absolute bottom-full left-0 mb-2 w-56 rounded-xl border border-black/5 bg-white p-3 text-xs leading-relaxed text-black/50 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.08)]"
		>
			This page is in demo mode. Content and features shown here are for preview purposes and may change before launch.
		</div>
	{/if}
</div>
