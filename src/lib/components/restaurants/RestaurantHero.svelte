<script lang="ts">
	import { dictation } from '$lib/dictation.svelte';
	import { createPlaceSearch } from '$lib/place-search.svelte';
	import TopicPills from './TopicPills.svelte';
	import PlaceSearchWidget from './PlaceSearchWidget.svelte';

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
	let isMobile = $state(false);
	$effect(() => {
		const mq = window.matchMedia('(max-width: 767px)');
		isMobile = mq.matches;
		const handler = (e: MediaQueryListEvent) => {
			isMobile = e.matches;
		};
		mq.addEventListener('change', handler);
		return () => mq.removeEventListener('change', handler);
	});
	const TYPE_MS = 45;
	const DELETE_MS = 25;
	const HOLD_MS = 2200;
	const PAUSE_MS = 400;

	let display = $state(PREFIX);
	let userQuery = $state('');
	let inputEl: HTMLTextAreaElement | undefined = $state();

	let isAnimating = $derived(!userQuery && !dictation.active && display.length > 0);

	$effect(() => {
		if (userQuery || dictation.active) return;

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
					await sleep(TYPE_MS);
				}

				await sleep(HOLD_MS);

				for (let i = text.length - 1; i >= 0; i--) {
					if (cancelled) return;
					display = PREFIX + text.slice(0, i);
					await sleep(DELETE_MS);
				}

				await sleep(PAUSE_MS);
				idx++;
			}
		}

		run();

		return () => {
			cancelled = true;
			clearTimeout(timeout);
		};
	});

	let {
		onleave
	}: {
		onleave?: (detail: {
			query: string;
			place: { name: string; secondary: string; placeId: string };
		}) => void;
	} = $props();

	let placeNudge = $state(false);
	let leaving = $state(false);

	function handleExplore() {
		if (!userQuery.trim()) {
			inputEl?.focus();
			return;
		}
		if (!selectedPlace) {
			placeNudge = true;
			contextOpen = true;
			requestAnimationFrame(() => placeInputEl?.focus());
			return;
		}
		if (leaving) return;
		placeNudge = false;
		leaving = true;
		inputEl?.blur();
		onleave?.({ query: userQuery.trim(), place: selectedPlace });
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleExplore();
		}
	}

	function resizeTextarea() {
		if (inputEl) {
			inputEl.style.height = 'auto';
			inputEl.style.height = inputEl.scrollHeight + 'px';
		}
	}

	$effect(() => {
		userQuery;
		resizeTextarea();
	});

	// --- Dictation ---
	let dictationBase = '';

	function handleDictation() {
		if (dictation.active) {
			dictation.stop();
			return;
		}
		dictationBase = userQuery;
		dictation.toggle();
	}

	$effect(() => {
		if (dictation.active) {
			const t = dictation.text;
			const space = dictationBase && t && !dictationBase.endsWith(' ') ? ' ' : '';
			userQuery = dictationBase + space + t;
		}
	});

	function selectTopic(query: string) {
		userQuery = query;
		if (!isMobile) inputEl?.focus();
	}

	// --- Context / Google Places ---

	const place = createPlaceSearch();
	let contextOpen = $state(false);
	let selectedPlace = $derived(place.selected);
	let contextExpanded = $derived(contextOpen && !selectedPlace);
	let contextOverflow = $state(false);
	let placeInputEl: HTMLInputElement | undefined = $state();

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
</script>

<section class="page-exit-content pt-32 md:pt-40" class:is-leaving={leaving}>
	{#if leaving}<div class="page-exit-overlay"></div>{/if}
	<div class="mx-auto max-w-[1200px] px-6">
		<!-- Headline -->
		<h1
			class="hero-fade mx-auto text-center font-semibold tracking-[-0.04em] text-black md:max-w-none dark:text-white"
			style="font-size: clamp(3rem, 6vw, 5.25rem); line-height: 1.02; animation-delay: 100ms;"
		>
			AI consultant <br class="max-md:hidden" />for every restaurant
		</h1>

		<!-- Subheadline -->
		<p
			class="hero-fade mx-auto mt-6 text-center text-lg leading-snug text-black/60 md:text-xl dark:text-white/60"
			style="max-width: 540px; animation-delay: 170ms;"
		>
			Stop relying on gossip and gut feel. Get clear answers about your competitors, pricing, and
			demand in minutes.
		</p>

		<!-- Prompt card -->
		<div
			class="prompt-fade relative z-20 mx-auto mt-10 md:mt-12"
			style="max-width: 650px; animation-delay: 280ms;"
		>
			<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
			<div
				onclick={() => inputEl?.focus()}
				class="prompt-card cursor-text rounded-2xl border border-black/[0.12] bg-white transition-colors focus-within:border-black/[0.55] dark:border-white/[0.12] dark:bg-cream-50 dark:focus-within:border-white/[0.55]"
			>
				<div class="flex flex-col">
					<div class="relative px-5 pt-5">
						<!-- svelte-ignore a11y_autofocus -->
						<textarea
							bind:this={inputEl}
							autofocus
							bind:value={userQuery}
							onkeydown={handleKeydown}
							onfocus={() => {}}
							placeholder={dictation.active
								? 'Start speaking...'
								: isAnimating
									? display
									: 'What do you want to know about your market?'}
							rows="3"
							class="w-full resize-none border-0 bg-transparent text-[15px] leading-relaxed text-black focus:outline-none dark:text-white {isAnimating
								? 'placeholder:text-black/70 dark:placeholder:text-white/70'
								: 'placeholder:text-black/25 dark:placeholder:text-white/25'}"
						></textarea>
					</div>

					<div class="flex items-center justify-between px-4 pb-2">
						<!-- Left icons + place chip -->
						<div class="relative flex items-center gap-1">
							<!-- Pin icon (opens place search) -->
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
							<!-- Map icon (disabled) -->
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
							<!-- Selected place chip (overlays pin + map icons) -->
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
							<!-- Send / Explore button -->
							<button
								onclick={handleExplore}
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

					<!-- Expanded context: place search -->
					{#if placeNudge && !selectedPlace}
						<p class="context-nudge mx-5 mb-2 text-[12px] text-black/40 dark:text-white/40">
							Select your venue so we can focus on the right area
						</p>
					{/if}

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
								<PlaceSearchWidget
									{place}
									bind:inputEl={placeInputEl}
									onSelect={() => (placeNudge = false)}
								/>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- Topic suggestion pills -->
		<TopicPills onPick={selectTopic} {isMobile} />
	</div>
</section>

<div class="h-24 md:h-36"></div>

<style>
	.hero-fade {
		animation: fadeIn 0.7s ease-out both;
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.prompt-fade {
		animation: fadeIn 0.6s ease-out both;
	}

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

	/* Exit transition */
	.page-exit-content {
		transition:
			opacity 0.25s cubic-bezier(0.4, 0, 1, 1),
			transform 0.25s cubic-bezier(0.4, 0, 1, 1),
			filter 0.25s cubic-bezier(0.4, 0, 1, 1);
	}

	.page-exit-content.is-leaving {
		opacity: 0;
		transform: scale(0.98) translateY(-8px);
		filter: blur(4px);
		pointer-events: none;
	}

	.page-exit-overlay {
		position: fixed;
		inset: 0;
		z-index: 9999;
		background: var(--color-cream);
		animation: overlayFadeIn 0.25s cubic-bezier(0.4, 0, 1, 1) both;
	}

	@keyframes overlayFadeIn {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}
</style>
