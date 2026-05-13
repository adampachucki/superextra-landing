<script lang="ts">
	import { onMount, tick } from 'svelte';
	import ChatThread from '$lib/components/restaurants/ChatThread.svelte';
	import RestaurantPromptComposer from '$lib/components/restaurants/RestaurantPromptComposer.svelte';
	import { chatState } from '$lib/chat-state.svelte';
	import { theme } from '$lib/theme.svelte';
	import { dictation } from '$lib/dictation.svelte';
	import type { PlaceSuggestion } from '$lib/place-search.svelte';
	import { formatRelativeTime } from '$lib/format-time';

	let inputEl: HTMLTextAreaElement | undefined = $state();
	let query = $state('');
	let composerResetKey = $state(0);
	let sidebarOpen = $state(false);
	let prevSidebarOpen = $state(false);
	let toggleBtnAnim = $state<'idle' | 'fade-out' | 'plop-in'>('idle');
	let isDesktop = $state(false);
	let isMobile = $state(false);
	let mounted = $state(false);
	let relativeNow = $state(Date.now());
	let sidebarContentVisible = $derived(sidebarOpen && mounted);
	let activePromptPosting = $state(false);
	let activePromptPostMessageCount = $state(0);
	let activePromptInactive = $derived(
		chatState.active && (chatState.loading || activePromptPosting)
	);

	$effect(() => {
		if (!mounted) return;
		if (sidebarOpen && !prevSidebarOpen) {
			// Sidebar opening — button fades out quickly
			toggleBtnAnim = 'fade-out';
		} else if (!sidebarOpen && prevSidebarOpen) {
			// Sidebar closing — button plops in after panel is gone
			toggleBtnAnim = 'plop-in';
		}
		prevSidebarOpen = sidebarOpen;
	});

	$effect(() => {
		if (!activePromptPosting) return;
		if (
			!chatState.active ||
			chatState.loading ||
			chatState.messages.length > activePromptPostMessageCount
		) {
			activePromptPosting = false;
		}
	});

	$effect(() => {
		const mq = window.matchMedia('(min-width: 1024px)');
		isDesktop = mq.matches;
		const handler = (e: MediaQueryListEvent) => {
			isDesktop = e.matches;
		};
		mq.addEventListener('change', handler);
		return () => mq.removeEventListener('change', handler);
	});

	$effect(() => {
		const mq = window.matchMedia('(max-width: 767px)');
		isMobile = mq.matches;
		const handler = (e: MediaQueryListEvent) => {
			isMobile = e.matches;
		};
		mq.addEventListener('change', handler);
		return () => mq.removeEventListener('change', handler);
	});

	function toggleSidebar() {
		sidebarOpen = !sidebarOpen;
	}

	// Lock body scroll when sidebar open on mobile
	$effect(() => {
		if (isDesktop || !sidebarOpen) return;
		document.body.style.overflow = 'hidden';
		return () => (document.body.style.overflow = '');
	});

	onMount(() => {
		relativeNow = Date.now();
		const relativeTimer = setInterval(() => {
			relativeNow = Date.now();
		}, 30_000);

		// Sign the visitor into Firebase anonymously in the background. Downstream
		// phases (Firestore session/event reads, ID-token-verified Cloud Function
		// calls) wait on the resolved UID via `ensureAnonAuth()`. Dynamic import
		// keeps Firebase out of routes that don't need it.
		import('$lib/firebase')
			.then(({ ensureAnonAuth }) => ensureAnonAuth())
			.catch((err) => {
				console.warn('Anonymous auth bootstrap failed:', err);
			});

		const params = new URL(window.location.href).searchParams;
		const sid = params.get('sid');
		const q = params.get('q');
		if (q) {
			const placeContext =
				params.get('placeId') && params.get('placeName')
					? {
							placeId: params.get('placeId')!,
							name: params.get('placeName')!,
							secondary: params.get('placeSecondary') ?? ''
						}
					: null;
			const trimmedQ = q?.trim();
			if (trimmedQ) {
				chatState.startNewChat(trimmedQ, placeContext);
				const clean = new URL(window.location.href);
				clean.searchParams.delete('q');
				clean.searchParams.delete('placeName');
				clean.searchParams.delete('placeSecondary');
				clean.searchParams.delete('placeId');
				history.replaceState(history.state, '', clean);
			}
		} else if (sid) {
			chatState.selectSession(sid);
		}
		sidebarOpen = window.matchMedia('(min-width: 1024px)').matches;
		prevSidebarOpen = sidebarOpen;
		tick().then(() => {
			mounted = true;
		});
		return () => clearInterval(relativeTimer);
	});

	// Keep URL in sync with active session
	$effect(() => {
		if (!mounted) return;
		const url = new URL(window.location.href);
		if (chatState.activeSid) {
			url.searchParams.set('sid', chatState.activeSid);
		} else {
			url.searchParams.delete('sid');
		}
		if (url.href !== window.location.href) {
			history.replaceState(history.state, '', url);
		}
	});

	async function handleSend() {
		const trimmed = query.trim();
		if (!chatState.active || !trimmed || activePromptInactive) return;
		sendError = null;
		if (dictation.active) dictation.stop();
		activePromptPostMessageCount = chatState.messages.length;
		activePromptPosting = true;
		query = '';
		resizeTextarea();
		try {
			await chatState.sendFollowUp(trimmed);
		} catch (err) {
			activePromptPosting = false;
			query = trimmed;
			resizeTextarea();
			sendError = err instanceof Error ? err.message : 'Could not send message. Please try again.';
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSend();
		}
	}

	function focusPromptFromCardClick(e: MouseEvent) {
		if (e.target instanceof Element && e.target.closest('button, input, textarea, a')) return;
		if (!activePromptInactive) {
			try {
				inputEl?.focus({ preventScroll: true });
			} catch {
				inputEl?.focus();
			}
		}
	}

	// --- Dictation ---
	let dictationBase = '';

	function handleDictation() {
		if (!chatState.active || activePromptInactive) return;
		if (dictation.active) {
			dictation.stop();
			return;
		}
		dictationBase = query;
		dictation.toggle();
	}

	$effect(() => {
		if (chatState.active && dictation.active) {
			const t = dictation.text;
			const space = dictationBase && t && !dictationBase.endsWith(' ') ? ' ' : '';
			query = dictationBase + space + t;
		}
	});

	$effect(() => {
		if (chatState.active && activePromptInactive && dictation.active) dictation.stop();
	});

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
		query = '';
		composerResetKey++;
	}

	function handleNewChatSubmit({ query, place }: { query: string; place: PlaceSuggestion }) {
		sendError = null;
		chatState.startNewChat(query, place);
	}

	// --- Request-action error state (Fix 1: surface transport failures) ---
	let sendError = $state<string | null>(null);
	let deleteError = $state<string | null>(null);

	let confirmDeleteId = $state<string | null>(null);
	let deletingId = $state<string | null>(null);

	function handleWindowClick(e: MouseEvent) {
		if (!confirmDeleteId || deletingId) return;
		const target = e.target as HTMLElement;
		if (!target.closest('.sb-item')) confirmDeleteId = null;
	}

	async function performDelete(sid: string) {
		if (deletingId) return;
		deleteError = null;
		deletingId = sid;
		try {
			await chatState.deleteSession(sid);
			confirmDeleteId = null;
		} catch (err) {
			deleteError = err instanceof Error ? err.message : 'Could not delete. Please try again.';
		} finally {
			deletingId = null;
		}
	}
