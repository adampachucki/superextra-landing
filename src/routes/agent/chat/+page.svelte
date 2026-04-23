<script lang="ts">
	import { onMount, tick } from 'svelte';
	import ChatThread from '$lib/components/restaurants/ChatThread.svelte';
	import { chatState } from '$lib/chat-state.svelte';
	import { theme } from '$lib/theme.svelte';
	import { dictation } from '$lib/dictation.svelte';
	import { createPlaceSearch } from '$lib/place-search.svelte';

	const PREFIX = 'Ask Superextra ';
	const PROMPTS = [
		'to compare prices in your area...',
		'to analyze competitor reviews...',
		'how was last month for others...',
		'where to open next...',
		'what line cooks earn nearby...',
		'which platforms perform best...'
	];
	const MOBILE_PROMPTS = [
		'about local prices...',
		'about competitor reviews...',
		'how last month went...',
		'where to open next...',
		'what cooks earn nearby...',
		'which platforms work...'
	];

	let inputEl: HTMLTextAreaElement | undefined = $state();
	let query = $state('');
	let sidebarOpen = $state(false);
	let prevSidebarOpen = $state(false);
	let toggleBtnAnim = $state<'idle' | 'fade-out' | 'plop-in'>('idle');
	let isDesktop = $state(false);
	let isMobile = $state(false);
	let mounted = $state(false);
	let sidebarContentVisible = $derived(sidebarOpen && mounted);

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

	let display = $state(PREFIX);
	let isAnimating = $derived(
		!chatState.active && !query && !dictation.active && display.length > 0
	);

	$effect(() => {
		if (chatState.active || query || dictation.active) return;

		let timeout: ReturnType<typeof setTimeout>;
		let cancelled = false;
		let idx = 0;

		function sleep(ms: number) {
			return new Promise<void>((r) => {
				timeout = setTimeout(r, ms);
			});
		}

		async function run() {
			while (!cancelled) {
				const prompts = isMobile ? MOBILE_PROMPTS : PROMPTS;
				const text = prompts[idx % prompts.length];
				for (let i = 1; i <= text.length; i++) {
					if (cancelled) return;
					display = PREFIX + text.slice(0, i);
					await sleep(45);
				}
				await sleep(2200);
				for (let i = text.length - 1; i >= 0; i--) {
					if (cancelled) return;
					display = PREFIX + text.slice(0, i);
					await sleep(25);
				}
				await sleep(400);
				idx++;
			}
		}

		run();
		return () => {
			cancelled = true;
			clearTimeout(timeout);
		};
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
			// Await: only strip the prefilled params on success. On failure keep
			// the composer state + URL intact and surface the error.
			chatState
				.startNewChat(q, placeContext)
				.then(() => {
					const clean = new URL(window.location.href);
					clean.searchParams.delete('q');
					clean.searchParams.delete('placeName');
					clean.searchParams.delete('placeSecondary');
					clean.searchParams.delete('placeId');
					history.replaceState(history.state, '', clean);
				})
				.catch((err: unknown) => {
					query = q;
					if (placeContext) place.select(placeContext);
					sendError =
						err instanceof Error ? err.message : 'Could not start chat. Please try again.';
				});
		} else if (sid) {
			chatState.selectSession(sid);
		}
		sidebarOpen = window.matchMedia('(min-width: 1024px)').matches;
		prevSidebarOpen = sidebarOpen;
		tick().then(() => {
			mounted = true;
		});
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
		if (!trimmed || chatState.loading) return;
		sendError = null;
		if (chatState.active) {
			query = '';
			resizeTextarea();
			try {
				await chatState.sendFollowUp(trimmed);
			} catch (err) {
				query = trimmed;
				resizeTextarea();
				sendError =
					err instanceof Error ? err.message : 'Could not send message. Please try again.';
			}
		} else {
			if (!selectedPlace) {
				placeNudge = true;
				contextOpen = true;
				requestAnimationFrame(() => placeInputEl?.focus());
				return;
			}
			placeNudge = false;
			const placeForSend = selectedPlace;
			query = '';
			resizeTextarea();
			try {
				await chatState.startNewChat(trimmed, placeForSend);
			} catch (err) {
				query = trimmed;
				resizeTextarea();
				sendError =
					err instanceof Error ? err.message : 'Could not start chat. Please try again.';
			}
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSend();
		}
	}

	// --- Dictation ---
	let dictationBase = '';

	function handleDictation() {
		if (dictation.active) {
			dictation.stop();
			return;
		}
		dictationBase = query;
		dictation.toggle();
	}

	$effect(() => {
		if (dictation.active) {
			const t = dictation.text;
			const space = dictationBase && t && !dictationBase.endsWith(' ') ? ' ' : '';
			query = dictationBase + space + t;
		}
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
		place.clear();
		contextOpen = false;
		placeNudge = false;
		query = '';
	}

	// --- Place search (Google Places) ---
	const place = createPlaceSearch();
	let placeNudge = $state(false);
	let contextOpen = $state(false);
	let selectedPlace = $derived(place.selected);
	let contextExpanded = $derived(contextOpen && !selectedPlace);
	let contextOverflow = $state(false);
	let placeInputEl: HTMLInputElement | undefined = $state();

	// --- Request-action error state (Fix 1: surface transport failures) ---
	let sendError = $state<string | null>(null);
	let deleteError = $state<string | null>(null);

	$effect(() => {
		if (contextExpanded) {
			const timer = setTimeout(() => {
				contextOverflow = true;
			}, 380);
			return () => {
				clearTimeout(timer);
				contextOverflow = false;
			};
		} else {
			contextOverflow = false;
		}
	});

	function onPlaceInput(e: Event) {
		place.setQuery((e.target as HTMLInputElement).value);
	}

	function selectPlaceSuggestion(s: { name: string; secondary: string; placeId: string }) {
		place.select(s);
		placeNudge = false;
	}

	function removePlace() {
		place.clear();
		contextOpen = false;
	}

	function toggleContext() {
		contextOpen = !contextOpen;
		if (contextOpen && !selectedPlace) {
			requestAnimationFrame(() => placeInputEl?.focus());
		}
	}

	let confirmDeleteId = $state<string | null>(null);

	function handleWindowClick(e: MouseEvent) {
		if (!confirmDeleteId) return;
		const target = e.target as HTMLElement;
		if (!target.closest('.sb-item')) confirmDeleteId = null;
	}

	function formatRelativeTime(ts: number): string {
		const diff = Date.now() - ts;
		const minutes = Math.floor(diff / 60000);
		if (minutes < 1) return 'just now';
		if (minutes < 60) return `${minutes}m ago`;
		const hours = Math.floor(minutes / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		if (days === 1) return 'yesterday';
		if (days < 7) return `${days}d ago`;
		return new Date(ts).toLocaleDateString('en-GB', { month: 'short', day: 'numeric' });
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
	class="toggle-float fixed top-[max(1rem,env(safe-area-inset-top))] left-[max(1rem,env(safe-area-inset-left))] z-30 flex h-9 w-9 cursor-pointer items-center justify-center rounded-full bg-black text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80
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
			class="flex h-9 w-9 cursor-pointer items-center justify-center rounded-full text-black/40 transition-all duration-200 hover:bg-black/[0.06] hover:text-black/60 dark:text-white/40 dark:hover:bg-white/[0.06] dark:hover:text-white/60"
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
			class="sb-item mb-6 flex w-full cursor-pointer items-center gap-2 rounded-lg bg-cream-100 px-2 py-1.5 text-[13px] text-black/70 transition-colors hover:bg-cream-200 hover:text-black dark:bg-cream-50 dark:text-white/70 dark:hover:bg-cream-100 dark:hover:text-white"
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
					<div
						class="sb-item group relative"
						style="--sb-delay: {Math.min(0.38 + i * 0.05, 0.7)}s"
						class:visible={sidebarContentVisible}
					>
						<button
							onclick={() => {
								if (confirmDeleteId && confirmDeleteId !== sess.sid) {
									confirmDeleteId = null;
									deleteError = null;
								}
								if (confirmDeleteId === sess.sid) return;
								chatState.selectSession(sess.sid);
								if (!isDesktop) sidebarOpen = false;
							}}
							class="w-full cursor-pointer rounded-lg px-2 py-2 pr-8 text-left transition-colors {sess.sid ===
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
										<span class="truncate text-black/40 dark:text-white/40"
											>{sess.placeContext.name}</span
										>
										<span class="text-black/20 dark:text-white/20">&middot;</span>
									{/if}
									<span class="shrink-0 text-black/30 dark:text-white/30"
										>{sess.updatedAtMs ? formatRelativeTime(sess.updatedAtMs) : ''}</span
									>
								</div>
								<div
									class="absolute inset-0 flex items-center gap-1.5 transition-all duration-150 {confirmDeleteId ===
									sess.sid
										? 'translate-x-0 opacity-100'
										: 'pointer-events-none -translate-x-1.5 opacity-0'}"
								>
									<span
										role="button"
										tabindex="0"
										onclick={async (e) => {
											e.stopPropagation();
											deleteError = null;
											try {
												await chatState.deleteSession(sess.sid);
												confirmDeleteId = null;
											} catch (err) {
												deleteError =
													err instanceof Error
														? err.message
														: 'Could not delete. Please try again.';
											}
										}}
										onkeydown={async (e) => {
											if (e.key === 'Enter' || e.key === ' ') {
												e.preventDefault();
												e.stopPropagation();
												deleteError = null;
												try {
													await chatState.deleteSession(sess.sid);
													confirmDeleteId = null;
												} catch (err) {
													deleteError =
														err instanceof Error
															? err.message
															: 'Could not delete. Please try again.';
												}
											}
										}}
										class="cursor-pointer text-red-500 transition-colors hover:text-red-600 dark:text-red-400 dark:hover:text-red-300"
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
										class="cursor-pointer text-black/40 transition-colors hover:text-black/60 dark:text-white/40 dark:hover:text-white/60"
										>Cancel</span
									>
								</div>
							</div>
							{#if confirmDeleteId === sess.sid && deleteError}
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
								onclick={() => (confirmDeleteId = sess.sid)}
								aria-label="Delete conversation"
								class="absolute top-1/2 right-1 flex h-6 w-6 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full transition-opacity hover:bg-black/[0.06] dark:hover:bg-white/[0.06] {confirmDeleteId ===
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
				class="ml-auto cursor-pointer text-black/40 transition-colors hover:text-black/60 dark:text-white/40 dark:hover:text-white/60"
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
		{#if chatState.active}
			{#if chatState.loadState === 'missing' || chatState.loadState === 'loadTimedOut'}
				<div
					class="chat-thread-enter flex min-h-dvh items-center justify-center {mounted
						? 'is-mounted'
						: ''}"
				>
					<p class="text-[14px] text-black/40 dark:text-white/40">Couldn't load this chat</p>
				</div>
			{:else}
				<div class="chat-thread-enter {mounted ? 'is-mounted' : ''}">
					<ChatThread />
				</div>
			{/if}
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
				onclick={() => inputEl?.focus()}
				class="prompt-card cursor-text rounded-2xl border border-black/[0.12] bg-white transition-colors focus-within:border-black/[0.55] dark:border-white/[0.12] dark:bg-cream-50 dark:focus-within:border-white/[0.55]"
			>
				<div class="px-5 pt-4">
					<textarea
						bind:this={inputEl}
						bind:value={query}
						onkeydown={handleKeydown}
						placeholder={dictation.active ? 'Start speaking...' : 'Ask a follow-up...'}
						rows="1"
						autocomplete="off"
						autocapitalize="off"
						spellcheck="false"
						class="w-full resize-none border-0 bg-transparent text-[15px] leading-relaxed text-black placeholder:text-black/45 focus:outline-none dark:text-white dark:placeholder:text-white/45"
					></textarea>
				</div>
				<div class="flex items-center justify-end gap-1 px-4 pb-4">
					{#if dictation.supported}
						<button
							onclick={handleDictation}
							aria-label={dictation.active ? 'Stop dictation' : 'Voice input'}
							class="relative flex h-8 w-8 cursor-pointer items-center justify-center rounded-full transition-colors {dictation.active
								? 'text-red-500'
								: 'text-black/40 hover:text-black/60 dark:text-white/40 dark:hover:text-white/60'}"
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
							class="flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-full text-black/15 dark:text-white/15"
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
						disabled={!query.trim() || chatState.loading}
						aria-label="Send"
						class="shrink-0 cursor-pointer rounded-full bg-black p-2 transition-colors hover:bg-black/80 disabled:cursor-not-allowed disabled:opacity-20 dark:bg-white dark:hover:bg-white/80"
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
			<div
				onclick={() => inputEl?.focus()}
				class="prompt-card cursor-text rounded-2xl border border-black/[0.12] bg-white transition-colors focus-within:border-black/[0.55] dark:border-white/[0.12] dark:bg-cream-50 dark:focus-within:border-white/[0.55]"
			>
				<div class="flex flex-col">
					<div class="relative px-5 pt-5">
						<textarea
							bind:this={inputEl}
							bind:value={query}
							onkeydown={handleKeydown}
							placeholder={dictation.active
								? 'Start speaking...'
								: isAnimating
									? display
									: 'What do you want to know about your market?'}
							rows="3"
							autocomplete="off"
							autocapitalize="off"
							spellcheck="false"
							class="w-full resize-none border-0 bg-transparent text-[15px] leading-relaxed text-black focus:outline-none dark:text-white {isAnimating
								? 'placeholder:text-black/70 dark:placeholder:text-white/70'
								: 'placeholder:text-black/25 dark:placeholder:text-white/25'}"
						></textarea>
					</div>

					<div class="flex items-center justify-between px-4 pb-2">
						<!-- Left icons + place chip -->
						<div class="relative flex items-center gap-1">
							<button
								onclick={toggleContext}
								aria-label="Add place"
								class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-full transition-colors {contextOpen ||
								selectedPlace
									? 'text-black/60 dark:text-white/60'
									: 'text-black/40 hover:text-black/60 dark:text-white/40 dark:hover:text-white/60'}"
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
										d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z"
									/>
									<path
										stroke-linecap="square"
										stroke-linejoin="miter"
										d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z"
									/>
								</svg>
							</button>
							<button
								disabled
								aria-label="Map view"
								class="flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-full text-black/15 dark:text-white/15"
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
										d="M3 7l6-3 6 3 6-3v14l-6 3-6-3-6 3V7zM9 4v14M15 7v14"
									/>
								</svg>
							</button>
							{#if selectedPlace}
								<span
									class="context-slide absolute inset-y-0 left-0 my-auto inline-flex h-6 items-center gap-1.5 rounded-full border border-black/[0.10] bg-cream-100 pr-1 pl-2.5 text-xs text-black/65 dark:border-white/[0.10] dark:bg-cream-50 dark:text-white/65"
								>
									<span class="truncate">{selectedPlace.name}</span>
									{#if selectedPlace.secondary}
										<span class="hidden truncate text-black/35 md:inline dark:text-white/35"
											>{selectedPlace.secondary}</span
										>
									{/if}
									<button
										onclick={removePlace}
										aria-label="Remove place"
										class="flex h-4 w-4 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors hover:bg-black/[0.06] dark:hover:bg-white/[0.06]"
									>
										<svg
											class="h-3 w-3 text-black/30 dark:text-white/30"
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke="currentColor"
											stroke-width="2"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M6 18L18 6M6 6l12 12"
											/>
										</svg>
									</button>
								</span>
							{/if}
						</div>

						<!-- Right icons: mic + send -->
						<div class="flex items-center gap-1">
							{#if dictation.supported}
								<button
									onclick={handleDictation}
									aria-label={dictation.active ? 'Stop dictation' : 'Voice input'}
									class="relative flex h-8 w-8 cursor-pointer items-center justify-center rounded-full transition-colors {dictation.active
										? 'text-red-500'
										: 'text-black/40 hover:text-black/60 dark:text-white/40 dark:hover:text-white/60'}"
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
									class="flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-full text-black/15 dark:text-white/15"
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
								aria-label="Explore"
								class="shrink-0 cursor-pointer rounded-full bg-black p-2 transition-colors hover:bg-black/80 dark:bg-white dark:hover:bg-white/80"
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

					<!-- Place nudge -->
					{#if placeNudge && !selectedPlace}
						<p class="context-nudge mx-5 mb-2 text-[12px] text-black/40 dark:text-white/40">
							Select your restaurant so we can focus on the right area
						</p>
					{/if}

					<!-- Expanded context: place search -->
					<div class="context-expand" class:open={contextExpanded}>
						<div
							class="context-expand-inner"
							class:allow-overflow={contextOverflow}
							inert={contextExpanded ? undefined : true}
						>
							<div
								class="context-reveal relative mx-4 mb-4 pt-2"
								class:visible={contextExpanded}
								onclick={(e) => e.stopPropagation()}
							>
								<div class="relative">
									<input
										bind:this={placeInputEl}
										type="text"
										value={place.query}
										oninput={onPlaceInput}
										onfocus={() => {
											if (place.suggestions.length) place.setQuery(place.query);
										}}
										onblur={() => setTimeout(() => place.hideSuggestions(), 150)}
										placeholder="Restaurant name..."
										autocomplete="off"
										autocorrect="off"
										spellcheck="false"
										class="w-full rounded-xl border border-black/[0.08] bg-cream-50/50 px-4 py-2.5 pr-9 text-[13px] text-black placeholder:text-black/30 focus:border-black/25 focus:outline-none dark:border-white/[0.08] dark:bg-white/[0.03] dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/25"
									/>
									{#if place.loading}
										<svg
											class="absolute top-1/2 right-3 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-black/25 dark:text-white/25"
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
										>
											<circle
												class="opacity-25"
												cx="12"
												cy="12"
												r="10"
												stroke="currentColor"
												stroke-width="3"
											></circle>
											<path
												class="opacity-75"
												fill="currentColor"
												d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
											></path>
										</svg>
									{/if}
								</div>
								{#if place.showSuggestions && place.suggestions.length > 0}
									<ul
										class="absolute right-0 bottom-full left-0 z-50 mb-1 max-h-48 overflow-auto rounded-xl border border-black/[0.08] bg-white py-1 shadow-lg dark:border-white/[0.08] dark:bg-cream-50"
									>
										{#each place.suggestions as s}
											<li>
												<button
													type="button"
													class="w-full cursor-pointer px-4 py-2.5 text-left text-[13px] transition-colors hover:bg-cream-50 dark:hover:bg-white/[0.04]"
													onpointerdown={(e) => e.preventDefault()}
													onclick={() => selectPlaceSuggestion(s)}
												>
													<span class="text-black dark:text-white">{s.name}</span>
													{#if s.secondary}
														<span class="ml-1.5 text-black/45 dark:text-white/45"
															>{s.secondary}</span
														>
													{/if}
												</button>
											</li>
										{/each}
									</ul>
								{/if}
							</div>
						</div>
					</div>
				</div>
			</div>
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

	.is-mounted .sidebar-overlay {
		transition: opacity 0.3s ease;
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

	.context-slide {
		animation: contextSlide 0.25s ease-out both;
	}

	@keyframes contextSlide {
		from {
			opacity: 0;
			transform: translateY(-4px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.context-nudge {
		animation: contextSlide 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;
	}

	.context-expand {
		display: grid;
		grid-template-rows: 0fr;
		transition: grid-template-rows 0.2s cubic-bezier(0.16, 1, 0.3, 1);
	}

	.context-expand.open {
		grid-template-rows: 1fr;
	}

	.context-expand-inner {
		overflow: hidden;
	}

	.context-expand-inner.allow-overflow {
		overflow: visible;
	}

	.context-reveal {
		opacity: 0;
		transition: opacity 0.15s ease;
	}

	.context-reveal.visible {
		opacity: 1;
		transition: opacity 0.7s ease;
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

	.chat-input-enter {
		opacity: 0;
		transform: translateY(24px);
		transition:
			opacity 0.35s cubic-bezier(0.16, 1, 0.3, 1) 0.1s,
			transform 0.35s cubic-bezier(0.16, 1, 0.3, 1) 0.1s;
	}

	.chat-input-enter.is-mounted {
		opacity: 1;
		transform: translateY(0);
	}
</style>
