<script lang="ts">
	import { goto, beforeNavigate } from '$app/navigation';
	import { onMount } from 'svelte';
	import ChatThread from '$lib/components/restaurants/ChatThread.svelte';
	import { chatState } from '$lib/chat-state.svelte';
	import { theme } from '$lib/theme.svelte';

	let inputEl: HTMLTextAreaElement | undefined = $state();
	let query = $state('');
	let sidebarOpen = $state(false);
	let isDesktop = $state(false);

	$effect(() => {
		const mq = window.matchMedia('(min-width: 1024px)');
		isDesktop = mq.matches;
		const handler = (e: MediaQueryListEvent) => { isDesktop = e.matches; };
		mq.addEventListener('change', handler);
		return () => mq.removeEventListener('change', handler);
	});

	function toggleSidebar() {
		sidebarOpen = !sidebarOpen;
	}

	beforeNavigate(({ cancel }) => {
		if (chatState.active && chatState.messages.length > 0) {
			if (!confirm('Leave this conversation? Your chat history will be lost.')) {
				cancel();
			}
		}
	});

	onMount(() => {
		const onBeforeUnload = (e: BeforeUnloadEvent) => {
			if (chatState.active && chatState.messages.length > 0) {
				e.preventDefault();
			}
		};
		addEventListener('beforeunload', onBeforeUnload);
		return () => removeEventListener('beforeunload', onBeforeUnload);
	});

	function handleSend() {
		const trimmed = query.trim();
		if (!trimmed || chatState.loading) return;
		chatState.send(trimmed);
		query = '';
		resizeTextarea();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSend();
		}
	}

	function resizeTextarea() {
		if (inputEl) {
			inputEl.style.height = 'auto';
			inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
		}
	}

	$effect(() => {
		query;
		resizeTextarea();
	});

	function handleNewChat() {
		chatState.reset();
		goto('/agent');
	}
</script>

<svelte:head>
	<title>Chat - Superextra</title>
	<meta name="description" content="Ask questions about your restaurant market. Powered by Superextra." />
</svelte:head>

