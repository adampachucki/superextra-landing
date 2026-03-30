<script lang="ts">
	import { goto, beforeNavigate } from '$app/navigation';
	import { onMount } from 'svelte';
	import Navbar from '$lib/components/Navbar.svelte';
	import ChatThread from '$lib/components/restaurants/ChatThread.svelte';
	import { chatState } from '$lib/chat-state.svelte';

	let inputEl: HTMLTextAreaElement | undefined = $state();
	let query = $state('');

	beforeNavigate(({ cancel }) => {
		if (chatState.active && chatState.messages.length > 0) {
			if (!confirm('Leave this conversation? Your chat history will be lost.')) {
				cancel();
			}
		}
	});

	onMount(() => {
		if (chatState.active) inputEl?.focus();

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

<Navbar minimal />

<div class="fixed inset-0 flex justify-center bg-cream pt-20">
	<div class="flex w-full max-w-[1000px]">
		<!-- Left panel (hidden on mobile) -->
		<aside class="hidden w-48 shrink-0 px-3 py-4 lg:block">
			<button onclick={handleNewChat} class="mb-6 flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-[13px] text-black/50 transition-colors hover:bg-cream-100 hover:text-black/70 dark:text-white/50 dark:hover:bg-cream-50 dark:hover:text-white/70">
				<svg class="h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
				</svg>
				New chat
			</button>

			{#if chatState.placeContext}
				<div class="mb-4">
					<p class="mb-2 text-[11px] font-medium tracking-wide text-black/25 dark:text-white/25">CONTEXT</p>
					<div class="flex items-start gap-2">
						<svg class="mt-0.5 h-3.5 w-3.5 shrink-0 text-black/30 dark:text-white/30" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.75">
							<path stroke-linecap="square" stroke-linejoin="miter" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
							<path stroke-linecap="square" stroke-linejoin="miter" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
						</svg>
						<div class="min-w-0">
							<p class="truncate text-[13px] text-black/70 dark:text-white/70">{chatState.placeContext.name}</p>
							{#if chatState.placeContext.secondary}
								<p class="truncate text-[11px] text-black/30 dark:text-white/30">{chatState.placeContext.secondary}</p>
							{/if}
						</div>
					</div>
				</div>
			{/if}
		</aside>

		<!-- Main chat area -->
		<div class="flex min-w-0 flex-1 flex-col">
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
				<!-- Mobile: place context + new chat (visible only on small screens) -->
				{#if chatState.placeContext}
					<div class="mb-2 flex items-center gap-2 lg:hidden">
						<svg class="h-3 w-3 shrink-0 text-black/30 dark:text-white/30" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.75">
							<path stroke-linecap="square" stroke-linejoin="miter" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
							<path stroke-linecap="square" stroke-linejoin="miter" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
						</svg>
						<span class="truncate text-[12px] text-black/40 dark:text-white/40">{chatState.placeContext.name}</span>
						<button onclick={handleNewChat} class="ml-auto cursor-pointer whitespace-nowrap text-[12px] text-black/25 transition-colors hover:text-black/50 dark:text-white/25 dark:hover:text-white/50">
							New chat
						</button>
					</div>
				{/if}
				<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
				<div onclick={() => inputEl?.focus()} class="cursor-text prompt-card rounded-2xl border border-black/[0.06] bg-white transition-colors focus-within:border-black/[0.12] dark:border-white/[0.06] dark:bg-cream-50 dark:focus-within:border-white/[0.12]">
					<div class="px-5 pt-4">
						<textarea
							bind:this={inputEl}
							bind:value={query}
							onkeydown={handleKeydown}
							placeholder="Ask a follow-up..."
							rows="1"
							class="w-full resize-none border-0 bg-transparent text-[15px] leading-relaxed text-black placeholder:text-black/25 focus:outline-none dark:text-white dark:placeholder:text-white/25"
						></textarea>
					</div>
					<div class="flex items-center justify-end px-4 pb-4">
						<button
							onclick={handleSend}
							disabled={!query.trim() || chatState.loading}
							aria-label="Send"
							class="shrink-0 cursor-pointer rounded-full bg-black p-2 transition-colors hover:bg-black/80 disabled:cursor-default disabled:opacity-20 dark:bg-white dark:hover:bg-white/80"
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
</style>