</script>

<svelte:window onclick={handleWindowClick} />

<svelte:head>
	<title>Chat - Superextra</title>
	<meta
		name="description"
		content="Ask questions about your restaurant market. Powered by Superextra."
	/>
</svelte:head>

<!-- Floating sidebar toggle (outside chat-enter to avoid transform containing block) -->
<button
	onclick={toggleSidebar}
	onanimationend={() => (toggleBtnAnim = 'idle')}
	aria-label="Open sidebar"
	class="toggle-float fixed top-[max(1rem,env(safe-area-inset-top))] left-[max(1rem,env(safe-area-inset-left))] z-30 flex h-9 w-9 items-center justify-center rounded-full bg-black text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80
	{sidebarOpen ? 'pointer-events-none' : ''}
	{toggleBtnAnim === 'fade-out'
		? 'toggle-out'
		: toggleBtnAnim === 'plop-in'
			? 'toggle-plop'
			: !sidebarOpen && mounted
				? 'scale-100 opacity-100'
				: 'scale-75 opacity-0'}"
>
	<svg class="h-5 w-5" viewBox="0 0 24 24" fill="none">
		<rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" stroke-width="1.5" />
		<line x1="9" y1="4" x2="9" y2="20" stroke="currentColor" stroke-width="1.5" />
	</svg>
