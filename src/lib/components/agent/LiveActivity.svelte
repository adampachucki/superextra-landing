<script lang="ts">
	import type { TimelineEvent } from '$lib/chat-types';
	import ProgressEventRow from './ProgressEventRow.svelte';
	import ProgressWrapper from './ProgressWrapper.svelte';

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

	// Step count = detail rows only. Notes are narrative, not "steps".
	let stepCount = $derived(events.filter((e) => e.kind === 'detail').length);
	// Always streaming while LiveActivity is mounted — `chatState.loading`
	// is the gate at the parent level.
	let isStreaming = true;
</script>

<div class="flex flex-col gap-3">
	<div class="text-[13px] text-black/55 dark:text-white/55">
		Working for {formatDuration(startedAtMs ? now - startedAtMs : 0)}
	</div>

	<ProgressWrapper {stepCount} {isStreaming} shouldMinimize={false}>
		{#each events as ev (ev.id)}
			{#if ev.kind === 'note'}
				<p class="text-[15px] leading-relaxed text-black/82 dark:text-white/82">
					{ev.text}
				</p>
			{:else if ev.kind === 'detail'}
				<ProgressEventRow
					label={ev.family}
					detail={ev.text}
					status="done"
					showConnector={false}
				/>
			{:else if ev.kind === 'drafting'}
				<ProgressEventRow label={ev.text} status="running" showConnector={false} />
			{/if}
		{/each}
	</ProgressWrapper>
</div>
