<script lang="ts">
	import type { TimelineEvent } from '$lib/chat-types';
	import ProgressEventRow from './ProgressEventRow.svelte';
	import ProgressWrapper from './ProgressWrapper.svelte';
	import TypewriterText from './TypewriterText.svelte';

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
</script>

<div class="flex flex-col gap-3">
	<div class="text-[13px] text-black/55 dark:text-white/55">
		Working for {formatDuration(startedAtMs ? now - startedAtMs : 0)}
	</div>

	<ProgressWrapper>
		{#each events as ev (ev.id)}
			{#if ev.kind === 'note'}
				<p class="text-[15px] leading-relaxed text-black/82 dark:text-white/82">
					<TypewriterText text={ev.text} charsPerFrame={3}>
						{#snippet children(text)}
							{text}
						{/snippet}
					</TypewriterText>
				</p>
			{:else if ev.kind === 'detail'}
				<ProgressEventRow label={ev.family} detail={ev.text} />
			{/if}
		{/each}
	</ProgressWrapper>
</div>
