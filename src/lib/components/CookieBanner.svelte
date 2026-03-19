<script lang="ts">
	import { browser } from '$app/environment';

	let dismissed = $state(!browser ? true : localStorage.getItem('se_cookies') === '1');

	function accept() {
		localStorage.setItem('se_cookies', '1');
		dismissed = true;
	}
</script>

{#if !dismissed}
	<div class="fixed right-5 bottom-5 z-50 flex items-center gap-3 rounded-full border border-black/10 bg-white/80 py-2 pr-2 pl-4 text-xs text-black/60 shadow-[0_2px_20px_-4px_rgba(0,0,0,0.06)] backdrop-blur-sm">
		<span>We use <a href="/privacy-policy" class="underline transition-colors hover:text-black/80">cookies</a></span>
		<button
			onclick={accept}
			class="rounded-full bg-black px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-black/80"
		>
			OK
		</button>
	</div>
{/if}
