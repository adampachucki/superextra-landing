<script lang="ts">
	let scrolled = $state(false);
	let mobileOpen = $state(false);

	function handleScroll() {
		scrolled = window.scrollY > 20;
	}
</script>

<svelte:window onscroll={handleScroll} />

<nav
	class="fixed top-0 left-0 right-0 z-50 transition-all duration-300 {scrolled
		? 'bg-white/80 backdrop-blur-xl border-b border-gray-200'
		: 'bg-transparent'}"
>
	<div class="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-5">
		<a href="/" class="flex items-center">
			<span class="text-[22px] font-black tracking-tight text-black"
				>superextra</span
			>
		</a>

		<div class="hidden items-center gap-8 md:flex">
			<a href="#platform" class="text-sm text-black/60 transition-colors hover:text-black">Platform</a>
			<a href="#how-it-works" class="text-sm text-black/60 transition-colors hover:text-black">How It Works</a>
			<a href="#faq" class="text-sm text-black/60 transition-colors hover:text-black">FAQ</a>
		</div>

		<div class="hidden items-center gap-3 md:flex">
			<a href="https://superextra.ai" class="rounded-full border border-gray-200 px-5 py-2 text-sm text-black transition-colors hover:bg-gray-50">Sign in</a>
			<a href="https://superextra.ai" class="rounded-full bg-black px-5 py-2 text-sm text-white transition-colors hover:bg-black/80">Get Early Access</a>
		</div>

		<button
			class="text-black md:hidden"
			onclick={() => (mobileOpen = !mobileOpen)}
			aria-label="Toggle menu"
		>
			{#if mobileOpen}
				<svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6 18L18 6M6 6l12 12" /></svg>
			{:else}
				<svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 6h16M4 12h16M4 18h16" /></svg>
			{/if}
		</button>
	</div>

	{#if mobileOpen}
		<div class="border-t border-gray-100 bg-white md:hidden">
			<div class="flex flex-col gap-4 px-6 py-6">
				<a href="#platform" class="text-sm text-black/60" onclick={() => (mobileOpen = false)}>Platform</a>
				<a href="#how-it-works" class="text-sm text-black/60" onclick={() => (mobileOpen = false)}>How It Works</a>
				<a href="#faq" class="text-sm text-black/60" onclick={() => (mobileOpen = false)}>FAQ</a>
				<hr class="border-gray-100" />
				<a href="https://superextra.ai" class="text-sm text-black/60">Sign in</a>
				<a href="https://superextra.ai" class="rounded-full bg-black px-5 py-2.5 text-center text-sm text-white">Get Early Access</a>
			</div>
		</div>
	{/if}
</nav>
