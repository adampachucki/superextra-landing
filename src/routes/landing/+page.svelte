<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Hero from '$lib/components/Hero.svelte';
	import About from '$lib/components/About.svelte';
	import PlatformCards from '$lib/components/PlatformCards.svelte';
	import Audiences from '$lib/components/Audiences.svelte';
	import UseCases from '$lib/components/UseCases.svelte';
	import GetOnboard from '$lib/components/GetOnboard.svelte';
	import FAQ from '$lib/components/FAQ.svelte';
	import DataSources from '$lib/components/DataSources.svelte';
	import CTA from '$lib/components/CTA.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import AccessForm from '$lib/components/AccessForm.svelte';
</script>

<svelte:head>
	<title>Superextra - Super Local Intelligence for Restaurants</title>
	<meta
		name="description"
		content="Super local intelligence and competitor benchmarking platform for the restaurant industry. The extra advantage behind smarter decisions."
	/>
	<meta property="og:title" content="Superextra - Super Local Intelligence for Restaurants" />
	<meta
		property="og:description"
		content="Super local intelligence and competitor benchmarking platform for the restaurant industry. The extra advantage behind smarter decisions."
	/>
	<meta property="og:type" content="website" />
	<meta property="og:url" content="https://landing.superextra.ai/landing" />
	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content="Superextra - Super Local Intelligence for Restaurants" />
	<meta
		name="twitter:description"
		content="Super local intelligence and competitor benchmarking platform for the restaurant industry."
	/>
</svelte:head>

<Navbar />

<main>
	<Hero />
	<About />
	<PlatformCards />
	<Audiences />
	<UseCases />
	<GetOnboard />
	<FAQ />
	<DataSources />
	<CTA />
</main>

<Footer />
<AccessForm />
