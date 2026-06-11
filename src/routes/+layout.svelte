<script lang="ts">
	import type { Pathname } from '$app/types';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { locales, localizeHref } from '$lib/paraglide/runtime';
	import '../app.css';
	import { afterNavigate } from '$app/navigation';
	import { onMount } from 'svelte';
	import CookieBanner from '$lib/components/CookieBanner.svelte';
	import AccessForm from '$lib/components/AccessForm.svelte';
	import LoginModal from '$lib/components/agent/LoginModal.svelte';
	import BillingModal from '$lib/components/agent/BillingModal.svelte';
	import BillingReturnNotice from '$lib/components/agent/BillingReturnNotice.svelte';
	import { stampFirstTouch } from '$lib/campaign';
	import { initAnalytics } from '$lib/analytics';
	import { initMetaPixel } from '$lib/meta-pixel';

	onMount(() => {
		stampFirstTouch();
		initAnalytics();
		initMetaPixel();

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
<AccessForm />
<LoginModal />
<BillingModal />
<BillingReturnNotice />

<div style="display:none">
	{#each locales as locale (locale)}
		<a href={resolve(localizeHref(page.url.pathname, { locale }) as Pathname)}>{locale}</a>
	{/each}
</div>
