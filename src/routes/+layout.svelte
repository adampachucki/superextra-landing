<script lang="ts">
	import '../app.css';
	import { afterNavigate } from '$app/navigation';
	import { onMount } from 'svelte';
	import CookieBanner from '$lib/components/CookieBanner.svelte';
	import LoginModal from '$lib/components/agent/LoginModal.svelte';
	import BillingModal from '$lib/components/agent/BillingModal.svelte';

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

{@render children()}
<CookieBanner />
<LoginModal />
<BillingModal />
