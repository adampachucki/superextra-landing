<script lang="ts">
	import { onMount } from 'svelte';
	import LiveActivity from '$lib/components/agent/LiveActivity.svelte';
	import { renderMarkdown } from '$lib/markdown';
	import type { TimelineEvent } from '$lib/chat-types';

	const events: TimelineEvent[] = [
		{
			kind: 'thought',
			id: 'venue',
			author: 'context_enricher',
			text: '**Looking up Pizzeria Stamatello**\n\nI want a baseline on the venue itself before comparing it with nearby competitors.\n\n'
		},
		{
			kind: 'detail',
			id: 'maps',
			group: 'platform',
			family: 'Google Maps',
			text: 'Checking Google Maps for Pizzeria Stamatello and 6 nearby competitors'
		},
		{
			kind: 'thought',
			id: 'reviews',
			author: 'research_lead',
			text: '**Reading guest signals**\n\nThe rating spread looks solid, so I am checking review language for repeat strengths, complaints, and signs of whether demand is tourist-heavy or local.\n\n'
		},
		{
			kind: 'detail',
			id: 'google-reviews',
			group: 'platform',
			family: 'Google reviews',
			text: 'Reading 128 Google reviews for Pizzeria Stamatello'
		},
		{
			kind: 'detail',
			id: 'tripadvisor',
			group: 'platform',
			family: 'TripAdvisor',
			text: 'Cross-referencing TripAdvisor for Pizzeria Stamatello'
		},
		{
			kind: 'thought',
			id: 'market',
			author: 'research_lead',
			text: '**Checking market context**\n\nNow I am checking whether the surrounding market changed enough to explain the venue performance, rather than treating ratings as the whole story.'
		}
	];

	const answer = `Pizzeria Stamatello appears well positioned in its immediate market. Its strongest signal is consistency: high review volume, steady positive language around dough and service, and enough nearby competition to make the rating meaningful rather than isolated.

The main risk is differentiation. Several nearby restaurants compete on similar Neapolitan cues, so Stamatello needs to keep leaning into reliability and local repeat visits instead of depending only on discovery traffic.`;

	let liveStartedAtMs: number | null = $state(null);

	onMount(() => {
		liveStartedAtMs = Date.now() - 18_000;
	});
</script>

<svelte:head>
	<title>Agent Activity Preview | Superextra</title>
</svelte:head>

<main class="min-h-screen bg-cream px-5 py-8 text-black dark:bg-black dark:text-white md:px-6">
	<div class="mx-auto flex max-w-[700px] flex-col gap-8">
		<section class="flex justify-start">
			<div class="max-w-[95%] px-1 py-1">
				<div
					class="prose max-w-none text-[15px] leading-relaxed text-black/80 dark:text-white/80 prose-headings:text-black dark:prose-headings:text-white prose-strong:text-black dark:prose-strong:text-white"
				>
					{@html renderMarkdown(answer)}
				</div>
				<div class="mt-4">
					<LiveActivity events={events} elapsedMs={35_000} completed />
				</div>
			</div>
		</section>

		<section class="flex justify-start">
			<div class="max-w-[95%] px-1 py-1">
				<LiveActivity events={events} startedAtMs={liveStartedAtMs} />
			</div>
		</section>
	</div>
</main>
