<script lang="ts">
	import { getLocale, locales, localizeHref, baseLocale } from '$lib/paraglide/runtime';

	// OpenGraph locale tags per app locale.
	const OG_LOCALE: Record<string, string> = {
		en: 'en_US',
		de: 'de_DE',
		pl: 'pl_PL'
	};

	let {
		title,
		description,
		canonicalPath = '/',
		robots = 'index, follow',
		// English-only pages (memo, legal, app shell) set this false: no hreflang
		// alternates are emitted and the canonical is the plain unprefixed path.
		localized = true,
		// Marketing/legal pages live on landing.superextra.ai; the app shell
		// defaults to agent.superextra.ai. Override per page so canonicals point
		// at the domain that actually serves the content.
		origin = 'https://agent.superextra.ai'
	}: {
		title: string;
		description: string;
		canonicalPath?: string;
		robots?: string;
		localized?: boolean;
		origin?: string;
	} = $props();

	// Canonical points at the current locale's URL; alternates cover every locale
	// plus x-default → the base (English) URL.
	const canonicalUrl = $derived(
		localized
			? `${origin}${localizeHref(canonicalPath, { locale: getLocale() })}`
			: `${origin}${canonicalPath}`
	);
	const alternates = $derived(
		localized
			? locales.map((locale) => ({
					locale,
					href: `${origin}${localizeHref(canonicalPath, { locale })}`
				}))
			: []
	);
	const xDefault = $derived(`${origin}${localizeHref(canonicalPath, { locale: baseLocale })}`);
</script>

<svelte:head>
	<title>{title}</title>
	<meta name="description" content={description} />
	<meta name="robots" content={robots} />
	<link rel="canonical" href={canonicalUrl} />

	{#each alternates as alt (alt.locale)}
		<link rel="alternate" hreflang={alt.locale} href={alt.href} />
	{/each}
	{#if localized}
		<link rel="alternate" hreflang="x-default" href={xDefault} />
	{/if}

	<meta property="og:site_name" content="Superextra" />
	<meta property="og:locale" content={OG_LOCALE[getLocale()] ?? 'en_US'} />
	<meta property="og:type" content="website" />
	<meta property="og:title" content={title} />
	<meta property="og:description" content={description} />
	<meta property="og:url" content={canonicalUrl} />

	<meta name="twitter:card" content="summary" />
	<meta name="twitter:title" content={title} />
	<meta name="twitter:description" content={description} />
	<meta name="theme-color" content="#f8f6f1" />
</svelte:head>
