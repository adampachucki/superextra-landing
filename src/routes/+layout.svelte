<script lang="ts">
	import '../app.css';
	import { afterNavigate } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import PreviewBadge from '$lib/components/PreviewBadge.svelte';
	import CookieBanner from '$lib/components/CookieBanner.svelte';

	onMount(() => {
		const onBeforeUnload = () => {
			sessionStorage.setItem('se:scroll', String(scrollY));
		};
		addEventListener('beforeunload', onBeforeUnload);
		// Safari fires pagehide but not always beforeunload
		addEventListener('pagehide', onBeforeUnload);
		return () => {
			removeEventListener('beforeunload', onBeforeUnload);
			removeEventListener('pagehide', onBeforeUnload);
		};
	});

	afterNavigate(({ type }) => {
		if (type === 'enter') {
			const y = sessionStorage.getItem('se:scroll');
			if (y) {
				sessionStorage.removeItem('se:scroll');
				requestAnimationFrame(() => scrollTo(0, parseInt(y)));
			}
		}
	});

	let { children } = $props();
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
	<meta property="og:url" content="https://superextra.ai" />
	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content="Superextra - Super Local Intelligence for Restaurants" />
	<meta
		name="twitter:description"
		content="Super local intelligence and competitor benchmarking platform for the restaurant industry."
	/>
</svelte:head>

{@render children()}
{#if !page.url.pathname.startsWith('/agent')}
	<div class="fixed bottom-5 left-5 z-50 hidden md:block">
		<PreviewBadge />
	</div>
{/if}
<CookieBanner />
