<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Hero from '$lib/components/Hero.svelte';
	import About from '$lib/components/About.svelte';
	import Platform from '$lib/components/Platform.svelte';
	import Audiences from '$lib/components/Audiences.svelte';
	import HowItWorks from '$lib/components/HowItWorks.svelte';
	import FAQ from '$lib/components/FAQ.svelte';
	import CTA from '$lib/components/CTA.svelte';
	import Footer from '$lib/components/Footer.svelte';
</script>

<Navbar />

<main>
	<Hero />
	<About />
	<Platform />
	<Audiences />
	<HowItWorks />
	<FAQ />
	<CTA />
</main>

<Footer />
