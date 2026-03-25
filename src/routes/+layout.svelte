<script lang="ts">
	import '../app.css';
	import { afterNavigate } from '$app/navigation';
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
	let unlocked = $state(true); // TEMP: password wall disabled
	let input = $state('');
	let shake = $state(false);

	function submit() {
		if (input === 'superpower') {
			localStorage.setItem('se_pass', 'superpower');
			unlocked = true;
		} else {
			shake = true;
			setTimeout(() => (shake = false), 500);
		}
	}
</script>

<svelte:head>
	<title>Superextra - Super Local Intelligence for Restaurants</title>
	<meta name="description" content="Super local intelligence and competitor benchmarking platform for the restaurant industry. The extra advantage behind smarter decisions." />
	<meta property="og:title" content="Superextra - Super Local Intelligence for Restaurants" />
	<meta property="og:description" content="Super local intelligence and competitor benchmarking platform for the restaurant industry. The extra advantage behind smarter decisions." />
	<meta property="og:type" content="website" />
	<meta property="og:url" content="https://superextra.ai" />
	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content="Superextra - Super Local Intelligence for Restaurants" />
	<meta name="twitter:description" content="Super local intelligence and competitor benchmarking platform for the restaurant industry." />
</svelte:head>

{#if unlocked}
	{@render children()}
	<div class="fixed bottom-5 left-5 z-50 hidden md:block">
		<PreviewBadge />
	</div>
	<CookieBanner />
{:else}
	<div class="fixed inset-0 z-[200] flex items-center justify-center bg-white dark:bg-cream">
		<form onsubmit={(e) => { e.preventDefault(); submit(); }} class="flex flex-col items-center gap-4">
			<input
				bind:value={input}
				type="password"
				placeholder="Password"
				autofocus
				class="w-64 rounded-xl border border-cream-200 bg-white px-4 py-3 text-center text-sm text-black placeholder:text-black/25 focus:border-black focus:ring-0 focus:outline-none dark:bg-cream-50 dark:text-white dark:placeholder:text-white/25 dark:focus:border-white {shake ? 'animate-shake' : ''}"
			/>
			<button
				type="submit"
				class="btn-primary px-7 py-2.5 text-sm"
			>
				Enter
			</button>
		</form>
	</div>
{/if}
