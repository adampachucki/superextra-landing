<script lang="ts">
	import { SvelteMap } from 'svelte/reactivity';
	import type { TimelineEvent } from '$lib/chat-types';
	import { createTypewriter, type Typewriter } from '$lib/typewriter';
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

	// Per-note drip state. The typewriter map lives outside $state because
	// the instances are objects with internal RAF state we don't want
	// Svelte to deep-track. The displayed text is reactive.
	let displayed = $state<Record<string, string>>({});
	const typers = new SvelteMap<string, Typewriter>();

	$effect(() => {
		for (const ev of events) {
			if (ev.kind !== 'note') continue;
			if (typers.has(ev.id)) continue;
			const id = ev.id;
			const typer = createTypewriter({
				charsPerFrame: 4,
				onUpdate: (current) => {
					displayed[id] = current;
				}
			});
			typers.set(id, typer);
			displayed[id] = '';
			typer.setTarget(ev.text);
		}
		return () => {
			for (const t of typers.values()) t.stop();
		};
	});

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
					{displayed[ev.id] ?? ''}
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
