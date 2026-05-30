<script lang="ts">
	import { fly } from 'svelte/transition';
	import { browser } from '$app/environment';
	import * as m from '$lib/paraglide/messages';

	let dismissed = $state(!browser ? true : localStorage.getItem('se_cookies') === '1');

	function accept() {
		localStorage.setItem('se_cookies', '1');
		dismissed = true;
	}
</script>

{#if !dismissed}
	<div
		class="fixed right-5 bottom-5 z-50 hidden items-center gap-3 rounded-full border-[0.5px] border-black/10 bg-white py-2 pr-2 pl-4 text-xs text-black/60 md:flex dark:border-white/10 dark:bg-cream-100 dark:text-white/60"
		transition:fly={{ y: 12, duration: 250 }}
	>
		<span
			>{m.cookie_we_use()}
			<a
				href="/privacy-policy"
				class="underline transition-colors hover:text-black dark:hover:text-white"
				>{m.cookie_link()}</a
			></span
		>
		<button onclick={accept} class="btn-primary px-3 py-1 text-xs"> OK </button>
	</div>
{/if}
