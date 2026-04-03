<script lang="ts">
	import type { ActivityItem, ActivityCategory } from '$lib/chat-state.svelte';

	let { activities, loading = false }: { activities: ActivityItem[]; loading?: boolean } = $props();

	// Derived groupings
	let dataItems = $derived(activities.filter((a) => a.category === 'data'));
	let searchItems = $derived(activities.filter((a) => a.category === 'search'));
	let readItems = $derived(activities.filter((a) => a.category === 'read'));
	let analyzeItems = $derived(activities.filter((a) => a.category === 'analyze'));

	// Filter out completed synthesizer from analyze items (rendered as its own header)
	let analyzeItemsVisible = $derived(
		analyzeItems.filter((a) => !(a.id === 'analyze-synthesizer' && a.status === 'complete'))
	);
	let researchComplete = $derived(
		analyzeItems.some((a) => a.id === 'analyze-synthesizer' && a.status === 'complete')
	);

	// Section done state
	function isSectionDone(key: ActivityCategory): boolean {
		const items =
			key === 'data'
				? dataItems
				: key === 'search'
					? searchItems
					: key === 'read'
						? readItems
						: analyzeItemsVisible;
		if (items.length === 0) return false;
		if (!items.every((a) => a.status === 'complete')) return false;
		// Data section: don't show Done until data-check is complete (when it exists)
		if (key === 'data') {
			const hasCheck = items.some((a) => a.id === 'data-check');
			if (hasCheck && !items.some((a) => a.id === 'data-check' && a.status === 'complete'))
				return false;
		}
		return true;
	}

	// --- Animated dots for section headers (type then backspace) ---
	let dotPhase = $state(0);

	$effect(() => {
		const interval = setInterval(() => {
			dotPhase = (dotPhase + 1) % 6;
		}, 350);
		return () => clearInterval(interval);
	});

	function getDots(phase: number): string {
		const count = phase <= 3 ? phase : 6 - phase;
		return '.'.repeat(count);
	}

	// --- Typewriter for data item details (place names cycling below labels) ---
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
			if (item.detail && dataTargets[item.id] !== item.detail) {
				dataTargets[item.id] = item.detail;
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

	// --- Reading section: staggered reveal + typewriter ---
	let readRevealedCount = $state(0);
	let visibleReadItems = $derived(readItems.slice(0, readRevealedCount));
	let readDone = $derived(
		readItems.length > 0 &&
			readItems.every((a) => a.status === 'complete') &&
			readRevealedCount >= readItems.length
	);

	// Stagger timer: reveal one item every 200ms
	$effect(() => {
		if (readRevealedCount >= readItems.length) return;
		const interval = setInterval(() => {
			readRevealedCount++;
			if (readRevealedCount >= readItems.length) clearInterval(interval);
		}, 200);
		return () => clearInterval(interval);
	});

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

	// Typewriter only runs for visible (revealed) items
	$effect(() => {
		for (const item of visibleReadItems) {
			const fullLabel = formatReadUrl(item.url || item.label);
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

	function formatReadUrl(url: string): string {
		try {
			const u = new URL(url);
			const path = u.hostname + u.pathname.replace(/\/$/, '');
			return path.length > 60 ? path.slice(0, 57) + '...' : path;
		} catch {
			return url.length > 60 ? url.slice(0, 57) + '...' : url;
		}
	}

	// Sections for the generic loop (read excluded — rendered separately)
	const SECTION_CONFIG: {
		key: ActivityCategory;
		label: string;
		items: () => ActivityItem[];
	}[] = [
		{ key: 'data', label: 'Gathering data', items: () => dataItems },
		{ key: 'search', label: 'Searching', items: () => searchItems },
		{ key: 'analyze', label: 'Analyzing', items: () => analyzeItemsVisible }
	];
</script>

<div class="flex flex-col gap-3">
	{#each SECTION_CONFIG as section (section.key)}
		{@const items = section.items()}
		{#if items.length > 0}
			{@const done = isSectionDone(section.key)}
			<div class="section-appear flex flex-col gap-0.5">
				<span class="text-[13px] text-black/30 dark:text-white/30">
					{#if done}
						{section.label} – Done
					{:else}
						{section.label}{getDots(dotPhase)}
					{/if}
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
						{#if section.key === 'data' || section.key === 'analyze'}
							<!-- Data + Analyze: label with detail below in smaller font -->
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
								{#if section.key === 'data' && dataDisplay[item.id]}
									<span class="text-[12px] text-black/30 dark:text-white/30">
										{dataDisplay[
											item.id
										]}{#if dataDisplay[item.id].length < (dataTargets[item.id] || '').length}<span
												class="cursor-blink">|</span
											>{/if}
									</span>
								{:else if section.key === 'analyze' && excerptDisplay[item.id]}
									<span class="text-[12px] text-black/30 dark:text-white/30">
										{excerptDisplay[
											item.id
										]}{#if excerptDisplay[item.id].length < (excerptTargets[item.id] || '').length}<span
												class="cursor-blink">|</span
											>{/if}
									</span>
								{/if}
							</div>
						{:else if section.key === 'search' && item.id === 'search-web'}
							<!-- Aggregate search: label + specialist detail below -->
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
								{#if item.detail}
									<span class="text-[12px] text-black/30 dark:text-white/30">
										{item.detail}
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
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	{/each}

	<!-- Reading section: counter + staggered children -->
	{#if readItems.length > 0}
		<div class="section-appear flex flex-col gap-0.5">
			<span class="text-[13px] text-black/30 dark:text-white/30">
				{readDone ? 'Reading – Done' : `Reading${getDots(dotPhase)}`}
			</span>

			<!-- Counter with dot -->
			<div class="activity-appear flex items-start gap-2 text-[13px] leading-snug">
				{#if readDone}
					<span class="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500"></span>
				{:else}
					<span class="stage-pulse mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full bg-amber-300"></span>
				{/if}
				<span
					class={readDone ? 'text-black/40 dark:text-white/40' : 'text-black/60 dark:text-white/60'}
				>
					Sources: {readItems.length}
				</span>
			</div>

			<!-- Staggered children: indented, no dots, smaller font -->
			{#each readDone ? visibleReadItems.slice(0, 5) : visibleReadItems as item (item.id)}
				<div class="activity-appear pl-5 text-[12px] leading-snug text-black/30 dark:text-white/30">
					{readDisplay[item.id] ||
						formatReadUrl(
							item.url || item.label
						)}{#if readDisplay[item.id] && readDisplay[item.id].length < (readTargets[item.id] || '').length}<span
							class="cursor-blink">|</span
						>{/if}
				</div>
			{/each}

			<!-- Collapse overflow when done -->
			{#if readDone && readItems.length > 5}
				<div class="pl-5 text-[12px] leading-snug text-black/20 dark:text-white/20">
					and {readItems.length - 5} more
				</div>
			{/if}
		</div>
	{/if}

	{#if researchComplete}
		<span class="activity-appear text-[13px] text-black/30 dark:text-white/30">
			Research complete!
		</span>
	{/if}

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
	.section-appear {
		animation: sectionIn 0.3s ease-out both;
	}

	@keyframes sectionIn {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

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
