<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import AccessForm from '$lib/components/AccessForm.svelte';
	import RestaurantHero from '$lib/components/restaurants/RestaurantHero.svelte';
	import ValueProps from '$lib/components/restaurants/ValueProps.svelte';

	import RestaurantCTA from '$lib/components/restaurants/RestaurantCTA.svelte';
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
	<ValueProps />
	<RestaurantCTA />
</main>

<Footer />
<AccessForm />
