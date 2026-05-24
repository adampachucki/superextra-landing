<script lang="ts">
	const origin = 'https://agent.superextra.ai';
	const defaultImage = `${origin}/landscape.webp`;
	const defaultImageAlt = 'Superextra restaurant market intelligence workspace';

	let {
		title,
		description,
		canonicalPath = '/',
		robots = 'index, follow',
		image = defaultImage,
		imageAlt = defaultImageAlt
	}: {
		title: string;
		description: string;
		canonicalPath?: string;
		robots?: string;
		image?: string;
		imageAlt?: string;
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
	<meta property="og:image" content={image} />
	<meta property="og:image:secure_url" content={image} />
	<meta property="og:image:type" content="image/webp" />
	<meta property="og:image:width" content="1707" />
	<meta property="og:image:height" content="1583" />
	<meta property="og:image:alt" content={imageAlt} />

	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content={title} />
	<meta name="twitter:description" content={description} />
	<meta name="twitter:image" content={image} />
	<meta name="twitter:image:alt" content={imageAlt} />
	<meta name="theme-color" content="#f8f6f1" />
</svelte:head>
