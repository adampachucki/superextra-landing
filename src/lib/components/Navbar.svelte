<script lang="ts">
	import { formState } from '$lib/form-state.svelte';
	import { onMount } from 'svelte';

	let {
		transparent = false,
		minimal = false,
		static: isStatic = false
	}: { transparent?: boolean; minimal?: boolean; static?: boolean } = $props();

	let scrolled = $state(false);
	let mobileOpen = $state(false);

	function handleScroll() {
		scrolled = window.scrollY > 20;
	}

	onMount(() => handleScroll());

	let over = $derived(transparent && !scrolled && !mobileOpen);

	function smoothScroll(e: MouseEvent) {
		const href = (e.currentTarget as HTMLAnchorElement).getAttribute('href');
		const hash = href?.split('#')[1];
		if (!hash) return;
		const el = document.getElementById(hash);
		if (!el) return;
		e.preventDefault();
		el.scrollIntoView({ behavior: 'smooth' });
	}
</script>

<svelte:window onscroll={handleScroll} />

<nav
	class="{isStatic
		? 'relative'
		: 'fixed top-0 right-0 left-0 z-50'} transition-colors duration-300 {over ? '' : 'bg-cream'}"
>
	{#if !minimal}
		<div
			class="absolute inset-x-0 bottom-0 h-px bg-cream-200 transition-opacity duration-300 {scrolled
				? 'opacity-100'
				: 'opacity-0'}"
		></div>
	{/if}
	<div class="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-5">
		<a
			href="/"
			class="group flex items-center gap-0 transition-colors md:gap-0.5 {over
				? 'text-white'
				: 'text-black dark:text-white'}"
		>
			<svg
				class="-mt-2.5 h-[18px] w-[18px] transition-transform duration-500 ease-out group-hover:rotate-45 md:-mt-2"
				viewBox="0 0 12 12"
				fill="none"
			>
				<line x1="6" y1="0.5" x2="6" y2="11.5" stroke="currentColor" stroke-width="1.5" />
				<line x1="1.24" y1="3.25" x2="10.76" y2="8.75" stroke="currentColor" stroke-width="1.5" />
				<line x1="1.24" y1="8.75" x2="10.76" y2="3.25" stroke="currentColor" stroke-width="1.5" />
			</svg>
			<span class="text-[22px] font-light tracking-tight">Superextra</span>
		</a>

		{#if !minimal}
			<div class="absolute left-1/2 hidden -translate-x-1/2 items-center gap-8 md:flex">
				<a
					href="/#intelligence"
					onclick={smoothScroll}
					class="text-sm transition-colors {over
						? 'text-white/60 hover:text-white'
						: 'text-black/60 hover:text-black dark:text-white/60 dark:hover:text-white'}"
					>Intelligence</a
				>
				<a
					href="/#use-cases"
					onclick={smoothScroll}
					class="text-sm transition-colors {over
						? 'text-white/60 hover:text-white'
						: 'text-black/60 hover:text-black dark:text-white/60 dark:hover:text-white'}"
					>Use Cases</a
				>
				<a
					href="/#faq"
					onclick={smoothScroll}
					class="text-sm transition-colors {over
						? 'text-white/60 hover:text-white'
						: 'text-black/60 hover:text-black dark:text-white/60 dark:hover:text-white'}">FAQ</a
				>
			</div>
		{/if}

		<div class="hidden items-center gap-3 md:flex">
			<a
				href="/login"
				class="cursor-pointer rounded-full border px-5 py-2 text-sm font-medium transition-all {over
					? 'border-white/15 text-white/70 hover:border-white/25 hover:text-white/90'
					: 'border-black/10 text-black/70 hover:border-black/15 hover:text-black/90 dark:border-white/10 dark:text-white/70 dark:hover:border-white/15 dark:hover:text-white/90'}"
				>Log In</a
			>
			<button onclick={() => formState.open()} class="cursor-pointer btn-primary px-5 py-2 text-sm"
				>Contact Us</button
			>
		</div>

		<div class="flex items-center gap-3 md:hidden">
			<a
				href="/login"
				class="cursor-pointer rounded-full border p-2 {over
					? 'border-white/15 text-white/40'
					: 'border-black/10 text-black/30 dark:border-white/10 dark:text-white/30'}"
				aria-label="Log In"
			>
				<svg
					class="h-4 w-4"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="1.5"
					><path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3-3h-9m9 0l-3-3m3 3l-3 3"
					/></svg
				>
			</a>
			<button
				onclick={() => formState.open()}
				class="cursor-pointer btn-primary px-4 py-1.5 text-sm">Contact Us</button
			>
			{#if !minimal}
				<button
					class={over ? 'text-white' : 'text-black dark:text-white'}
					onclick={() => (mobileOpen = !mobileOpen)}
					aria-label="Toggle menu"
				>
					{#if mobileOpen}
						<svg
							xmlns="http://www.w3.org/2000/svg"
							class="h-6 w-6"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							><path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="1.5"
								d="M6 18L18 6M6 6l12 12"
							/></svg
						>
					{:else}
						<svg
							xmlns="http://www.w3.org/2000/svg"
							class="h-6 w-6"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							><path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="1.5"
								d="M4 6h16M4 12h16M4 18h16"
							/></svg
						>
					{/if}
				</button>
			{/if}
		</div>
	</div>

	{#if !minimal}
		<div
			class="grid transition-[grid-template-rows] duration-300 md:hidden {mobileOpen
				? 'grid-rows-[1fr]'
				: 'grid-rows-[0fr]'}"
		>
			<div class="overflow-hidden">
				<div class="border-t border-cream-100 bg-cream">
					<div class="flex flex-col gap-4 px-6 py-6">
						<a
							href="/#intelligence"
							class="text-sm text-black/60 dark:text-white/60"
							onclick={(e) => {
								mobileOpen = false;
								smoothScroll(e);
							}}>Intelligence</a
						>
						<a
							href="/#use-cases"
							class="text-sm text-black/60 dark:text-white/60"
							onclick={(e) => {
								mobileOpen = false;
								smoothScroll(e);
							}}>Use Cases</a
						>
						<a
							href="/#faq"
							class="text-sm text-black/60 dark:text-white/60"
							onclick={(e) => {
								mobileOpen = false;
								smoothScroll(e);
							}}>FAQ</a
						>
					</div>
				</div>
			</div>
		</div>
	{/if}
</nav>
