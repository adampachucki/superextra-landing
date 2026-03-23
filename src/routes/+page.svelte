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
