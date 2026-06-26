<script lang="ts">
	import { flushSync, onDestroy, onMount } from 'svelte';
	import { dictation } from '$lib/dictation.svelte';
	import { createPlaceSearch, type PlaceSuggestion } from '$lib/place-search.svelte';
	import PromptIcon from './PromptIcon.svelte';
	import PlaceSearchWidget from './PlaceSearchWidget.svelte';
	import { capture } from '$lib/analytics';
	import { trackEngagedVisit } from '$lib/meta-pixel';
	import * as m from '$lib/paraglide/messages';

	const PREFIX = m.composer_prefix();
	const PROMPTS = [
		m.composer_prompt_1(),
		m.composer_prompt_2(),
		m.composer_prompt_3(),
		m.composer_prompt_4(),
		m.composer_prompt_5(),
		m.composer_prompt_6()
	];
	const MOBILE_PROMPTS = [
		m.composer_prompt_m1(),
		m.composer_prompt_m2(),
		m.composer_prompt_m3(),
		m.composer_prompt_m4(),
		m.composer_prompt_m5(),
		m.composer_prompt_m6()
	];

	let {
		query = $bindable(''),
		isMobile = false,
		placeDirection = 'down',
		placePlaceholder = m.composer_place_placeholder(),
		autofocusMode = false,
		focusOnQueryChange = false,
		onSubmit
	}: {
		query?: string;
		isMobile?: boolean;
		placeDirection?: 'down' | 'up';
		placePlaceholder?: string;
		autofocusMode?: 'desktop' | false;
		focusOnQueryChange?: boolean;
		onSubmit: (detail: { query: string; place: PlaceSuggestion | null }) => void;
	} = $props();

	const place = createPlaceSearch();
	let inputEl: HTMLTextAreaElement | undefined = $state();
	let placeInputEl: HTMLInputElement | undefined = $state();
	let contextOpen = $state(false);
	let contextVisible = $state(false);
	let display = $state<string>(PREFIX);
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
		if (dictation.active) dictation.stop();
		query = '';
		resizeTextarea();
		onSubmit({ query: trimmed, place: selectedPlace });
	}

	let promptFocusTracked = false;
	// Set right before our own programmatic `.focus()` calls (desktop autofocus on
	// mount, focus-on-query-change) so the resulting `focus` event isn't counted as
	// engagement — only a genuine user focus or keystroke should fire `prompt_focus`.
	let suppressFocusEvent = false;

	function trackPromptEngagement() {
		if (promptFocusTracked) return;
		promptFocusTracked = true;
		let firstSession = true;
		try {
			firstSession = !localStorage.getItem('se_ph_focused');
			localStorage.setItem('se_ph_focused', '1');
		} catch {
			// localStorage unavailable (private mode) — treat as first session.
		}
		capture('prompt_focus', { is_first_session: firstSession });
		trackEngagedVisit();
	}

	function handlePromptFocus() {
		if (suppressFocusEvent) {
			suppressFocusEvent = false;
			return;
		}
		trackPromptEngagement();
	}

	// Typing into an already-(auto)focused box is genuine engagement that never
	// re-fires `focus`, so count the first real keystroke too. Programmatic value
	// changes (pills, dictation, draft restore) don't fire the DOM input event.
	function handlePromptInput() {
		trackPromptEngagement();
	}

	function focusTextareaSilently() {
		// Nothing to suppress if it's already focused — no focus event will fire.
		if (!inputEl || (typeof document !== 'undefined' && document.activeElement === inputEl)) return;
		suppressFocusEvent = true;
		focusWithoutScroll(inputEl);
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
			requestAnimationFrame(focusTextareaSilently);
		}
		previousQuery = currentQuery;
	});

	onMount(() => {
		if (autofocusMode === 'desktop' && !mobileViewport())
			requestAnimationFrame(focusTextareaSilently);
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
				onfocus={handlePromptFocus}
				oninput={handlePromptInput}
				data-agent-prompt-input="true"
				placeholder={dictation.active
					? m.composer_placeholder_speaking()
					: isAnimating
						? display
						: m.composer_placeholder_default()}
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
					aria-label={m.composer_add_focus()}
					class="flex h-8 w-8 items-center justify-center rounded-full transition-colors {contextOpen ||
					selectedPlace
						? 'text-black/60 dark:text-white/60'
						: 'text-black/40 hover:text-black/60 dark:text-white/40 dark:hover:text-white/60'}"
				>
					<PromptIcon name="location" class="h-[19px] w-[19px]" />
				</button>
				<button
					type="button"
					disabled
					aria-label={m.composer_attach()}
					class="flex h-8 w-8 items-center justify-center rounded-full text-black/15 dark:text-white/15"
				>
					<PromptIcon name="attach" class="h-[18px] w-[18px] translate-y-px" />
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
							aria-label={m.composer_remove_focus()}
							class="flex h-4 w-4 shrink-0 items-center justify-center rounded-full transition-colors hover:bg-black/[0.06] dark:hover:bg-white/[0.06]"
						>
							<PromptIcon name="close" class="h-3 w-3 text-black/30 dark:text-white/30" />
						</button>
					</span>
				{/if}
			</div>

			<div class="flex items-center gap-1">
				{#if dictation.supported}
					<button
						type="button"
						onclick={handleDictation}
						aria-label={dictation.active ? m.composer_stop_dictation() : m.composer_voice()}
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
						<PromptIcon name="mic" class="relative h-[18px] w-[18px]" />
					</button>
				{:else}
					<button
						type="button"
						disabled
						aria-label={m.composer_voice_unsupported()}
						class="flex h-8 w-8 items-center justify-center rounded-full text-black/15 dark:text-white/15"
					>
						<PromptIcon name="mic" class="h-[18px] w-[18px]" />
					</button>
				{/if}
				<button
					type="button"
					onclick={handleSubmit}
					aria-label={m.composer_explore()}
					class="shrink-0 rounded-full bg-black p-2 transition-colors hover:bg-black/80 dark:bg-white dark:hover:bg-white/80"
				>
					<PromptIcon name="send" class="h-4 w-4 text-white dark:text-black" />
				</button>
			</div>
		</div>

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
