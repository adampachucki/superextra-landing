<script lang="ts">
	import { PUBLIC_GOOGLE_PLACES_KEY } from '$env/static/public';
	import { goto } from '$app/navigation';
	import { chatState } from '$lib/chat-state.svelte';

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
		const handler = (e: MediaQueryListEvent) => { isMobile = e.matches; };
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

	let isAnimating = $derived(!userQuery && display.length > 0);

	$effect(() => {
		if (userQuery) return;

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
		chatState.start(userQuery.trim(), selectedPlace);
		setTimeout(() => goto('/agent/chat'), 400);
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleExplore();
		}
	}

	const topics = [
		{ label: 'Menu price gaps', color: '#6ee7b3', query: 'How does our menu pricing compare to competitors within a mile?' },
		{ label: "Who's getting the traffic", color: '#a78bfa', query: 'What are the foot traffic patterns in my neighbourhood by day and daypart?' },
		{ label: 'Salary benchmarks', color: '#f472b6', query: 'What are restaurants near us actually paying for every role?' },
		{ label: 'What guests are saying', color: '#fbbf24', query: 'What are the real sentiment themes across our reviews and competitors?' },
		{ label: 'Market sales shifts', color: '#818cf8', query: 'Is a slow month just us or is the whole neighbourhood pulling back?' },
		{ label: 'Who opened nearby', color: '#06b6d4', query: 'What new restaurants have opened or closed in my area recently?' }
	];

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

	function selectTopic(query: string) {
		userQuery = query;
		if (!isMobile) inputEl?.focus();
	}

	// --- Context / Google Places ---
	let contextOpen = $state(false);
	let placeName = $state('');
	let selectedPlace = $state<{ name: string; secondary: string; placeId: string } | null>(null);
	let contextExpanded = $derived(contextOpen && !selectedPlace);
	let contextOverflow = $state(false);

	$effect(() => {
		if (contextExpanded) {
			const timer = setTimeout(() => { contextOverflow = true; }, 380);
			return () => { clearTimeout(timer); contextOverflow = false; };
		} else {
			contextOverflow = false;
		}
	});

	let placeSuggestions = $state<Array<{ name: string; secondary: string; placeId: string }>>([]);
	let showSuggestions = $state(false);
	let loadingSuggestions = $state(false);
	let debounceTimer: ReturnType<typeof setTimeout>;
	let placeInputEl: HTMLInputElement | undefined = $state();

	let browserCountry = $state('');
	$effect(() => {
		try {
			const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
			const tzCountryMap: Record<string, string> = {
				'America/': 'us', 'US/': 'us',
				'Europe/London': 'gb', 'Europe/Berlin': 'de', 'Europe/Warsaw': 'pl',
				'Europe/Paris': 'fr', 'Europe/Rome': 'it', 'Europe/Madrid': 'es',
				'Europe/Amsterdam': 'nl', 'Europe/Brussels': 'be', 'Europe/Vienna': 'at',
				'Europe/Zurich': 'ch', 'Europe/Prague': 'cz', 'Europe/Stockholm': 'se',
				'Europe/Copenhagen': 'dk', 'Europe/Oslo': 'no', 'Europe/Helsinki': 'fi',
				'Europe/Dublin': 'ie', 'Europe/Lisbon': 'pt', 'Europe/Bucharest': 'ro',
				'Europe/Budapest': 'hu', 'Europe/Athens': 'gr',
				'Australia/': 'au', 'Pacific/Auckland': 'nz',
				'Asia/Tokyo': 'jp', 'Asia/Seoul': 'kr', 'Asia/Singapore': 'sg',
			};
			for (const [prefix, code] of Object.entries(tzCountryMap)) {
				if (tz.startsWith(prefix) || tz === prefix) {
					browserCountry = code;
					return;
				}
			}
		} catch {}
		const locales = navigator.languages || [navigator.language || ''];
		for (const locale of locales) {
			const parts = locale.split('-');
			if (parts.length > 1) {
				browserCountry = parts[parts.length - 1].toLowerCase();
				return;
			}
		}
	});

	let mapsPromise: Promise<void> | null = null;
	function loadGoogleMaps(): Promise<void> {
		if (mapsPromise) return mapsPromise;
		mapsPromise = new Promise<void>((resolve, reject) => {
			if (typeof google !== 'undefined' && google.maps?.places) {
				resolve();
				return;
			}
			const script = document.createElement('script');
			script.src = `https://maps.googleapis.com/maps/api/js?key=${PUBLIC_GOOGLE_PLACES_KEY}&libraries=places`;
			script.async = true;
			script.onload = () => resolve();
			script.onerror = reject;
			document.head.appendChild(script);
		});
		return mapsPromise;
	}

	async function fetchPlaceSuggestions(input: string) {
		if (input.length < 2) {
			placeSuggestions = [];
			loadingSuggestions = false;
			return;
		}
		loadingSuggestions = true;
		try {
			await loadGoogleMaps();
			const opts: any = {
				input,
				includedPrimaryTypes: ['restaurant', 'cafe', 'bar', 'hotel', 'food']
			};
			if (browserCountry) {
				opts.region = browserCountry;
			}
			const { suggestions } = await (google.maps.places.AutocompleteSuggestion as any).fetchAutocompleteSuggestions(opts);
			placeSuggestions = suggestions.map((s: any) => ({
				name: s.placePrediction.mainText.text,
				secondary: s.placePrediction.secondaryText?.text ?? '',
				placeId: s.placePrediction.placeId
			}));
		} catch {
			placeSuggestions = [];
		}
		loadingSuggestions = false;
	}

	function onPlaceInput(e: Event) {
		const value = (e.target as HTMLInputElement).value;
		placeName = value;
		selectedPlace = null;
		clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => fetchPlaceSuggestions(value), 300);
		showSuggestions = true;
	}

	function selectPlaceSuggestion(s: { name: string; secondary: string; placeId: string }) {
		placeName = s.name;
		selectedPlace = s;
		placeSuggestions = [];
		showSuggestions = false;
		placeNudge = false;
	}

	function removePlace() {
		selectedPlace = null;
		placeName = '';
		placeSuggestions = [];
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
			class="hero-fade mx-auto md:max-w-none text-center font-semibold tracking-[-0.03em] text-black dark:text-white"
			style="font-size: clamp(3rem, 6vw, 5.25rem); line-height: 1.02; animation-delay: 100ms;"
		>
			AI consultant <br class="max-md:hidden" />for every restaurant
		</h1>

		<!-- Subheadline -->
		<p class="hero-fade mx-auto mt-6 text-center text-lg leading-snug text-black/60 dark:text-white/60 md:text-xl" style="max-width: 540px; animation-delay: 170ms;">
			Stop relying on gossip and gut feel. Get clear answers about your competitors, pricing, and demand in minutes.
		</p>

		<!-- Prompt card -->
		<div class="prompt-fade relative z-20 mx-auto mt-10 md:mt-12" style="max-width: 650px; animation-delay: 280ms;">
			<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
			<div onclick={() => inputEl?.focus()} class="cursor-text prompt-card rounded-2xl border border-black/[0.06] bg-white transition-colors focus-within:border-black/[0.35] dark:border-white/[0.06] dark:bg-cream-50 dark:focus-within:border-white/[0.35]">
				<div class="flex flex-col">
					<div class="px-5 pt-5">
						<!-- svelte-ignore a11y_autofocus -->
						<textarea
							bind:this={inputEl}
							autofocus
							bind:value={userQuery}
							onkeydown={handleKeydown}
							onfocus={() => {}}
							placeholder={isAnimating ? display : 'What do you want to know about your market?'}
							rows="3"
							class="w-full resize-none border-0 bg-transparent text-[15px] leading-relaxed text-black focus:outline-none dark:text-white {isAnimating ? 'placeholder:text-black/70 dark:placeholder:text-white/70' : 'placeholder:text-black/25 dark:placeholder:text-white/25'}"
						></textarea>
					</div>

					<div class="flex items-center justify-between px-4 pb-2">
						<!-- Left icons + place chip -->
						<div class="relative flex items-center gap-1">
							<!-- Pin icon (opens place search) -->
							<button onclick={toggleContext} aria-label="Add place" class="cursor-pointer flex h-8 w-8 items-center justify-center rounded-full transition-colors {contextOpen || selectedPlace ? 'text-black/60 dark:text-white/60' : 'text-black/30 hover:text-black/50 dark:text-white/30 dark:hover:text-white/50'}">
								<svg class="h-[18px] w-[18px]" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.75">
									<path stroke-linecap="square" stroke-linejoin="miter" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
									<path stroke-linecap="square" stroke-linejoin="miter" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
								</svg>
							</button>
							<!-- Map icon (disabled) -->
							<button disabled aria-label="Map view" class="flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-full text-black/15 dark:text-white/15">
								<svg class="h-[18px] w-[18px]" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.75">
									<path stroke-linecap="square" stroke-linejoin="miter" d="M3 7l6-3 6 3 6-3v14l-6 3-6-3-6 3V7zM9 4v14M15 7v14" />
								</svg>
							</button>
							<!-- Selected place chip (overlays pin + map icons) -->
							{#if selectedPlace}
								<span class="context-slide absolute inset-y-0 left-0 my-auto h-6 inline-flex items-center gap-1.5 rounded-full border border-black/[0.10] bg-cream-100 pl-2.5 pr-1 text-xs text-black/65 dark:border-white/[0.10] dark:bg-cream-50 dark:text-white/65">
									<span class="truncate">{selectedPlace.name}</span>
									{#if selectedPlace.secondary}
										<span class="hidden truncate text-black/35 dark:text-white/35 md:inline">{selectedPlace.secondary}</span>
									{/if}
									<button onclick={removePlace} aria-label="Remove place" class="cursor-pointer flex h-4 w-4 shrink-0 items-center justify-center rounded-full transition-colors hover:bg-black/[0.06] dark:hover:bg-white/[0.06]">
										<svg class="h-3 w-3 text-black/30 dark:text-white/30" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
											<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
										</svg>
									</button>
								</span>
							{/if}
						</div>

						<!-- Right icons: mic + send -->
						<div class="flex items-center gap-1">
							<!-- Microphone icon (disabled) -->
							<button disabled aria-label="Voice input" class="flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-full text-black/15 dark:text-white/15">
								<svg class="h-[18px] w-[18px]" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.75">
									<path stroke-linecap="square" stroke-linejoin="miter" d="M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3z" />
									<path stroke-linecap="square" stroke-linejoin="miter" d="M19 10v2a7 7 0 01-14 0v-2M12 19v4" />
								</svg>
							</button>
							<!-- Send / Explore button -->
							<button onclick={handleExplore} aria-label="Explore" class="cursor-pointer shrink-0 rounded-full bg-black p-2 transition-colors hover:bg-black/80 dark:bg-white dark:hover:bg-white/80">
								<svg class="h-4 w-4 text-white dark:text-black" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
									<path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
								</svg>
							</button>
						</div>
					</div>

					<!-- Expanded context: place search -->
					{#if placeNudge && !selectedPlace}
						<p class="context-nudge mx-5 mb-2 text-[12px] text-black/40 dark:text-white/40">
							Select your restaurant so we can focus on the right area
						</p>
					{/if}

					<div class="context-expand" class:open={contextExpanded}>
						<div class="context-expand-inner" class:allow-overflow={contextOverflow} inert={contextExpanded ? undefined : true}>
							<div class="context-reveal relative mx-4 mb-4 pt-2" class:visible={contextExpanded} onclick={(e) => e.stopPropagation()}>
								<div class="relative">
									<input
										bind:this={placeInputEl}
										type="text"
										value={placeName}
										oninput={onPlaceInput}
										onfocus={() => { if (placeSuggestions.length) showSuggestions = true; }}
										onblur={() => setTimeout(() => (showSuggestions = false), 150)}
										placeholder="Restaurant name..."
										autocomplete="off"
										autocorrect="off"
										spellcheck="false"
										class="w-full rounded-xl border border-black/[0.08] bg-cream-50/50 py-2.5 px-4 pr-9 text-[13px] text-black placeholder:text-black/30 focus:border-black/25 focus:outline-none dark:border-white/[0.08] dark:bg-white/[0.03] dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/25"
									/>
									{#if loadingSuggestions}
										<svg class="absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-black/25 dark:text-white/25" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
											<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3"></circle>
											<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
										</svg>
									{/if}
								</div>
								{#if showSuggestions && placeSuggestions.length > 0}
									<ul class="absolute left-0 right-0 top-full z-50 mt-1 max-h-48 overflow-auto rounded-xl border border-black/[0.08] bg-white py-1 shadow-lg dark:border-white/[0.08] dark:bg-cream-50">
										{#each placeSuggestions as s}
											<li>
												<button
													type="button"
													class="w-full cursor-pointer px-4 py-2.5 text-left text-[13px] transition-colors hover:bg-cream-50 dark:hover:bg-white/[0.04]"
													onpointerdown={(e) => e.preventDefault()}
													onclick={() => selectPlaceSuggestion(s)}
												>
													<span class="text-black dark:text-white">{s.name}</span>
													{#if s.secondary}
														<span class="ml-1.5 text-black/45 dark:text-white/45">{s.secondary}</span>
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

		</div>

		<!-- Topic suggestion pills -->
		<div
			class="topic-row mx-auto mt-12 flex flex-wrap justify-center gap-2 pb-1 transition-all duration-300 md:mt-12"
			style="max-width: 750px;"
		>
			{#each topics as topic, i}
				<div
					class="topic-pill-wrap"
					style="animation-delay: {380 + i * 40}ms"
				>
					<button
						onclick={() => selectTopic(topic.query)}
						class="topic-pill inline-flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-full border border-black/[0.12] px-3.5 py-2 text-[13px] text-black/55 transition-all duration-200 hover:border-black/[0.30] hover:text-black/75 active:border-black/[0.30] active:text-black/75 dark:border-white/[0.12] dark:text-white/55 dark:hover:border-white/[0.30] dark:hover:text-white/75 dark:active:border-white/[0.30] dark:active:text-white/75"
					>
						<span class="h-1.5 w-1.5 shrink-0 rounded-full" style="background-color: {topic.color}"></span>
						{topic.label}
					</button>
				</div>
			{/each}
		</div>
	</div>
</section>

<div class="h-24 md:h-36"></div>

<style>
	.hero-fade {
		animation: fadeIn 0.7s ease-out both;
	}

	@keyframes fadeIn {
		from { opacity: 0; transform: translateY(8px); }
		to { opacity: 1; transform: translateY(0); }
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

	.topic-pill-wrap {
		animation: fadeIn 0.4s ease-out both;
	}

	.context-slide {
		animation: contextSlide 0.25s ease-out both;
	}

	@keyframes contextSlide {
		from { opacity: 0; transform: translateY(-4px); }
		to { opacity: 1; transform: translateY(0); }
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
		transition: opacity 0.4s cubic-bezier(0.4, 0, 1, 1),
			transform 0.4s cubic-bezier(0.4, 0, 1, 1),
			filter 0.4s cubic-bezier(0.4, 0, 1, 1);
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
		animation: overlayFadeIn 0.4s cubic-bezier(0.4, 0, 1, 1) both;
	}

	@keyframes overlayFadeIn {
		from { opacity: 0; }
		to { opacity: 1; }
	}

</style>
