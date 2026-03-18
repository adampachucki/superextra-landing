<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Hero from '$lib/components/Hero.svelte';
	import About from '$lib/components/About.svelte';
	import Platform from '$lib/components/Platform.svelte';
	import Audiences from '$lib/components/Audiences.svelte';
	import UseCases from '$lib/components/UseCases.svelte';
	import HowItWorks from '$lib/components/HowItWorks.svelte';
	import FAQ from '$lib/components/FAQ.svelte';
	import CTA from '$lib/components/CTA.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import AccessForm from '$lib/components/AccessForm.svelte';
	import PreviewBadge from '$lib/components/PreviewBadge.svelte';
	import CookieBanner from '$lib/components/CookieBanner.svelte';
</script>

<Navbar />

<main>
	<Hero />
	<About />
	<Platform />
	<Audiences />
	<UseCases />
	<HowItWorks />
	<FAQ />
	<CTA />
</main>

<Footer />
<AccessForm />
<PreviewBadge />
<CookieBanner />
