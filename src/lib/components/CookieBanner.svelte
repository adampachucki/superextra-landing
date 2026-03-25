<script lang="ts">
	import { browser } from '$app/environment';

	let dismissed = $state(!browser ? true : localStorage.getItem('se_cookies') === '1');

	function accept() {
		localStorage.setItem('se_cookies', '1');
		dismissed = true;
	}
</script>

{#if !dismissed}
	<div class="fixed right-5 bottom-5 z-50 hidden items-center gap-3 rounded-full border-[0.5px] border-black/10 dark:border-white/10 bg-white/80 dark:bg-cream-100/80 py-2 pr-2 pl-4 text-xs text-black/60 dark:text-white/60 backdrop-blur-sm md:flex">
		<span>We use <a href="/privacy-policy" class="underline transition-colors hover:text-black dark:hover:text-white">cookies</a></span>
		<button
			onclick={accept}
			class="btn-primary px-3 py-1 text-xs"
		>
			OK
		</button>
	</div>
{/if}
