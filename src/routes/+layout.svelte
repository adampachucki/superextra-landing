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
	let showPreviewBadge = $derived(!page.url.pathname.startsWith('/chat'));
</script>

{@render children()}
{#if showPreviewBadge}
	<div class="fixed bottom-5 left-5 z-50 hidden md:block">
		<PreviewBadge />
	</div>
{/if}
<CookieBanner />
