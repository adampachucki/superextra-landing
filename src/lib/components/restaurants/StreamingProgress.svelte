<script lang="ts">
	import type { ActivityItem, ActivityCategory } from '$lib/chat-state.svelte';

	let { activities, loading = false }: { activities: ActivityItem[]; loading?: boolean } = $props();

	// Derived groupings
	let dataItems = $derived(activities.filter((a) => a.category === 'data'));
	let searchItems = $derived(activities.filter((a) => a.category === 'search'));
	let readItems = $derived(activities.filter((a) => a.category === 'read'));
	let analyzeItems = $derived(activities.filter((a) => a.category === 'analyze'));

	// --- Typewriter for read item labels ---
	let readDisplay: Record<string, string> = $state({});
	let readTargets: Record<string, string> = {};
	let readRafs: Record<string, number> = {};

	function drainRead(id: string) {
		const target = readTargets[id];
		if (!target) return;
		const current = readDisplay[id] || '';
		if (current.length < target.length) {
			readDisplay[id] = target.slice(0, current.length + 2);
			readRafs[id] = requestAnimationFrame(() => drainRead(id));
		} else {
			delete readRafs[id];
		}
	}

	$effect(() => {
		for (const item of readItems) {
			const fullLabel = item.detail ? `${item.label} — ${item.detail}` : item.label;
			if (readTargets[item.id] !== fullLabel) {
				readTargets[item.id] = fullLabel;
				readDisplay[item.id] = '';
				if (readRafs[item.id]) cancelAnimationFrame(readRafs[item.id]);
				readRafs[item.id] = requestAnimationFrame(() => drainRead(item.id));
			}
		}
		return () => {
			for (const raf of Object.values(readRafs)) cancelAnimationFrame(raf);
		};
	});

	// --- Typewriter for data item labels (restaurant names + ratings) ---
	let dataDisplay: Record<string, string> = $state({});
	let dataTargets: Record<string, string> = {};
	let dataRafs: Record<string, number> = {};

	function drainData(id: string) {
		const target = dataTargets[id];
		if (!target) return;
		const current = dataDisplay[id] || '';
		if (current.length < target.length) {
			dataDisplay[id] = target.slice(0, current.length + 2);
			dataRafs[id] = requestAnimationFrame(() => drainData(id));
		} else {
			delete dataRafs[id];
		}
	}

	$effect(() => {
		for (const item of dataItems) {
			const fullLabel = item.detail ? `${item.label} — ${item.detail}` : item.label;
			if (dataTargets[item.id] !== fullLabel) {
				dataTargets[item.id] = fullLabel;
				dataDisplay[item.id] = '';
				if (dataRafs[item.id]) cancelAnimationFrame(dataRafs[item.id]);
				dataRafs[item.id] = requestAnimationFrame(() => drainData(item.id));
			}
		}
		return () => {
			for (const raf of Object.values(dataRafs)) cancelAnimationFrame(raf);
		};
	});

	// --- Sentence-rotation typewriter for analyze excerpts ---
	let excerptDisplay: Record<string, string> = $state({});
	let excerptTargets: Record<string, string> = {};
	let excerptRafs: Record<string, number> = {};

	function drainExcerpt(id: string) {
		const target = excerptTargets[id];
		if (!target) return;
		const current = excerptDisplay[id] || '';
		if (current.length < target.length) {
			excerptDisplay[id] = target.slice(0, current.length + 2);
			excerptRafs[id] = requestAnimationFrame(() => drainExcerpt(id));
		} else {
			delete excerptRafs[id];
		}
	}

	$effect(() => {
		for (const item of analyzeItems) {
			if (item.detail && excerptTargets[item.id] !== item.detail) {
				excerptTargets[item.id] = item.detail;
				excerptDisplay[item.id] = '';
				if (excerptRafs[item.id]) cancelAnimationFrame(excerptRafs[item.id]);
				excerptRafs[item.id] = requestAnimationFrame(() => drainExcerpt(item.id));
			}
		}
		return () => {
			for (const raf of Object.values(excerptRafs)) cancelAnimationFrame(raf);
		};
	});

	const SECTION_CONFIG: {
		key: ActivityCategory;
		label: string;
		items: () => ActivityItem[];
	}[] = [
		{ key: 'data', label: 'Gathering data', items: () => dataItems },
		{ key: 'search', label: 'Searching', items: () => searchItems },
		{ key: 'read', label: 'Reading', items: () => readItems },
		{ key: 'analyze', label: 'Analyzing', items: () => analyzeItems }
	];
</script>