</button>

{#if !isDesktop && sidebarOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-40 touch-none bg-[var(--color-cream)]/60"
		onclick={() => (sidebarOpen = false)}
	></div>
{/if}
<aside
	class="sidebar fixed top-0 left-0 z-50 flex h-dvh w-64 flex-col overflow-y-auto overscroll-y-contain border-r border-black/[0.06] bg-cream pt-[env(safe-area-inset-top)] dark:border-white/[0.06] {mounted
		? 'animated'
		: ''} {sidebarOpen ? '' : '-translate-x-full'}"
>
	<!-- Logo + toggle -->
	<div
		class="sb-item flex items-center justify-between px-6 py-5"
		style="--sb-delay: 0.15s"
		class:visible={sidebarContentVisible}
	>
		<a
			href="/agent"
			class="group flex items-center gap-0.5 text-black no-underline dark:text-white"
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
		<button
			onclick={toggleSidebar}
			aria-label="Close sidebar"
			class="flex h-9 w-9 items-center justify-center rounded-full text-black/40 transition-all duration-200 hover:bg-black/[0.06] hover:text-black/60 dark:text-white/40 dark:hover:bg-white/[0.06] dark:hover:text-white/60"
		>
			<svg class="h-5 w-5" viewBox="0 0 24 24" fill="none">
				<rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" stroke-width="1.5" />
				<line x1="9" y1="4" x2="9" y2="20" stroke="currentColor" stroke-width="1.5" />
			</svg>
		</button>
	</div>

	<!-- Panel content -->
	<div class="flex-1 overflow-y-auto px-5 py-2">
		<button
			onclick={() => {
				handleNewChat();
				if (!isDesktop) sidebarOpen = false;
			}}
			class="sb-item mb-6 flex w-full items-center gap-2 rounded-lg bg-cream-100 px-2 py-1.5 text-[13px] text-black/70 transition-colors hover:bg-cream-200 hover:text-black dark:bg-cream-50 dark:text-white/70 dark:hover:bg-cream-100 dark:hover:text-white"
			style="--sb-delay: 0.25s"
			class:visible={sidebarContentVisible}
		>
			<svg
				class="h-3.5 w-3.5"
				xmlns="http://www.w3.org/2000/svg"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				stroke-width="2"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
			</svg>
			New chat
		</button>

		{#if chatState.sessionsList.length > 0}
			<p
				class="sb-item mb-2 text-[11px] font-medium tracking-wide text-black/40 dark:text-white/40"
				style="--sb-delay: 0.32s"
				class:visible={sidebarContentVisible}
			>
				CONVERSATIONS
			</p>
			<div class="flex flex-col gap-0.5">
				{#each chatState.sessionsList as sess, i (sess.sid)}
					{@const canDeleteRow = sess.userId === chatState.currentUid}
					{@const isDeleting = deletingId === sess.sid}
					<div
						class="sb-item group relative transition-opacity duration-200 {isDeleting
							? 'opacity-60'
							: ''}"
						style="--sb-delay: {Math.min(0.38 + i * 0.05, 0.7)}s"
						class:visible={sidebarContentVisible}
						aria-busy={isDeleting ? 'true' : undefined}
					>
						<button
							onclick={() => {
								if (isDeleting) return;
								if (confirmDeleteId && confirmDeleteId !== sess.sid) {
									confirmDeleteId = null;
									deleteError = null;
								}
								if (confirmDeleteId === sess.sid) return;
								chatState.selectSession(sess.sid);
								if (!isDesktop) sidebarOpen = false;
							}}
							class="w-full rounded-lg px-2 py-2 pr-8 text-left transition-colors {sess.sid ===
							chatState.activeSid
								? 'bg-cream-100 dark:bg-cream-100'
								: confirmDeleteId === sess.sid
									? 'bg-cream-100/50 dark:bg-cream-50/50'
									: 'hover:bg-cream-100/50 dark:hover:bg-cream-50/50'}"
						>
							<p
								class="truncate text-[13px] {sess.sid === chatState.activeSid
									? 'text-black dark:text-white'
									: 'text-black/70 dark:text-white/70'}"
							>
								{sess.title ?? 'Untitled chat'}
							</p>
							<div class="relative mt-0.5 text-[11px]">
								<div
									class="flex items-center gap-1.5 transition-opacity duration-150 {confirmDeleteId ===
									sess.sid
										? 'pointer-events-none opacity-0'
										: 'opacity-100'}"
								>
									{#if sess.placeContext}
										<span class="truncate text-black/40 dark:text-white/40">
											{sess.placeContext.name}
										</span>
										<span class="text-black/20 dark:text-white/20">&middot;</span>
									{/if}
									<span class="shrink-0 text-black/30 dark:text-white/30">
										{sess.updatedAtMs ? formatRelativeTime(sess.updatedAtMs, relativeNow) : ''}
									</span>
								</div>
								<div
									class="absolute inset-0 flex items-center gap-1.5 transition-all duration-150 {confirmDeleteId ===
									sess.sid
										? 'translate-x-0 opacity-100'
										: 'pointer-events-none -translate-x-1.5 opacity-0'}"
								>
									{#if isDeleting}
										<span class="deleting-indicator text-black/60 dark:text-white/60"
											>Deleting…</span
										>
									{:else}
										<span
											role="button"
											tabindex="0"
											onclick={(e) => {
												e.stopPropagation();
												void performDelete(sess.sid);
											}}
											onkeydown={(e) => {
												if (e.key === 'Enter' || e.key === ' ') {
													e.preventDefault();
													e.stopPropagation();
													void performDelete(sess.sid);
												}
											}}
											class="text-red-500 transition-colors hover:text-red-600 dark:text-red-400 dark:hover:text-red-300"
											>Delete</span
										>
										<span class="text-black/20 dark:text-white/20">&middot;</span>
										<span
											role="button"
											tabindex="0"
											onclick={(e) => {
												e.stopPropagation();
												confirmDeleteId = null;
												deleteError = null;
											}}
											onkeydown={(e) => {
												if (e.key === 'Enter' || e.key === ' ') {
													e.preventDefault();
													e.stopPropagation();
													confirmDeleteId = null;
													deleteError = null;
												}
											}}
											class="text-black/40 transition-colors hover:text-black/60 dark:text-white/40 dark:hover:text-white/60"
											>Cancel</span
										>
									{/if}
								</div>
							</div>
							{#if confirmDeleteId === sess.sid && deleteError && !isDeleting}
								<div
									class="mt-1 truncate text-[11px] text-red-600 dark:text-red-400"
									role="alert"
								>
									{deleteError}
								</div>
							{/if}
						</button>
						{#if canDeleteRow}
							<button
								onclick={() => {
								confirmDeleteId = sess.sid;
								deleteError = null;
							}}
								aria-label="Delete conversation"
								class="absolute top-1/2 right-1 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full transition-opacity hover:bg-black/[0.06] dark:hover:bg-white/[0.06] {confirmDeleteId ===
								sess.sid
									? 'hidden'
									: sess.sid === chatState.activeSid
										? 'lg:opacity-0 lg:group-hover:opacity-100'
										: 'max-lg:hidden lg:opacity-0 lg:group-hover:opacity-100'}"
							>
								<svg
									class="h-3 w-3 text-black/30 dark:text-white/30"
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
									stroke-width="2"
								>
									<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
								</svg>
							</button>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Footer -->
	<div
		class="sb-item border-t border-black/[0.06] px-5 py-4 dark:border-white/[0.06]"
		style="--sb-delay: 0.45s"
		class:visible={sidebarContentVisible}
	>
		<div class="flex items-center gap-4">
			<a
				href="/privacy-policy"
				class="text-[12px] text-black/50 transition-colors hover:text-black/70 dark:text-white/50 dark:hover:text-white/70"
				>Privacy</a
			>
			<a
				href="/terms"
				class="text-[12px] text-black/50 transition-colors hover:text-black/70 dark:text-white/50 dark:hover:text-white/70"
				>Terms</a
			>
			<button
				onclick={() => theme.cycle()}
				class="ml-auto text-black/40 transition-colors hover:text-black/60 dark:text-white/40 dark:hover:text-white/60"
				aria-label="Toggle theme"
			>
				{#if theme.mode === 'dark'}
					<svg
						class="h-4 w-4"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="1.5"
						><path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"
						/></svg
					>
				{:else if theme.mode === 'light'}
					<svg
						class="h-4 w-4"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="1.5"
						><circle cx="12" cy="12" r="4" /><path
							stroke-linecap="round"
							d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41m11.32-11.32l1.41-1.41"
						/></svg
					>
				{:else}
					<svg
						class="h-4 w-4"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="1.5"
						><path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25A2.25 2.25 0 015.25 3h13.5A2.25 2.25 0 0121 5.25z"
						/></svg
					>
				{/if}
			</button>
		</div>
		<p class="mt-2 text-[11px] text-black/35 dark:text-white/35">
			&copy; {new Date().getFullYear()} Superextra
		</p>
	</div>
</aside>

<div class="chat-enter relative min-h-dvh {mounted ? 'is-mounted' : ''}">
	<!-- Main area (flows in document, page-level scroll) -->
	<div
		class="relative min-h-dvh pb-40 transition-[padding-left] duration-300 ease-out {isDesktop &&
		sidebarOpen
			? 'pl-64'
			: ''}"
	>
		{#if chatState.loadState === 'missing'}
			<div
				class="chat-thread-enter flex min-h-dvh items-center justify-center {mounted
					? 'is-mounted'
					: ''}"
			>
				<p class="text-[14px] text-black/40 dark:text-white/40">
					{chatState.active ? "Couldn't load this chat" : "Couldn't start this chat"}
				</p>
			</div>
		{:else if chatState.active}
			<div class="chat-thread-enter {mounted ? 'is-mounted' : ''}">
				<ChatThread />
			</div>
		{:else}
			<div
				class="chat-thread-enter flex min-h-dvh items-center justify-center {mounted
					? 'is-mounted'
					: ''}"
			>
				<p class="text-[14px] text-black/40 dark:text-white/40">Start a new conversation below</p>
			</div>
		{/if}
	</div>
</div>

<!-- Input bar (fixed, outside chat-enter) -->
<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div
	class="fixed right-0 bottom-0 left-0 z-20 bg-[var(--color-cream)] transition-[left] duration-300 ease-out {isDesktop &&
	sidebarOpen
		? 'left-64'
		: ''}"
