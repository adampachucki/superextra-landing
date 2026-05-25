<script lang="ts">
	const origin = 'https://agent.superextra.ai';

	let {
		title,
		description,
		canonicalPath = '/',
		robots = 'index, follow'
	}: {
		title: string;
		description: string;
		canonicalPath?: string;
		robots?: string;
	} = $props();

	let canonicalUrl = $derived(`${origin}${canonicalPath}`);
</script>

<svelte:head>
	<title>{title}</title>
	<meta name="description" content={description} />
	<meta name="robots" content={robots} />
	<link rel="canonical" href={canonicalUrl} />

	<meta property="og:site_name" content="Superextra" />
	<meta property="og:locale" content="en_US" />
	<meta property="og:type" content="website" />
	<meta property="og:title" content={title} />
	<meta property="og:description" content={description} />
	<meta property="og:url" content={canonicalUrl} />

	<meta name="twitter:card" content="summary" />
	<meta name="twitter:title" content={title} />
	<meta name="twitter:description" content={description} />
	<meta name="theme-color" content="#f8f6f1" />
</svelte:head>
