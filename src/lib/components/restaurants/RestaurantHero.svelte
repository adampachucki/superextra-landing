<script lang="ts">
	import { PUBLIC_GOOGLE_PLACES_KEY } from '$env/static/public';
	import { dictation } from '$lib/dictation.svelte';

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

	const PILL_POOL = [
		// Market context
		{
			label: 'Market sales shifts',
			color: '#818cf8',
			query: 'Is a slow month just us or is the whole neighbourhood pulling back?'
		},
		{
			label: 'Seasonal demand patterns',
			color: '#818cf8',
			query: 'How does demand in my area shift across seasons — and how should I plan for it?'
		},
		{
			label: 'Local market performance',
			color: '#818cf8',
			query: 'How is the local food and drink market performing compared to six months ago?'
		},
		// Site selection
		{
			label: "Who's getting the traffic",
			color: '#a78bfa',
			query: 'What are the foot traffic patterns in my neighbourhood by day and daypart?'
		},
		{
			label: 'Best streets to open on',
			color: '#a78bfa',
			query: 'Which streets or blocks near me have the highest foot traffic for hospitality?'
		},
		{
			label: 'Competition density',
			color: '#a78bfa',
			query: 'How saturated is the food and drink market within 1 km of this location?'
		},
		// Concept validation
		{
			label: 'Cuisine gaps in the area',
			color: '#f472b6',
			query: 'What cuisine types are underrepresented near me that locals are searching for?'
		},
		{
			label: 'What concepts work here',
			color: '#f472b6',
			query: 'Which formats and cuisines are thriving in this neighbourhood?'
		},
		{
			label: 'Delivery demand signals',
			color: '#f472b6',
			query: 'What delivery categories are growing fastest in my area right now?'
		},
		// Wage benchmarking
		{
			label: 'Salary benchmarks',
			color: '#6ee7b3',
			query: 'What are restaurants near us actually paying for every role?'
		},
		{
			label: 'Chef pay in my area',
			color: '#6ee7b3',
			query: 'What are head chefs and sous chefs earning at comparable restaurants nearby?'
		},
		{
			label: 'Server wage trends',
			color: '#6ee7b3',
			query: 'How have front-of-house wages changed in my area over the past year?'
		},
		// Price positioning
		{
			label: 'Menu price gaps',
			color: '#fbbf24',
			query: 'How does our menu pricing compare to competitors within 1 km?'
		},
		{
			label: 'Lunch price positioning',
			color: '#fbbf24',
			query: 'Where does my lunch menu sit price-wise compared to nearby competitors?'
		},
		{
			label: 'Drinks pricing landscape',
			color: '#fbbf24',
			query: 'How do my cocktail and wine prices compare to similar bars in the area?'
		},
		// Sentiment trends
		{
			label: 'What guests are saying',
			color: '#fb923c',
			query: 'What are the real sentiment themes across our reviews and competitors?'
		},
		{
			label: 'Service complaint trends',
			color: '#fb923c',
			query: 'What service issues keep coming up in reviews of places like mine?'
		},
		{
			label: 'What earns 5 stars nearby',
			color: '#fb923c',
			query: 'What do the top-rated cafes near me have in common according to reviews?'
		},
		// Competitor tracking
		{
			label: 'Competitor menu changes',
			color: '#06b6d4',
			query: 'Have any competitors near me changed their menu or pricing recently?'
		},
		{
			label: 'New launches nearby',
			color: '#06b6d4',
			query: 'What new concepts have launched in my area in the last 3 months?'
		},
		{
			label: 'Who opened nearby',
			color: '#06b6d4',
			query: 'What has opened or closed in my area recently?'
		},
		// Market shifts
		{
			label: 'Closures in the area',
			color: '#f87171',
			query: 'What has closed nearby recently and what can I learn from it?'
		},
		{
			label: 'Format shifts happening',
			color: '#f87171',
			query:
				'Are restaurants in my area shifting formats — dine-in to fast-casual, adding delivery?'
		},
		{
			label: 'Emerging food trends',
			color: '#f87171',
			query: 'What food trends are gaining traction in my market right now?'
		}
	];

	const VISIBLE_COUNT = 6;

	function shuffle<T>(arr: T[]): T[] {
		const a = [...arr];
		for (let i = a.length - 1; i > 0; i--) {
			const j = Math.floor(Math.random() * (i + 1));
			[a[i], a[j]] = [a[j], a[i]];
		}
		return a;
	}

	let pillGen = $state(0);
	let topics = $state(shuffle(PILL_POOL).slice(0, VISIBLE_COUNT));

	function reshufflePills() {
		pillGen++;
		topics = shuffle(PILL_POOL).slice(0, VISIBLE_COUNT);
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
	let contextOpen = $state(false);
	let placeName = $state('');
	let selectedPlace = $state<{ name: string; secondary: string; placeId: string } | null>(null);
	let contextExpanded = $derived(contextOpen && !selectedPlace);
	let contextOverflow = $state(false);

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
				'America/': 'us',
				'US/': 'us',
				'Europe/London': 'gb',
				'Europe/Berlin': 'de',
				'Europe/Warsaw': 'pl',
				'Europe/Paris': 'fr',
				'Europe/Rome': 'it',
				'Europe/Madrid': 'es',
				'Europe/Amsterdam': 'nl',
				'Europe/Brussels': 'be',
				'Europe/Vienna': 'at',
				'Europe/Zurich': 'ch',
				'Europe/Prague': 'cz',
				'Europe/Stockholm': 'se',
				'Europe/Copenhagen': 'dk',
				'Europe/Oslo': 'no',
				'Europe/Helsinki': 'fi',
				'Europe/Dublin': 'ie',
				'Europe/Lisbon': 'pt',
				'Europe/Bucharest': 'ro',
				'Europe/Budapest': 'hu',
				'Europe/Athens': 'gr',
				'Australia/': 'au',
				'Pacific/Auckland': 'nz',
				'Asia/Tokyo': 'jp',
				'Asia/Seoul': 'kr',
				'Asia/Singapore': 'sg'
			};
			for (const [prefix, code] of Object.entries(tzCountryMap)) {
				if (tz.startsWith(prefix) || tz === prefix) {
					browserCountry = code;
					return;
				}
			}
		} catch {
			// ignore Intl formatting failures
		}
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
			// eslint-disable-next-line @typescript-eslint/no-explicit-any -- AutocompleteSuggestion lacks types
			const opts: any = {
				input,
				includedPrimaryTypes: ['restaurant', 'cafe', 'bar', 'hotel', 'food']
			};
			if (browserCountry) {
				opts.region = browserCountry;
			}
			let { suggestions } = await // eslint-disable-next-line @typescript-eslint/no-explicit-any
			(google.maps.places.AutocompleteSuggestion as any).fetchAutocompleteSuggestions(opts);
			// Retry without type filter when typed query (e.g. "name city") yields no results
			if (suggestions.length === 0) {
				// eslint-disable-next-line @typescript-eslint/no-unused-vars
				const { includedPrimaryTypes: _, ...fallbackOpts } = opts;
				({ suggestions } = await // eslint-disable-next-line @typescript-eslint/no-explicit-any
				(google.maps.places.AutocompleteSuggestion as any).fetchAutocompleteSuggestions(
					fallbackOpts
				));
			}
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
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
								<div class="relative">
									<input
										bind:this={placeInputEl}
										type="text"
										value={placeName}
										oninput={onPlaceInput}
										onfocus={() => {
											if (placeSuggestions.length) showSuggestions = true;
										}}
										onblur={() => setTimeout(() => (showSuggestions = false), 150)}
										placeholder="Venue name..."
										autocomplete="off"
										autocorrect="off"
										spellcheck="false"
										class="w-full rounded-xl border border-black/[0.08] bg-cream-50/50 px-4 py-2.5 pr-9 text-[13px] text-black placeholder:text-black/30 focus:border-black/25 focus:outline-none dark:border-white/[0.08] dark:bg-white/[0.03] dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/25"
									/>
									{#if loadingSuggestions}
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
								{#if showSuggestions && placeSuggestions.length > 0}
									<ul
										class="absolute top-full right-0 left-0 z-50 mt-1 max-h-48 overflow-auto rounded-xl border border-black/[0.08] bg-white py-1 shadow-lg dark:border-white/[0.08] dark:bg-cream-50"
									>
										{#each placeSuggestions as s (s.placeId)}
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
		</div>

		<!-- Topic suggestion pills -->
		{#key pillGen}
			<div
				class="mx-auto mt-12 flex flex-wrap justify-center gap-2 md:mt-12"
				style="max-width: 750px;"
			>
				{#each topics as topic, i (topic.label)}
					<div
						class={pillGen === 0 ? 'topic-pill-wrap' : 'topic-pill-shuffle'}
						style="animation-delay: {pillGen === 0 ? 380 + i * 40 : 150 + i * 100}ms"
					>
						<button
							onclick={() => selectTopic(topic.query)}
							class="topic-pill inline-flex cursor-pointer items-center gap-2 rounded-full border border-black/[0.12] px-3.5 py-2 text-[13px] whitespace-nowrap text-black/55 transition-all duration-200 hover:border-black/[0.30] hover:text-black/75 active:border-black/[0.30] active:text-black/75 dark:border-white/[0.12] dark:text-white/55 dark:hover:border-white/[0.30] dark:hover:text-white/75 dark:active:border-white/[0.30] dark:active:text-white/75"
						>
							<span
								class="h-1.5 w-1.5 shrink-0 rounded-full"
								style="background-color: {topic.color}"
							></span>
							{topic.label}
						</button>
					</div>
				{/each}
				<div
					class={pillGen === 0 ? 'topic-pill-wrap' : 'topic-pill-shuffle'}
					style="animation-delay: {pillGen === 0
						? 380 + VISIBLE_COUNT * 40
						: 150 + VISIBLE_COUNT * 100}ms"
				>
					<button
						onclick={reshufflePills}
						aria-label="Show different suggestions"
						class="shuffle-btn group inline-flex h-[34px] w-[34px] cursor-pointer items-center justify-center rounded-full border border-black/[0.12] dark:border-white/[0.12]"
					>
						<svg
							class="h-3.5 w-3.5 text-black opacity-30 transition-opacity duration-200 group-hover:opacity-55 dark:text-white"
							xmlns="http://www.w3.org/2000/svg"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2"
							stroke-linecap="square"
							stroke-linejoin="miter"
						>
							<polyline points="23 4 23 10 17 10" />
							<path d="M21.17 8A9 9 0 0012 3 9 9 0 003 12a9 9 0 0016.5 5" />
						</svg>
					</button>
				</div>
			</div>
		{/key}
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

	.topic-pill-wrap {
		animation: fadeIn 0.4s ease-out both;
	}

	.topic-pill-shuffle {
		animation: pillShuffle 0.6s ease-out both;
	}

	@keyframes pillShuffle {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	.shuffle-btn svg {
		transition: transform 0.35s ease;
	}

	.shuffle-btn:active svg {
		transform: rotate(180deg);
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
