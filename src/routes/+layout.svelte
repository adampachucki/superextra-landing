<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { browser } from '$app/environment';
	import { afterNavigate } from '$app/navigation';
	import { onMount } from 'svelte';

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
	let unlocked = $state(!browser || localStorage.getItem('se_pass') === 'superpower');
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
	<link rel="icon" href={favicon} />
	<title>Superextra - Super Local Intelligence for Restaurants</title>
	<meta name="description" content="Super local intelligence and competitor benchmarking platform for the restaurant industry. The extra advantage behind smarter decisions." />
</svelte:head>

{#if unlocked}
	{@render children()}
{:else}
	<div class="fixed inset-0 z-[200] flex items-center justify-center bg-white">
		<form onsubmit={(e) => { e.preventDefault(); submit(); }} class="flex flex-col items-center gap-4">
			<input
				bind:value={input}
				type="password"
				placeholder="Password"
				autofocus
				class="w-64 rounded-xl border border-gray-200 px-4 py-3 text-center text-sm text-black placeholder:text-black/25 focus:border-black focus:ring-0 focus:outline-none {shake ? 'animate-shake' : ''}"
			/>
			<button
				type="submit"
				class="rounded-full bg-black px-7 py-2.5 text-sm font-medium text-white transition-colors hover:bg-black/80"
			>
				Enter
			</button>
		</form>
	</div>
{/if}

<style>
	@keyframes shake {
		0%, 100% { transform: translateX(0); }
		20%, 60% { transform: translateX(-6px); }
		40%, 80% { transform: translateX(6px); }
	}
	:global(.animate-shake) {
		animation: shake 0.4s ease-in-out;
	}
</style>