>
	<div
		class="pointer-events-none absolute inset-x-0 -top-8 h-8 bg-gradient-to-t from-[var(--color-cream)]/60 to-transparent"
	></div>
	<div class="mx-auto max-w-[800px] px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] md:px-6">
		{#if sendError}
			<div class="mb-2 px-1 text-[13px] text-red-600 dark:text-red-400" role="alert">
				{sendError}
			</div>
		{/if}
		{#if chatState.active}
			<div
				onclick={focusPromptFromCardClick}
				aria-disabled={activePromptInactive}
				class="prompt-card rounded-2xl border border-black/[0.12] bg-white transition-colors focus-within:border-black/[0.55] dark:border-white/[0.12] dark:bg-cream-50 dark:focus-within:border-white/[0.55] {activePromptInactive
					? 'cursor-not-allowed'
					: 'cursor-text'}"
			>
				<div class="px-5 pt-4">
					<textarea
						bind:this={inputEl}
						bind:value={query}
						onkeydown={handleKeydown}
						disabled={activePromptInactive}
						placeholder={activePromptInactive
							? 'Awaiting final response...'
							: dictation.active
								? 'Start speaking...'
								: 'Ask a follow-up...'}
						rows="1"
						class="w-full resize-none border-0 bg-transparent text-[15px] leading-relaxed text-black placeholder:text-black/45 focus:outline-none disabled:cursor-not-allowed disabled:text-black/35 disabled:placeholder:text-black/35 dark:text-white dark:placeholder:text-white/45 dark:disabled:text-white/35 dark:disabled:placeholder:text-white/35"
					></textarea>
				</div>
				<div class="flex items-center justify-end gap-1 px-4 pb-4">
					{#if dictation.supported}
						<button
							onclick={handleDictation}
							disabled={activePromptInactive}
							aria-label={activePromptInactive
								? 'Voice input disabled while response is pending'
								: dictation.active
									? 'Stop dictation'
									: 'Voice input'}
							class="relative flex h-8 w-8 items-center justify-center rounded-full transition-colors {dictation.active
								? 'text-red-500'
								: 'text-black/40 hover:text-black/60 dark:text-white/40 dark:hover:text-white/60'} disabled:opacity-20"
						>
							{#if dictation.active}
								<span
									class="absolute inset-0 rounded-full bg-red-500/15"
									style="transform: scale({1 + dictation.volume * 0.5}); opacity: {0.4 +
										dictation.volume * 0.6};"
								></span>
							{/if}
							<svg
								class="relative h-[18px] w-[18px]"
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								stroke-width="1.75"
							>
								<path
									stroke-linecap="square"
									stroke-linejoin="miter"
									d="M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3z"
								/>
								<path
									stroke-linecap="square"
									stroke-linejoin="miter"
									d="M19 10v2a7 7 0 01-14 0v-2M12 19v4"
								/>
							</svg>
						</button>
					{:else}
						<button
							disabled
							aria-label="Voice input not supported"
							class="flex h-8 w-8 items-center justify-center rounded-full text-black/15 dark:text-white/15"
						>
							<svg
								class="h-[18px] w-[18px]"
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								stroke-width="1.75"
							>
								<path
									stroke-linecap="square"
									stroke-linejoin="miter"
									d="M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3z"
								/>
								<path
									stroke-linecap="square"
									stroke-linejoin="miter"
									d="M19 10v2a7 7 0 01-14 0v-2M12 19v4"
								/>
							</svg>
						</button>
					{/if}
					<button
						onclick={handleSend}
						disabled={!query.trim() || activePromptInactive}
						aria-label="Send"
						class="shrink-0 rounded-full bg-black p-2 transition-colors hover:bg-black/80 disabled:opacity-20 dark:bg-white dark:hover:bg-white/80"
					>
						<svg
							class="h-4 w-4 text-white dark:text-black"
							xmlns="http://www.w3.org/2000/svg"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2.5"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"
							/>
						</svg>
					</button>
				</div>
			</div>
		{:else}
			{#key composerResetKey}
				<RestaurantPromptComposer
					bind:query
					{isMobile}
					placeDirection="up"
					placePlaceholder="Restaurant name..."
					placeNudgeText="Select your restaurant so we can focus on the right area"
					onSubmit={handleNewChatSubmit}
				/>
			{/key}
		{/if}
	</div>
</div>

<style>
	.prompt-card {
		box-shadow:
			0 1px 2px rgba(0, 0, 0, 0.02),
			0 3px 12px rgba(0, 0, 0, 0.04);
	}

	:global(.dark) .prompt-card {
		box-shadow:
			0 1px 2px rgba(0, 0, 0, 0.08),
			0 3px 12px rgba(0, 0, 0, 0.2);
	}

	.sb-item {
		opacity: 0;
		transform: translateY(6px);
		transition:
			opacity 0.45s cubic-bezier(0.16, 1, 0.3, 1) var(--sb-delay, 0s),
			transform 0.45s cubic-bezier(0.16, 1, 0.3, 1) var(--sb-delay, 0s);
	}

	.sb-item.visible {
		opacity: 1;
		transform: translateY(0);
	}

	.sidebar.animated {
		transition:
			translate 0.5s cubic-bezier(0.16, 1, 0.3, 1),
			margin-left 0.5s cubic-bezier(0.16, 1, 0.3, 1);
		will-change: translate, margin-left;
	}

	.toggle-float {
		transition:
			background-color 0.2s ease,
			color 0.2s ease;
	}

	/* Fade out: quick, independent dip */
	.toggle-float.toggle-out {
		animation: toggleOut 0.15s ease-in forwards;
	}

	/* Plop in: delayed entrance with overshoot */
	.toggle-float.toggle-plop {
		animation: togglePlop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) 0.2s both;
	}

	@keyframes toggleOut {
		from {
			opacity: 1;
			transform: scale(1);
		}
		to {
			opacity: 0;
			transform: scale(0.6);
		}
	}

	@keyframes togglePlop {
		0% {
			opacity: 0;
			transform: scale(0.5);
		}
		60% {
			opacity: 1;
			transform: scale(1.15);
		}
		100% {
			opacity: 1;
			transform: scale(1);
		}
	}

	.deleting-indicator {
		animation: deletingPulse 1.4s ease-in-out infinite;
	}

	@keyframes deletingPulse {
		0%,
		100% {
			opacity: 0.45;
		}
		50% {
			opacity: 1;
		}
	}

		/* Entrance transitions — triggered by .is-mounted added after onMount */
	.chat-enter {
		opacity: 0;
		transform: scale(0.97);
		transition:
			opacity 0.35s cubic-bezier(0.16, 1, 0.3, 1),
			transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
	}

	.chat-enter.is-mounted {
		opacity: 1;
		transform: scale(1);
	}

	.chat-thread-enter {
		opacity: 0;
		transform: translateY(12px);
		transition:
			opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1) 0.05s,
			transform 0.3s cubic-bezier(0.16, 1, 0.3, 1) 0.05s;
	}

	.chat-thread-enter.is-mounted {
		opacity: 1;
		transform: translateY(0);
	}

</style>