<div class="fixed inset-0 flex bg-cream">
	<!-- Sidebar -->
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div
		class="sidebar-overlay fixed inset-0 z-40 bg-black/20 {!isDesktop && sidebarOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'}"
		onclick={() => (sidebarOpen = false)}
	></div>
	<aside class="sidebar flex w-64 shrink-0 flex-col border-r border-black/[0.06] bg-cream dark:border-white/[0.06] {isDesktop ? 'relative' : 'fixed inset-y-0 left-0 z-50'} {sidebarOpen ? '' : isDesktop ? '-ml-64' : '-translate-x-full'}">
		<!-- Logo + toggle -->
		<div class="flex items-center justify-between px-6 py-5">
			<div class="group flex cursor-default items-center gap-0.5 text-black dark:text-white">
				<svg class="h-[18px] w-[18px] -mt-2.5 md:-mt-2 transition-transform duration-500 ease-out group-hover:rotate-45" viewBox="0 0 12 12" fill="none">
					<line x1="6" y1="0.5" x2="6" y2="11.5" stroke="currentColor" stroke-width="1.5"/>
					<line x1="1.24" y1="3.25" x2="10.76" y2="8.75" stroke="currentColor" stroke-width="1.5"/>
					<line x1="1.24" y1="8.75" x2="10.76" y2="3.25" stroke="currentColor" stroke-width="1.5"/>
				</svg>
				<span class="text-[22px] font-light tracking-tight">Superextra</span>
			</div>
			<button onclick={toggleSidebar} aria-label="Close sidebar" class="cursor-pointer text-black/30 transition-colors hover:text-black/50 dark:text-white/30 dark:hover:text-white/50">
				<svg class="h-5 w-5" viewBox="0 0 24 24" fill="none">
					<rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" stroke-width="1.5" />
					<line x1="9" y1="4" x2="9" y2="20" stroke="currentColor" stroke-width="1.5" />
				</svg>
			</button>
		</div>

		<!-- Panel content -->
		<div class="flex-1 overflow-y-auto px-5 py-2">
			<button onclick={handleNewChat} class="mb-6 flex w-full cursor-pointer items-center gap-2 rounded-lg bg-cream-100 px-2 py-1.5 text-[13px] text-black/70 transition-colors hover:bg-cream-200 hover:text-black dark:bg-cream-50 dark:text-white/70 dark:hover:bg-cream-100 dark:hover:text-white">
				<svg class="h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
				</svg>
				New chat
			</button>

			{#if chatState.placeContext}
				<div class="mb-4">
					<p class="mb-2 text-[11px] font-medium tracking-wide text-black/40 dark:text-white/40">CONTEXT</p>
					<div class="min-w-0">
						<p class="truncate text-[14px] text-black/80 dark:text-white/80">{chatState.placeContext.name}</p>
						{#if chatState.placeContext.secondary}
							<p class="truncate text-[12px] text-black/50 dark:text-white/50">{chatState.placeContext.secondary}</p>
						{/if}
					</div>
				</div>
			{/if}
		</div>

		<!-- Footer -->
		<div class="border-t border-black/[0.06] px-5 py-4 dark:border-white/[0.06]">
			<div class="flex items-center gap-4">
				<a href="/privacy-policy" class="text-[12px] text-black/40 transition-colors hover:text-black/60 dark:text-white/40 dark:hover:text-white/60">Privacy</a>
				<a href="/terms" class="text-[12px] text-black/40 transition-colors hover:text-black/60 dark:text-white/40 dark:hover:text-white/60">Terms</a>
				<button
					onclick={() => theme.cycle()}
					class="ml-auto cursor-pointer text-black/30 transition-colors hover:text-black/50 dark:text-white/30 dark:hover:text-white/50"
					aria-label="Toggle theme"
				>
					{#if theme.mode === 'dark'}
						<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" /></svg>
					{:else if theme.mode === 'light'}
						<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="4" /><path stroke-linecap="round" d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41m11.32-11.32l1.41-1.41" /></svg>
					{:else}
						<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25A2.25 2.25 0 015.25 3h13.5A2.25 2.25 0 0121 5.25z" /></svg>
					{/if}
				</button>
			</div>
			<p class="mt-2 text-[11px] text-black/25 dark:text-white/25">&copy; {new Date().getFullYear()} Superextra</p>
		</div>
	</aside>

	<!-- Main area -->
	<div class="relative flex min-w-0 flex-1 flex-col">
		<!-- Floating sidebar toggle (when closed) -->
		<button onclick={toggleSidebar} aria-label="Open sidebar" class="toggle-float absolute left-4 top-4 z-30 flex h-9 w-9 cursor-pointer items-center justify-center rounded-full bg-white/60 backdrop-blur-md text-black/40 transition-all hover:bg-white/80 hover:text-black/60 dark:bg-white/10 dark:backdrop-blur-md dark:text-white/40 dark:hover:bg-white/20 dark:hover:text-white/60 {sidebarOpen ? 'pointer-events-none opacity-0' : 'opacity-100'}">
			<svg class="h-5 w-5" viewBox="0 0 24 24" fill="none">
				<rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" stroke-width="1.5" />
				<line x1="9" y1="4" x2="9" y2="20" stroke="currentColor" stroke-width="1.5" />
			</svg>
		</button>

		<!-- Chat thread -->
		{#if chatState.active}
			<ChatThread />
		{:else}
			<div class="flex flex-1 items-center justify-center">
				<div class="text-center">
					<p class="text-[14px] text-black/30 dark:text-white/30">No active conversation.</p>
					<a href="/agent" class="mt-3 inline-block text-[13px] text-black/50 underline transition-colors hover:text-black/70 dark:text-white/50 dark:hover:text-white/70">Start a new chat</a>
				</div>
			</div>
		{/if}

		<!-- Input bar -->
		<div class="relative">
			<div class="pointer-events-none absolute inset-x-0 -top-8 h-8 bg-gradient-to-t from-[var(--color-cream)]/80 to-transparent"></div>
			<div class="relative z-10 bg-cream">
			<div class="mx-auto max-w-[800px] px-4 pb-3 md:px-6">
				<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
				<div onclick={() => chatState.active && inputEl?.focus()} class="{chatState.active ? 'cursor-text' : 'cursor-not-allowed'} prompt-card rounded-2xl border border-black/[0.06] bg-white transition-colors focus-within:border-black/[0.35] dark:border-white/[0.06] dark:bg-cream-50 dark:focus-within:border-white/[0.35]">
					<div class="px-5 pt-4">
						<textarea
							bind:this={inputEl}
							bind:value={query}
							onkeydown={handleKeydown}
							placeholder="Ask a follow-up..."
							rows="1"
							disabled={!chatState.active}
							class="w-full resize-none border-0 bg-transparent text-[15px] leading-relaxed text-black placeholder:text-black/45 focus:outline-none disabled:cursor-not-allowed dark:text-white dark:placeholder:text-white/45"
						></textarea>
					</div>
					<div class="flex items-center justify-end px-4 pb-4">
						<button
							onclick={handleSend}
							disabled={!chatState.active || !query.trim() || chatState.loading}
							aria-label="Send"
							class="shrink-0 cursor-pointer rounded-full bg-black p-2 transition-colors hover:bg-black/80 disabled:cursor-not-allowed disabled:opacity-20 dark:bg-white dark:hover:bg-white/80"
						>
							<svg class="h-4 w-4 text-white dark:text-black" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
							</svg>
						</button>
					</div>
				</div>
				<p class="mt-2 text-center text-[11px] text-black/20 dark:text-white/20">
					Superextra may make mistakes.
				</p>
			</div>
		</div>
		</div>
	</div>
</div>

<style>
	.prompt-card {
		box-shadow:
			0 1px 2px rgba(0, 0, 0, 0.02),
			0 8px 32px rgba(0, 0, 0, 0.06);
	}

	:global(.dark) .prompt-card {
		box-shadow:
			0 1px 2px rgba(0, 0, 0, 0.1),
			0 8px 32px rgba(0, 0, 0, 0.3);
	}

	.sidebar {
		transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), margin-left 0.3s cubic-bezier(0.16, 1, 0.3, 1);
		will-change: transform;
	}

	.sidebar-overlay {
		transition: opacity 0.3s ease;
	}

	.toggle-float {
		transition: opacity 0.2s ease;
	}
</style>
