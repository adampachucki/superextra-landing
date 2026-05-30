<script lang="ts">
	import { page } from '$app/state';
	import { scale } from 'svelte/transition';
	import { getLocale, locales, localizeHref, setLocale, type Locale } from '$lib/paraglide/runtime';
	import * as m from '$lib/paraglide/messages';

	// `over` matches the nav's transparent-hero state (white text on a dark image).
	// `dropUp` opens the menu above the trigger — for footer/sidebar placements
	// that sit at the bottom of their container.
	let { over = false, dropUp = false }: { over?: boolean; dropUp?: boolean } = $props();

	let open = $state(false);

	const localeName: Record<Locale, () => string> = {
		en: m.lang_english,
		de: m.lang_german,
		pl: m.lang_polish
	};

	const current = $derived(getLocale());
	const path = $derived(page.url.pathname + page.url.search);

	function choose(locale: Locale) {
		open = false;
		// setLocale persists the cookie (so the choice carries to /login and the
		// app) and navigates to the localized URL on marketing pages, or reloads
		// in place on the cookie-driven app routes. Respects routeStrategies.
		setLocale(locale);
	}

	const triggerClass = $derived(
		`flex items-center gap-1 text-sm transition-colors ${
			over
				? 'text-white/60 hover:text-white'
				: 'text-black/60 hover:text-black dark:text-white/60 dark:hover:text-white'
		}`
	);
</script>

<svelte:window onclick={() => (open = false)} />

<div class="relative">
	<button
		type="button"
		class={triggerClass}
		aria-label={m.lang_switch()}
		aria-haspopup="listbox"
		aria-expanded={open}
		onclick={(e) => {
			e.stopPropagation();
			open = !open;
		}}
	>
		<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
			<circle cx="12" cy="12" r="9" />
			<path d="M3 12h18M12 3c2.5 2.5 2.5 15 0 18M12 3c-2.5 2.5-2.5 15 0 18" />
		</svg>
		<span class="uppercase">{current}</span>
	</button>

	{#if open}
		<ul
			class="absolute right-0 z-50 min-w-[8rem] overflow-hidden rounded-lg border border-cream-200 bg-cream py-1 shadow-lg {dropUp
				? 'bottom-full mb-2 origin-bottom-right'
				: 'top-full mt-2 origin-top-right'}"
			role="listbox"
			transition:scale={{ duration: 150, start: 0.95, opacity: 0 }}
		>
			{#each locales as locale (locale)}
				<li>
					<a
						href={localizeHref(path, { locale })}
						hreflang={locale}
						data-sveltekit-reload
						role="option"
						aria-selected={locale === current}
						class="flex items-center justify-between px-4 py-2 text-sm text-black/70 transition-colors hover:bg-cream-100 hover:text-black dark:text-white/70 dark:hover:text-white {locale ===
						current
							? 'font-medium text-black dark:text-white'
							: ''}"
						onclick={(e) => {
							e.preventDefault();
							choose(locale);
						}}
					>
						{localeName[locale]()}
						{#if locale === current}
							<svg
								class="h-3.5 w-3.5"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
							>
								<path d="M5 13l4 4L19 7" />
							</svg>
						{/if}
					</a>
				</li>
			{/each}
		</ul>
	{/if}
</div>
