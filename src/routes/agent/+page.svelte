<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import AccessForm from '$lib/components/AccessForm.svelte';
	import RestaurantHero from '$lib/components/restaurants/RestaurantHero.svelte';
	import ValueProps from '$lib/components/restaurants/ValueProps.svelte';

	import UseCases from '$lib/components/UseCases.svelte';
	import FAQ from '$lib/components/FAQ.svelte';
	import DataSources from '$lib/components/DataSources.svelte';
	import RestaurantCTA from '$lib/components/restaurants/RestaurantCTA.svelte';

	const agentUseCases = [
		{
			title: 'Competitive Benchmarking',
			description:
				'See how your pricing, reviews, and traffic stack up against the restaurants around you. Know exactly where you stand without the guesswork.'
		},
		{
			title: 'Menu & Pricing',
			description:
				'Track what competitors charge, which items are trending, and where your pricing sits in the local market. Adjust with data, not gut feel.'
		},
		{
			title: 'Marketing Strategy',
			description:
				'Benchmark your brand against local competitors. Know which campaigns, channels, and price points are actually driving results in your market.'
		},
		{
			title: 'Expansion Planning',
			description:
				'Evaluate new locations with foot traffic, competition density, demographics, and rent data side by side. De-risk every site decision before you sign a lease.'
		},
		{
			title: 'Concept Validation',
			description:
				"Test a new concept against real market data before you commit. See what's already working in the area, where the gaps are, and whether demand supports your idea."
		},
		{
			title: 'Guest Sentiment',
			description:
				'Understand what guests love and what frustrates them — across your venues and the competition. Spot patterns that individual reviews never reveal.'
		},
		{
			title: 'Workforce & Costs',
			description:
				'Know what the market actually pays for every role, how your labor costs compare, and where staffing pressure is building around you.'
		},
		{
			title: 'Market Monitoring',
			description:
				'Get a clear picture when competitors open, close, change prices, or shift strategy. Stay ahead of changes instead of reacting to them.'
		}
	];

	const agentFaqs = [
		{
			question: 'How does this actually work?',
			answer:
				"You ask a question about your market. Superextra searches across dozens of data sources — reviews, delivery platforms, foot traffic, pricing, public records — and returns a clear, sourced answer. No dashboards to learn, no reports to wait for."
		},
		{
			question: 'How accurate is the data?',
			answer:
				"Every insight is grounded in real data from public and proprietary sources. AI models cross-reference and validate continuously. When something isn't available, the agent says so rather than guessing."
		},
		{
			question: 'Do I need to connect my POS or share any internal data?',
			answer:
				'No. Superextra brings the market to you — competitor activity, local pricing, guest sentiment, foot traffic. Nothing to integrate, no internal data to share.'
		},
		{
			question: 'What markets are covered?',
			answer:
				'Launching with deep coverage in select European markets and expanding rapidly. Reach out to check availability for your area.'
		},
		{
			question: 'What does it cost?',
			answer:
				'Pricing is based on the number of locations and depth of intelligence needed. Early access customers get preferential rates.'
		}
	];
</script>

<svelte:head>
	<title>Restaurant Intelligence - Superextra</title>
	<meta name="description" content="AI-powered market intelligence that shows you where you stand against the competition and where to go next." />
	<meta property="og:title" content="Restaurant Intelligence - Superextra" />
	<meta property="og:description" content="See what's happening outside your four walls. Market analyst for every restaurant." />
	<meta property="og:url" content="https://superextra.ai/agent" />
</svelte:head>

<Navbar minimal />

<main>
	<RestaurantHero />
	<ValueProps intro="Restaurant operators make critical decisions every day — where to open, how to price, when to hire — too often without a clear view of the market around them at all. Superextra changes that." description="Our AI models synthesize competitor, pricing, guest, delivery, and market signals into an external intelligence layer for your restaurant. Better context behind better decisions." />
	<UseCases items={agentUseCases} title="The questions you're already asking — now with real answers" titleClass="max-w-3xl" subtitleClass="text-xs" />
	<FAQ items={agentFaqs} />
	<DataSources title="Dozens of data sources" subtitle="We aggregate and validate data across every market we cover." />
	<RestaurantCTA />
</main>

<Footer />
<AccessForm />
