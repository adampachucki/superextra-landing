<script lang="ts">
	import { goto } from '$app/navigation';
	import { chatState } from '$lib/chat-state.svelte';
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import AccessForm from '$lib/components/AccessForm.svelte';
	import RestaurantHero from '$lib/components/restaurants/RestaurantHero.svelte';
	import About from '$lib/components/About.svelte';

	import UseCases from '$lib/components/UseCases.svelte';
	import DataSources from '$lib/components/DataSources.svelte';
	import RestaurantCTA from '$lib/components/restaurants/RestaurantCTA.svelte';

	let leaving = $state(false);
	let leaveError = $state<string | null>(null);

	async function handleLeave({
		query,
		place
	}: {
		query: string;
		place: { name: string; secondary: string; placeId: string };
	}) {
		leaving = true;
		leaveError = null;
		try {
			await chatState.startNewChat(query, place);
			setTimeout(() => goto('/agent/chat'), 250);
		} catch (err) {
			leaving = false;
			leaveError =
				err instanceof Error ? err.message : 'Could not start chat. Please try again.';
		}
	}

	const agentUseCases = [
		{
			title: 'Market context',
			graphicIndex: 2,
			description: `Track local market dynamics, demand cycles, and competitor momentum. Separate venue performance from the market trend — so every decision starts from signal, not noise.`
		},
		{
			title: 'Expansion strategy',
			graphicIndex: 1,
			description: `Evaluate locations with foot traffic, demographics, competition density, and rent data mapped around every site. De-risk every expansion decision.`
		},
		{
			title: 'Concept validation',
			graphicIndex: 7,
			description: `Validate new concepts against real local signals. See what's working nearby and whether demand supports the idea — before committing to a buildout.`
		},
		{
			title: 'Financial planning',
			graphicIndex: 3,
			description: `Project revenue, occupancy, and labor costs against real local benchmarks. Track how spend and staffing compare to the market — and spot inefficiencies before they hit margins.`
		},
		{
			title: 'Price positioning',
			graphicIndex: 4,
			description: `Benchmark pricing against local competitors on the price curve. Know which price points, channels, and promos are driving results — and adjust with confidence.`
		},
		{
			title: 'Sentiment trends',
			graphicIndex: 5,
			description: `Connect review signals across venues. See which themes are growing, fading, or unique to a single location — and catch shifts before they become ratings.`
		},
		{
			title: 'Competitor tracking',
			graphicIndex: 6,
			description:
				'Monitor competitor moves as they happen — menu changes, price shifts, new launches, and format pivots. Stay current without relying on word of mouth.'
		},
		{
			title: 'Market shifts',
			graphicIndex: 0,
			description: `Track openings, closures, and format changes across the local market. Spot white spaces where demand meets thin competition — flagged early, with time to respond.`
		}
	];
</script>

<svelte:head>
	<title>Restaurant Intelligence - Superextra</title>
	<meta
		name="description"
		content="AI-powered market intelligence that shows you where you stand against the competition and where to go next."
	/>
	<meta property="og:title" content="Restaurant Intelligence - Superextra" />
	<meta
		property="og:description"
		content="See what's happening outside your four walls. Market analyst for every restaurant."
	/>
	<meta property="og:url" content="https://agent.superextra.ai" />
</svelte:head>

<div class="page-exit" class:is-leaving={leaving}>
	<Navbar minimal />

	<main>
		<RestaurantHero onleave={handleLeave} />
		{#if leaveError}
			<div
				class="mx-auto max-w-[720px] px-6 pb-6 text-center text-sm text-red-600 dark:text-red-400"
				role="alert"
			>
				{leaveError}
			</div>
		{/if}
		<About
			headline="The market view your restaurant has been missing"
			intro="Restaurant operators make critical decisions every day — where to open, how to price, when to hire — too often without a clear view of the market around them at all. Superextra changes that."
			description="Our AI models synthesize competitor, pricing, guest, delivery, and market signals into an external intelligence layer for your restaurant. Better context behind better decisions."
			class="border-t border-cream-200 md:border-t-0"
		/>
		<UseCases
			items={agentUseCases}
			title="The questions you've been asking – answered"
			titleClass="max-w-2xl"
			subtitleClass="text-xs"
		/>
		<DataSources
			title="Only credible data sources"
			subtitle="Reviewed and validated information you can rely on."
		/>
		<RestaurantCTA />
	</main>

	<Footer borderless />
	<AccessForm />
</div>

<style>
	.page-exit {
		transition:
			opacity 0.25s cubic-bezier(0.4, 0, 1, 1),
			transform 0.25s cubic-bezier(0.4, 0, 1, 1),
			filter 0.25s cubic-bezier(0.4, 0, 1, 1);
	}

	.page-exit.is-leaving {
		opacity: 0;
		transform: scale(0.98) translateY(-8px);
		filter: blur(4px);
		pointer-events: none;
	}
</style>
