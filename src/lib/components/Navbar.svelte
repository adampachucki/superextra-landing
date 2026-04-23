<script lang="ts">
	import { formState } from '$lib/form-state.svelte';
	import { chatState } from '$lib/chat-state.svelte';
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
	let chatCount = $derived(minimal ? chatState.sessionsList.length : 0);

	function smoothScroll(e: MouseEvent) {
		const href = (e.currentTarget as HTMLAnchorElement).getAttribute('href');
		const hash = href?.split('#')[1];
		if (!hash) return;
		const el = document.getElementById(hash);
		if (!el) return;
		e.preventDefault();
		el.scrollIntoView({ behavior: 'smooth' });
	}

	const iconBtnClass = $derived(
		`relative cursor-pointer rounded-full border p-2 transition-all duration-200 ${over ? 'border-white/[0.12] text-white/55 hover:border-white/[0.30] hover:text-white/75' : 'border-black/[0.12] text-black/55 hover:border-black/[0.30] hover:text-black/75 dark:border-white/[0.12] dark:text-white/55 dark:hover:border-white/[0.30] dark:hover:text-white/75'}`
	);
</script>

{#snippet chatIcon()}
	<a href="/agent/chat" class={iconBtnClass} aria-label="Chat history">
		<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
			<path d="M2 2h20v14H10l-2 4-2-4H2z" />
		</svg>
		{#if chatCount > 0}
			<span
				class="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-black px-0.5 text-[10px] font-medium text-white dark:bg-white dark:text-black"
				>{chatCount}</span
			>
		{/if}
	</a>
{/snippet}

<svelte:window onscroll={handleScroll} />

<nav
	class="{isStatic
		? 'relative'
		: 'fixed top-0 right-0 left-0 z-50'} transition-colors duration-300 {over ? '' : 'bg-cream'}"
>
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
			{#if minimal}
				{@render chatIcon()}
			{/if}
			{#if !minimal}
				<a
					href="/login"
					class="cursor-pointer px-5 py-2 {over
						? 'rounded-full border border-white/15 text-sm font-medium text-white/70 transition-all hover:border-white/25 hover:text-white/90'
						: 'btn-ghost'}">Log In</a
				>
			{/if}
			<button onclick={() => formState.open()} class="cursor-pointer btn-primary px-5 py-2 text-sm"
				>Contact Us</button
			>
		</div>

		<div class="flex items-center gap-3 md:hidden">
			{#if minimal}
				{@render chatIcon()}
			{/if}
			{#if !minimal}
				<a href="/login" class={iconBtnClass} aria-label="Log In">
					<svg
						class="h-4 w-4"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="1.5"><circle cx="12" cy="8" r="4" /><path d="M4 23a8 8 0 0 1 16 0" /></svg
					>
				</a>
			{/if}
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
