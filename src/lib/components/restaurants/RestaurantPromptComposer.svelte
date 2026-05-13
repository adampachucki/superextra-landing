<script lang="ts">
	import { flushSync, onDestroy, onMount } from 'svelte';
	import { dictation } from '$lib/dictation.svelte';
	import { createPlaceSearch, type PlaceSuggestion } from '$lib/place-search.svelte';
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

	let {
		query = $bindable(''),
		isMobile = false,
		placeDirection = 'down',
		placePlaceholder = 'Venue name...',
		placeNudgeText = 'Select your venue so we can focus on the right area',
		autofocusMode = false,
		focusOnQueryChange = false,
		onSubmit
	}: {
		query?: string;
		isMobile?: boolean;
		placeDirection?: 'down' | 'up';
		placePlaceholder?: string;
		placeNudgeText?: string;
		autofocusMode?: 'desktop' | false;
		focusOnQueryChange?: boolean;
		onSubmit: (detail: { query: string; place: PlaceSuggestion }) => void;
	} = $props();

	const place = createPlaceSearch();
	let inputEl: HTMLTextAreaElement | undefined = $state();
	let placeInputEl: HTMLInputElement | undefined = $state();
	let contextOpen = $state(false);
	let contextVisible = $state(false);
	let placeNudge = $state(false);
	let display = $state(PREFIX);
	let dictationBase = '';
	let previousQuery = '';

	let selectedPlace = $derived(place.selected);
	let isAnimating = $derived(!query && !dictation.active && display.length > 0);

	function mobileViewport() {
		return (
			isMobile || (typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches)
		);
	}

	function focusWithoutScroll(el: HTMLElement | undefined) {
		if (!el) return;
		try {
			el.focus({ preventScroll: true });
		} catch {
			el.focus();
		}
	}

	function focusTextarea() {
		focusWithoutScroll(inputEl);
	}

	function focusPlaceInput() {
		placeInputEl?.focus();
	}

	function resizeTextarea() {
		if (!inputEl) return;
		inputEl.style.height = 'auto';
		inputEl.style.height = inputEl.scrollHeight + 'px';
	}

	function openContext() {
		flushSync(() => {
			contextOpen = true;
			contextVisible = true;
		});
		focusPlaceInput();
	}

	function toggleContext() {
		const nextOpen = !contextOpen;
		flushSync(() => {
			contextOpen = nextOpen;
			contextVisible = nextOpen && !selectedPlace;
		});
		if (contextVisible) focusPlaceInput();
	}

	function removePlace() {
		place.clear();
		contextOpen = false;
		contextVisible = false;
	}

	function handlePlaceSelect() {
		placeNudge = false;
		focusTextarea();
		requestAnimationFrame(() => {
			contextVisible = false;
		});
	}

	function handleSubmit() {
		const trimmed = query.trim();
		if (!trimmed) {
			focusTextarea();
			return;
		}
		if (!selectedPlace) {
			placeNudge = true;
			openContext();
			return;
		}
		if (dictation.active) dictation.stop();
		placeNudge = false;
		query = '';
		resizeTextarea();
		onSubmit({ query: trimmed, place: selectedPlace });
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSubmit();
		}
	}

	function focusPromptFromCardClick(e: MouseEvent) {
		if (e.target instanceof Element && e.target.closest('button, input, textarea, a')) return;
		focusTextarea();
	}

	function handleDictation() {
		if (dictation.active) {
			dictation.stop();
			return;
		}
		dictationBase = query;
		dictation.toggle();
	}

	$effect(() => {
		if (query || dictation.active) return;

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
		if (dictation.active) {
			const t = dictation.text;
			const space = dictationBase && t && !dictationBase.endsWith(' ') ? ' ' : '';
			query = dictationBase + space + t;
		}
	});

	$effect(() => {
		const currentQuery = query;
		resizeTextarea();
		if (
			focusOnQueryChange &&
			currentQuery &&
			currentQuery !== previousQuery &&
			typeof document !== 'undefined' &&
			document.activeElement !== inputEl &&
			!mobileViewport()
		) {
			requestAnimationFrame(focusTextarea);
		}
		previousQuery = currentQuery;
	});

	onMount(() => {
		if (autofocusMode === 'desktop' && !mobileViewport()) requestAnimationFrame(focusTextarea);
	});

	onDestroy(() => {
		if (dictation.active) dictation.stop();
	});
</script>

<div
	onclick={focusPromptFromCardClick}
	role="presentation"
	class="prompt-card cursor-text rounded-2xl border border-black/[0.12] bg-white transition-colors focus-within:border-black/[0.55] dark:border-white/[0.12] dark:bg-cream-50 dark:focus-within:border-white/[0.55]"
>
	<div class="flex flex-col">
		<div class="relative px-5 pt-5">
			<textarea
				bind:this={inputEl}
				bind:value={query}
				onkeydown={handleKeydown}
				data-agent-prompt-input="true"
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
			<div class="relative flex items-center gap-1">
				<button
					type="button"
					onclick={toggleContext}
					aria-label="Add place"
					class="flex h-8 w-8 items-center justify-center rounded-full transition-colors {contextOpen ||
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
					type="button"
					disabled
					aria-label="Map view"
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
							type="button"
							onclick={removePlace}
							aria-label="Remove place"
							class="flex h-4 w-4 shrink-0 items-center justify-center rounded-full transition-colors hover:bg-black/[0.06] dark:hover:bg-white/[0.06]"
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
					</span>
				{/if}
			</div>

			<div class="flex items-center gap-1">
				{#if dictation.supported}
					<button
						type="button"
						onclick={handleDictation}
						aria-label={dictation.active ? 'Stop dictation' : 'Voice input'}
						class="relative flex h-8 w-8 items-center justify-center rounded-full transition-colors {dictation.active
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
						type="button"
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
					type="button"
					onclick={handleSubmit}
					aria-label="Explore"
					class="shrink-0 rounded-full bg-black p-2 transition-colors hover:bg-black/80 dark:bg-white dark:hover:bg-white/80"
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

		{#if placeNudge && !selectedPlace}
			<p class="context-slide mx-5 mb-2 text-[12px] text-black/40 dark:text-white/40">
				{placeNudgeText}
			</p>
		{/if}

		{#if contextVisible}
			<div
				class="context-slide relative mx-4 mb-4 pt-2"
				onclick={(e) => e.stopPropagation()}
				role="presentation"
			>
				<PlaceSearchWidget
					{place}
					bind:inputEl={placeInputEl}
					direction={placeDirection}
					placeholder={placePlaceholder}
					onSelect={handlePlaceSelect}
				/>
			</div>
		{/if}
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
</style>
