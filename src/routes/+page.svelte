<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Hero from '$lib/components/Hero.svelte';
	import About from '$lib/components/About.svelte';
	import Platform from '$lib/components/Platform.svelte';
	import Audiences from '$lib/components/Audiences.svelte';
	import UseCases from '$lib/components/UseCases.svelte';
	import GetOnboard from '$lib/components/GetOnboard.svelte';
	import FAQ from '$lib/components/FAQ.svelte';
	import CTA from '$lib/components/CTA.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import AccessForm from '$lib/components/AccessForm.svelte';
</script>

<Navbar />

<main>
	<Hero />
	<About />
	<Platform />
	<Audiences />
	<UseCases />
	<GetOnboard />
	<FAQ />
	<CTA />
</main>

<Footer />
<AccessForm />
