<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>Superextra - Super Local Intelligence for Restaurants</title>
	<meta name="description" content="Super local intelligence and competitor benchmarking platform for the restaurant industry. The extra advantage behind smarter decisions." />
</svelte:head>

{@render children()}
