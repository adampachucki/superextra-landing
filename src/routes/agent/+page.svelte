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
			title: 'Down month',
			description: `Sales dropped 12% and the team is second-guessing the new menu. Is it you or is everyone down? Separate your performance from the market trend.`
		},
		{
			title: 'Expansion risk',
			description: `Opening a second location is the biggest bet you'll make. See foot traffic, competition, demographics, and rent before you sign.`
		},
		{
			title: 'Unproven concept',
			description: `You're betting a buildout on a concept that "feels right." Find out what's actually working nearby and whether local demand supports the idea.`
		},
		{
			title: 'Staffing gaps',
			description: `Lost two line cooks this month. Is your pay off or is the whole market tight? Benchmark what nearby restaurants actually pay for every role.`
		},
		{
			title: 'Pricing blind spots',
			description: `The place across the street undercut your lunch deal last week and you only noticed by accident. Know where your menu sits against every comparable venue.`
		},
		{
			title: 'Review overload',
			description: `Every review feels urgent but which complaints are real patterns? Surface the sentiment trends that individual reviews never reveal.`
		},
		{
			title: 'Late to know',
			description:
				'They changed their menu and adjusted prices. You heard about it months later from a supplier. Track every competitor move as it happens.'
		},
		{
			title: 'New competition',
			description:
				'A new spot opened two streets over and started pulling your weekday crowd. Get alerted to openings, closures, and market shifts early.'
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
