<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import AccessForm from '$lib/components/AccessForm.svelte';
	import RestaurantHero from '$lib/components/restaurants/RestaurantHero.svelte';
	import About from '$lib/components/About.svelte';

	import UseCases from '$lib/components/UseCases.svelte';
	import DataSources from '$lib/components/DataSources.svelte';
	import RestaurantCTA from '$lib/components/restaurants/RestaurantCTA.svelte';

	const agentUseCases = [
		{
			title: 'Down month \u2014 us or everyone?',
			description:
				`Sales dropped 12% and the whole team is second-guessing the new menu. Superextra separates your performance from the market trend so you know whether to fix something or ride it out.`
		},
		{
			title: 'Expansion gamble',
			description:
				`Opening a second location is the biggest bet you'll make. Most operators choose based on gut feel and a few drive-bys. Superextra maps foot traffic, competition density, demographics, and rent before you sign a lease.`
		},
		{
			title: 'New concept, no proof',
			description:
				`You're betting a buildout on a concept that "feels right" for the area. Superextra shows what's already working nearby, where the gaps are, and whether local demand actually supports the idea.`
		},
		{
			title: 'Staffing squeeze',
			description:
				`You lost two line cooks this month and you're not sure if your pay is off or the whole market is tight. Superextra benchmarks what restaurants nearby actually pay for every role so you hire to retain, not just to fill.`
		},
		{
			title: 'Pricing in the dark',
			description:
				`You set prices based on food cost and a rough sense of what the neighbourhood will bear. Meanwhile the place across the street undercut your lunch deal last week. Superextra shows exactly where your menu sits relative to every comparable venue nearby.`
		},
		{
			title: 'Review noise',
			description:
				`You read every review but still can't tell what's a one-off complaint and what's a real pattern. Superextra surfaces the sentiment trends that individual reviews never reveal \u2014 across your venues and the competition.`
		},
		{
			title: 'Competitor blind spot',
			description:
				'Your competitors changed their menu and adjusted prices. You heard about it months later from a supplier. Superextra tracks every move in your market so you can respond in days, not quarters.'
		},
		{
			title: 'Slow to react',
			description:
				'A new competitor opened two streets over and started pulling your weekday crowd. You found out when covers were already down. Superextra alerts you to openings, closures, and strategy shifts as they happen.'
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
	<About headline="The market view your restaurant has been missing" intro="Restaurant operators make critical decisions every day — where to open, how to price, when to hire — too often without a clear view of the market around them at all. Superextra changes that." description="Our AI models synthesize competitor, pricing, guest, delivery, and market signals into an external intelligence layer for your restaurant. Better context behind better decisions." class="border-t border-cream-200 md:border-t-0" />
	<UseCases items={agentUseCases} title="The questions you've been asking – answered" titleClass="max-w-2xl" subtitleClass="text-xs" />
	<DataSources title="Dozens of data sources" subtitle="We aggregate and validate data across every market we cover." />
	<RestaurantCTA />
</main>

<Footer />
<AccessForm />
