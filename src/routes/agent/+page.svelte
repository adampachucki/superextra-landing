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

	function handleLeave({
		query,
		place
	}: {
		query: string;
		place: { name: string; secondary: string; placeId: string };
	}) {
		leaving = true;
		chatState.start(query, place);
		setTimeout(() => goto('/agent/chat'), 250);
	}

	const agentUseCases = [
		{
			title: 'Market context',
			graphicIndex: 4,
			description: `Know whether a slow month is yours or the market's. Separate performance from the trend so every decision is based on signal, not noise.`
		},
		{
			title: 'Site selection',
			graphicIndex: 1,
			description: `Foot traffic, competition density, demographics, and rent — side by side. Every new location decision grounded in real data.`
		},
		{
			title: 'Concept validation',
			graphicIndex: 0,
			description: `See what's actually working nearby and whether local demand supports the idea — before committing to a buildout.`
		},
		{
			title: 'Wage benchmarking',
			graphicIndex: 3,
			description: `See what nearby restaurants actually pay for every role. Set compensation that attracts talent without overspending.`
		},
		{
			title: 'Price positioning',
			graphicIndex: 2,
			description: `Know exactly where every menu item sits against comparable venues. Adjust with confidence, not guesswork.`
		},
		{
			title: 'Sentiment trends',
			graphicIndex: 7,
			description: `Surface the patterns individual reviews never reveal. See which themes are growing, fading, or unique to a single location.`
		},
		{
			title: 'Competitor tracking',
			graphicIndex: 5,
			description:
				'Menu changes, price moves, new launches — tracked as they happen. Stay current without relying on word of mouth.'
		},
		{
			title: 'Market shifts',
			graphicIndex: 6,
			description: `New openings, closures, and format changes in the area — flagged early so there's time to respond.`
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
