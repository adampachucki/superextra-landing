/**
 * Google Places autocomplete for restaurant/venue search.
 *
 * Factory pattern — each call returns an independent reactive store so the
 * hero and chat-page place inputs can coexist without sharing state. The
 * Google Maps script loader and browser-country detection ARE singletons
 * (shared across instances).
 */

import { PUBLIC_GOOGLE_PLACES_KEY } from '$env/static/public';

export interface PlaceSuggestion {
	name: string;
	secondary: string;
	placeId: string;
}

export interface PlaceSearch {
	readonly query: string;
	readonly suggestions: PlaceSuggestion[];
	readonly loading: boolean;
	readonly selected: PlaceSuggestion | null;
	readonly showSuggestions: boolean;
	setQuery(value: string): void;
	select(suggestion: PlaceSuggestion): void;
	clear(): void;
	hideSuggestions(): void;
}

export interface PlaceSearchOptions {
	/** Debounce window before firing a fetch. Default 300 ms. */
	debounceMs?: number;
	/** Minimum characters before a fetch is attempted. Default 2. */
	minChars?: number;
	/** Primary type filter for first-pass fetch. Default restaurant-adjacent types. */
	types?: string[];
}

// --- Module-level singletons (shared across instances) ---

let mapsPromise: Promise<void> | null = null;
let cachedCountry: string | null = null;

/** Lazy-load Google Maps JS API with the `places` library. */
export function loadGoogleMaps(): Promise<void> {
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
		script.onerror = () => {
			mapsPromise = null; // allow retry on next call
			reject(new Error('Failed to load Google Maps'));
		};
		document.head.appendChild(script);
	});
	return mapsPromise;
}

const TZ_COUNTRY_MAP: Record<string, string> = {
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

/**
 * Derive a 2-letter region code from the browser timezone or locale.
 * Memoized after first call.
 */
export function resolveBrowserCountry(): string {
	if (cachedCountry !== null) return cachedCountry;
	try {
		const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
		for (const [prefix, code] of Object.entries(TZ_COUNTRY_MAP)) {
			if (tz.startsWith(prefix) || tz === prefix) {
				cachedCountry = code;
				return code;
			}
		}
	} catch {
		// ignore
	}
	const locales =
		typeof navigator !== 'undefined' ? navigator.languages || [navigator.language || ''] : [''];
	for (const locale of locales) {
		const parts = locale.split('-');
		if (parts.length > 1) {
			cachedCountry = parts[parts.length - 1].toLowerCase();
			return cachedCountry;
		}
	}
	cachedCountry = '';
	return cachedCountry;
}

/** Reset module-level singletons. Test-only. */
export function __resetPlaceSearchSingletons(): void {
	mapsPromise = null;
	cachedCountry = null;
}

// --- Factory ---

const DEFAULT_TYPES = ['restaurant', 'cafe', 'bar', 'hotel', 'food'];

/**
 * Create an independent place-search store. Consumers bind to `.query`,
 * `.suggestions`, etc. — all reactive via Svelte runes.
 */
export function createPlaceSearch(opts: PlaceSearchOptions = {}): PlaceSearch {
	const debounceMs = opts.debounceMs ?? 300;
	const minChars = opts.minChars ?? 2;
	const types = opts.types ?? DEFAULT_TYPES;

	let query = $state('');
	let suggestions = $state<PlaceSuggestion[]>([]);
	let loading = $state(false);
	let selected = $state<PlaceSuggestion | null>(null);
	let showSuggestions = $state(false);

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let fetchToken = 0;

	async function fetchSuggestions(input: string): Promise<void> {
		const myToken = ++fetchToken;
		if (input.length < minChars) {
			if (myToken === fetchToken) {
				suggestions = [];
				loading = false;
			}
			return;
		}
		loading = true;
		try {
			await loadGoogleMaps();
			const country = resolveBrowserCountry();
			// eslint-disable-next-line @typescript-eslint/no-explicit-any -- AutocompleteSuggestion lacks types
			const base: any = { input, includedPrimaryTypes: types };
			if (country) base.region = country;
			let result = await // eslint-disable-next-line @typescript-eslint/no-explicit-any
			(google.maps.places.AutocompleteSuggestion as any).fetchAutocompleteSuggestions(base);
			// Fallback: retry without type filter when typed query (e.g. "name city") yields no results
			if (result.suggestions.length === 0) {
				// eslint-disable-next-line @typescript-eslint/no-unused-vars
				const { includedPrimaryTypes: _, ...fallback } = base;
				result = await // eslint-disable-next-line @typescript-eslint/no-explicit-any
				(google.maps.places.AutocompleteSuggestion as any).fetchAutocompleteSuggestions(fallback);
			}
			if (myToken !== fetchToken) return; // superseded by a newer setQuery
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			suggestions = result.suggestions.map((s: any) => ({
				name: s.placePrediction.mainText.text,
				secondary: s.placePrediction.secondaryText?.text ?? '',
				placeId: s.placePrediction.placeId
			}));
		} catch {
			if (myToken === fetchToken) suggestions = [];
		}
		if (myToken === fetchToken) loading = false;
	}

	return {
		get query() {
			return query;
		},
		get suggestions() {
			return suggestions;
		},
		get loading() {
			return loading;
		},
		get selected() {
			return selected;
		},
		get showSuggestions() {
			return showSuggestions;
		},
		setQuery(value: string) {
			query = value;
			selected = null;
			showSuggestions = true;
			if (debounceTimer) clearTimeout(debounceTimer);
			debounceTimer = setTimeout(() => fetchSuggestions(value), debounceMs);
		},
		select(suggestion: PlaceSuggestion) {
			query = suggestion.name;
			selected = suggestion;
			suggestions = [];
			showSuggestions = false;
			fetchToken++; // cancel any in-flight fetch
			if (debounceTimer) {
				clearTimeout(debounceTimer);
				debounceTimer = null;
			}
		},
		clear() {
			query = '';
			selected = null;
			suggestions = [];
			showSuggestions = false;
			fetchToken++;
			if (debounceTimer) {
				clearTimeout(debounceTimer);
				debounceTimer = null;
			}
		},
		hideSuggestions() {
			showSuggestions = false;
		}
	};
}