<div class="flex flex-col gap-3">
	{#each SECTION_CONFIG as section (section.key)}
		{@const items = section.items()}
		{#if items.length > 0}
			<div class="flex flex-col gap-0.5">
				<span class="text-[13px] text-black/30 dark:text-white/30">
					{section.label}...
				</span>
				{#each items as item (item.id)}
					<div class="activity-appear flex items-start gap-2 text-[13px] leading-snug">
						<!-- Status dot -->
						{#if item.status === 'complete'}
							<span class="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500"></span>
						{:else if item.status === 'running'}
							<span class="stage-pulse mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full bg-amber-300"
							></span>
						{:else}
							<span class="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full bg-black/15 dark:bg-white/15"
							></span>
						{/if}

						<!-- Content varies by category -->
						{#if section.key === 'read'}
							<span
								class={[
									item.status === 'complete'
										? 'text-black/40 dark:text-white/40'
										: 'text-black/60 dark:text-white/60'
								]}
							>
								{readDisplay[item.id] ||
									item.label}{#if readDisplay[item.id] && readDisplay[item.id].length < (readTargets[item.id] || '').length}<span
										class="cursor-blink">|</span
									>{/if}
							</span>
						{:else if section.key === 'analyze'}
							<div class="flex flex-col">
								<span
									class={[
										item.status === 'complete'
											? 'text-black/40 dark:text-white/40'
											: 'text-black/60 dark:text-white/60'
									]}
								>
									{item.label}
								</span>
								{#if excerptDisplay[item.id]}
									<span class="text-[12px] text-black/30 dark:text-white/30">
										{excerptDisplay[
											item.id
										]}{#if excerptDisplay[item.id].length < (excerptTargets[item.id] || '').length}<span
												class="cursor-blink">|</span
											>{/if}
									</span>
								{/if}
							</div>
						{:else if section.key === 'search'}
							<span
								class={[
									item.status === 'complete'
										? 'text-black/40 dark:text-white/40'
										: 'text-black/60 dark:text-white/60'
								]}
							>
								"{item.label}"
							</span>
						{:else}
							<span
								class={[
									item.status === 'complete'
										? 'text-black/40 dark:text-white/40'
										: 'text-black/60 dark:text-white/60'
								]}
							>
								{dataDisplay[item.id] ||
									item.label}{#if dataDisplay[item.id] && dataDisplay[item.id].length < (dataTargets[item.id] || '').length}<span
										class="cursor-blink">|</span
									>{/if}
							</span>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	{/each}

	{#if loading}
		<div class="flex items-center gap-2">
			<span class="loading-dots flex gap-1">
				<span class="h-1 w-1 rounded-full bg-[#6ee7b3]"></span>
				<span class="h-1 w-1 rounded-full bg-[#a78bfa]"></span>
				<span class="h-1 w-1 rounded-full bg-[#f472b6]"></span>
			</span>
			<span class="shimmer-text text-[13px]">Researching...</span>
		</div>
	{/if}
</div>

<style>
	.activity-appear {
		animation: activityIn 0.2s ease-out both;
	}

	@keyframes activityIn {
		from {
			opacity: 0;
			transform: translateY(4px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.stage-pulse {
		animation: stagePulse 1.5s ease-in-out infinite;
	}

	@keyframes stagePulse {
		0%,
		100% {
			opacity: 0.4;
		}
		50% {
			opacity: 1;
		}
	}

	.cursor-blink {
		animation: cursorBlink 1s step-end infinite;
		font-weight: 300;
		opacity: 0.6;
	}

	@keyframes cursorBlink {
		0%,
		100% {
			opacity: 0.6;
		}
		50% {
			opacity: 0;
		}
	}

	.shimmer-text {
		color: transparent;
		background: linear-gradient(
			90deg,
			rgba(0, 0, 0, 0.35) 0%,
			rgba(0, 0, 0, 0.5) 40%,
			rgba(0, 0, 0, 0.35) 80%
		);
		background-size: 200% 100%;
		background-clip: text;
		-webkit-background-clip: text;
		animation: shimmer 5s ease-in-out infinite;
	}

	:global(.dark) .shimmer-text {
		background: linear-gradient(
			90deg,
			rgba(255, 255, 255, 0.35) 0%,
			rgba(255, 255, 255, 0.5) 40%,
			rgba(255, 255, 255, 0.35) 80%
		);
		background-size: 200% 100%;
		background-clip: text;
		-webkit-background-clip: text;
	}

	@keyframes shimmer {
		0% {
			background-position: 200% 0;
		}
		50% {
			background-position: -200% 0;
		}
		100% {
			background-position: -200% 0;
		}
	}

	.loading-dots span {
		animation: dotWave 1.4s ease-in-out infinite;
	}
	.loading-dots span:nth-child(2) {
		animation-delay: 0.15s;
	}
	.loading-dots span:nth-child(3) {
		animation-delay: 0.3s;
	}

	@keyframes dotWave {
		0%,
		80%,
		100% {
			opacity: 0.4;
			transform: translateY(0);
		}
		40% {
			opacity: 1;
			transform: translateY(-3px);
		}
	}
</style>
