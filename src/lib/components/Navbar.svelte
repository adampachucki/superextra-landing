<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { getLocale, localizeHref } from '$lib/paraglide/runtime';
	import { formState } from '$lib/form-state.svelte';
	import { chatState } from '$lib/chat-state.svelte';
	import { auth } from '$lib/auth.svelte';
	import AccountMenu from '$lib/components/agent/AccountMenu.svelte';
	import Mark from '$lib/components/Mark.svelte';
	import * as m from '$lib/paraglide/messages';
	import { onMount } from 'svelte';

	let { transparent = false }: { transparent?: boolean } = $props();

	let scrolled = $state(false);

	function handleScroll() {
		scrolled = window.scrollY > 20;
	}

	onMount(() => {
		handleScroll();
		void auth.init();
	});

	let over = $derived(transparent && !scrolled);
	// The logo always points at the agent home (the canonical site). On the home
	// route itself it just scrolls to top; on every other page it navigates there.
	const homeHref = $derived(
		`https://agent.superextra.ai${localizeHref('/', { locale: getLocale() })}`
	);
	// Only count sessions once the user is signed in — touching sessionsList
	// kicks the listener attach, but the count is 0 for signed-out users so
	// the badge stays hidden.
	let chatCount = $derived(auth.user ? chatState.sessionsList.length : 0);

	function handleLoginClick() {
		auth.openModal({
			afterSignIn: () => {
				goto('/chat');
			}
		});
	}

	const chatIconClass = $derived(
		`relative mr-2 p-1 transition-colors duration-200 ${over ? 'text-white/70 hover:text-white' : 'text-black/70 hover:text-black dark:text-white/70 dark:hover:text-white'}`
	);
</script>

{#snippet chatIcon()}
	<a href="/chat" class={chatIconClass} aria-label={m.nav_chat_history()}>
		<svg
			class="h-6 w-6 translate-y-0.5"
			fill="none"
			viewBox="0 0 24 24"
			stroke="currentColor"
			stroke-width="1"
		>
			<path d="M2.5 2.5h19v13H10l-2 4-2-4H2.5z" />
		</svg>
		{#if chatCount > 0}
			<span
				class="absolute top-0 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-black px-1 text-[10px] font-medium text-white dark:bg-white dark:text-black"
				>{chatCount}</span
			>
		{/if}
	</a>
{/snippet}

{#snippet actions(demoClass: string)}
	{#if auth.user}
		{@render chatIcon()}
		<AccountMenu />
	{:else}
		<button
			onclick={handleLoginClick}
			class="text-sm transition-colors {over
				? 'text-white/80 hover:text-white'
				: 'text-black/70 hover:text-black dark:text-white/70 dark:hover:text-white'}"
		>
			{m.nav_sign_in()}
		</button>
	{/if}
	<button onclick={() => formState.open()} class="btn-primary {demoClass} text-sm whitespace-nowrap"
		>{m.nav_book_demo()}</button
	>
{/snippet}

<svelte:window onscroll={handleScroll} />

<nav
	class="fixed top-0 right-0 left-0 z-50 transition-colors duration-300 {over ? '' : 'bg-cream'}"
>
	<div class="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-5">
		<a
			href={homeHref}
			onclick={(e) => {
				if (page.route.id !== '/') return;
				e.preventDefault();
				window.scrollTo({ top: 0, behavior: 'smooth' });
			}}
			class="group flex items-center gap-0 transition-colors md:gap-0.5 {over
				? 'text-white'
				: 'text-black dark:text-white'}"
		>
			<Mark
				class="-mt-2.5 h-[18px] w-[18px] transition-transform duration-500 ease-out group-hover:rotate-45 md:-mt-2"
			/>
			<span class="text-[22px] font-light tracking-tight">Superextra</span>
		</a>

		<div class="hidden items-center gap-3 md:flex">
			{@render actions('px-5 py-2')}
		</div>

		<div class="flex items-center gap-3 md:hidden">
			{@render actions('px-4 py-1.5')}
		</div>
	</div>
</nav>
