<script lang="ts">
	import type { TimelineEvent, TurnCounts } from '$lib/firestore-stream';

	let {
		events,
		startedAtMs
	}: {
		events: TimelineEvent[];
		startedAtMs: number | null;
	} = $props();

	let now = $state(Date.now());

	$effect(() => {
		now = Date.now();
		const timer = setInterval(() => {
			now = Date.now();
		}, 1000);
		return () => clearInterval(timer);
	});

	function formatDuration(ms: number): string {
		const totalSeconds = Math.max(0, Math.floor(ms / 1000));
		const minutes = Math.floor(totalSeconds / 60);
		const seconds = totalSeconds % 60;
		if (minutes > 0) return `${minutes}m ${seconds}s`;
		return `${seconds}s`;
	}

	function formatCounts(counts: TurnCounts): string {
		const parts: string[] = [];
		if (counts.webQueries > 0)
			parts.push(`Searched ${counts.webQueries} quer${counts.webQueries === 1 ? 'y' : 'ies'}`);
		if (counts.sources > 0)
			parts.push(`Opened ${counts.sources} source${counts.sources === 1 ? '' : 's'}`);
		if (counts.venues > 0)
			parts.push(`Checked ${counts.venues} venue${counts.venues === 1 ? '' : 's'}`);
		if (counts.platforms > 0)
			parts.push(`Reviewed ${counts.platforms} platform${counts.platforms === 1 ? '' : 's'}`);
		return parts.join(', ') || 'Working';
	}

	const FAMILY_ORDER = [
		'Searching the web',
		'Google Maps',
		'TripAdvisor',
		'Google reviews',
		'Public sources',
		'Warnings'
	] as const;

	let notes = $derived(
		events.filter((event) => event.kind === 'note' || event.kind === 'drafting')
	);
	let detailGroups = $derived(
		FAMILY_ORDER.map((family) => ({
			family,
			rows: events.filter((event) => event.kind === 'detail' && event.family === family)
		})).filter((group) => group.rows.length > 0)
	);
</script>

<div class="flex flex-col gap-5">
	<div
		class="border-b border-black/6 pb-3 text-[14px] text-black/55 dark:border-white/10 dark:text-white/55"
	>
		Working for {formatDuration(startedAtMs ? now - startedAtMs : 0)}
	</div>

	{#each notes as event (event.id)}
		<div class="flex flex-col gap-1">
			<div class="text-[15px] leading-relaxed text-black/85 dark:text-white/85">{event.text}</div>
			{#if event.kind === 'note'}
				<div class="text-[13px] text-black/38 dark:text-white/38">
					{formatCounts(event.counts)}
				</div>
			{/if}
		</div>
	{/each}

	{#each detailGroups as group (group.family)}
		<div class="flex flex-col gap-1.5">
			<div class="text-[13px] text-black/38 dark:text-white/38">{group.family}</div>
			{#each group.rows as row (row.id)}
				<div class="pl-1 text-[13px] leading-snug text-black/62 dark:text-white/62">
					{row.text}
				</div>
			{/each}
		</div>
	{/each}
</div>
