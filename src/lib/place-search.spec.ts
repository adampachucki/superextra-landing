import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
	createPlaceSearch,
	resolveBrowserCountry,
	__resetPlaceSearchSingletons
} from './place-search.svelte';

// --- google.maps stub ---

type FetchFn = (opts: {
	input: string;
	includedPrimaryTypes?: string[];
	region?: string;
}) => Promise<{
	suggestions: Array<{
		placePrediction: {
			mainText: { text: string };
			secondaryText?: { text: string };
			placeId: string;
		};
	}>;
}>;

function stubGoogleMaps(fetchFn: FetchFn) {
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	(globalThis as any).google = {
		maps: {
			places: {
				AutocompleteSuggestion: {
					fetchAutocompleteSuggestions: fetchFn
				}
			}
		}
	};
}

function makeSuggestion(name: string, secondary = '', placeId = 'p:' + name) {
	return {
		placePrediction: {
			mainText: { text: name },
			secondaryText: { text: secondary },
			placeId
		}
	};
}

beforeEach(() => {
	vi.useFakeTimers();
	__resetPlaceSearchSingletons();
});

afterEach(() => {
	vi.useRealTimers();
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	delete (globalThis as any).google;
});

describe('resolveBrowserCountry', () => {
	it('maps Intl timezone to country code', () => {
		vi.stubGlobal('Intl', {
			DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'Europe/Warsaw' }) })
		});
		expect(resolveBrowserCountry()).toBe('pl');
		vi.unstubAllGlobals();
	});

	it('memoizes after first call', () => {
		let callCount = 0;
		vi.stubGlobal('Intl', {
			DateTimeFormat: () => {
				callCount++;
				return { resolvedOptions: () => ({ timeZone: 'Asia/Tokyo' }) };
			}
		});
		resolveBrowserCountry();
		resolveBrowserCountry();
		expect(callCount).toBe(1);
		vi.unstubAllGlobals();
	});

	it('falls back to navigator.language when timezone has no mapping', () => {
		vi.stubGlobal('Intl', {
			DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'Unknown/Tz' }) })
		});
		vi.stubGlobal('navigator', { languages: ['en-CA'], language: 'en-CA' });
		expect(resolveBrowserCountry()).toBe('ca');
		vi.unstubAllGlobals();
	});
});

describe('createPlaceSearch', () => {
	it('debounces setQuery before fetching', async () => {
		const fetch = vi.fn(async () => ({
			suggestions: [makeSuggestion('Test')]
		})) as unknown as FetchFn;
		stubGoogleMaps(fetch);
		const place = createPlaceSearch({ debounceMs: 200 });
		place.setQuery('San');
		place.setQuery('San F');
		place.setQuery('San Fran');
		await vi.advanceTimersByTimeAsync(100);
		expect(fetch).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(150);
		await Promise.resolve();
		expect(fetch).toHaveBeenCalledTimes(1);
	});

	it('skips fetch when input is below minChars', async () => {
		const fetch = vi.fn(async () => ({ suggestions: [] })) as unknown as FetchFn;
		stubGoogleMaps(fetch);
		const place = createPlaceSearch({ debounceMs: 10, minChars: 3 });
		place.setQuery('ab');
		await vi.advanceTimersByTimeAsync(50);
		expect(fetch).not.toHaveBeenCalled();
	});

	it('falls back to unfiltered fetch when type-filtered returns empty', async () => {
		let call = 0;
		const fetch = vi.fn(async () => {
			call++;
			if (call === 1) return { suggestions: [] }; // first pass, type-filtered
			return { suggestions: [makeSuggestion('X', 'Y')] };
		}) as unknown as FetchFn;
		stubGoogleMaps(fetch);
		const place = createPlaceSearch({ debounceMs: 10 });
		place.setQuery('obscure name');
		await vi.advanceTimersByTimeAsync(20);
		await Promise.resolve();
		await Promise.resolve();
		expect(fetch).toHaveBeenCalledTimes(2);
		expect(place.suggestions.length).toBe(1);
		expect(place.suggestions[0].name).toBe('X');
	});

	it('aborts an in-flight fetch when a newer query arrives', async () => {
		let resolveFirst: (v: { suggestions: unknown[] }) => void = () => {};
		const fetch = vi.fn((opts) => {
			if (opts.input === 'first') {
				return new Promise((res) => {
					resolveFirst = res as (v: { suggestions: unknown[] }) => void;
				});
			}
			return Promise.resolve({ suggestions: [makeSuggestion('Second')] });
		}) as unknown as FetchFn;
		stubGoogleMaps(fetch);
		const place = createPlaceSearch({ debounceMs: 0 });
		place.setQuery('first');
		await vi.advanceTimersByTimeAsync(5);
		place.setQuery('second');
		await vi.advanceTimersByTimeAsync(5);
		await Promise.resolve();
		await Promise.resolve();
		// Now resolve the first call — its result must be discarded.
		resolveFirst({ suggestions: [makeSuggestion('Stale')] });
		await Promise.resolve();
		await Promise.resolve();
		expect(place.suggestions.map((s) => s.name)).toEqual(['Second']);
	});

	it('select() clears suggestions and records selected', async () => {
		const fetch = vi.fn(async () => ({
			suggestions: [makeSuggestion('A', 'B', 'pid')]
		})) as unknown as FetchFn;
		stubGoogleMaps(fetch);
		const place = createPlaceSearch({ debounceMs: 0 });
		place.setQuery('foo');
		await vi.advanceTimersByTimeAsync(5);
		await Promise.resolve();
		await Promise.resolve();
		const s = place.suggestions[0];
		place.select(s);
		expect(place.selected).toEqual({ name: 'A', secondary: 'B', placeId: 'pid' });
		expect(place.query).toBe('A');
		expect(place.suggestions).toEqual([]);
		expect(place.showSuggestions).toBe(false);
	});

	it('clear() resets everything', async () => {
		const fetch = vi.fn(async () => ({ suggestions: [makeSuggestion('A')] })) as unknown as FetchFn;
		stubGoogleMaps(fetch);
		const place = createPlaceSearch({ debounceMs: 0 });
		place.setQuery('foo');
		await vi.advanceTimersByTimeAsync(5);
		await Promise.resolve();
		await Promise.resolve();
		place.select(place.suggestions[0]);
		place.clear();
		expect(place.query).toBe('');
		expect(place.selected).toBe(null);
		expect(place.suggestions).toEqual([]);
		expect(place.showSuggestions).toBe(false);
	});

	it('two instances are independent', async () => {
		const fetch = vi.fn(async (opts) => ({
			suggestions: [makeSuggestion('for:' + opts.input)]
		})) as unknown as FetchFn;
		stubGoogleMaps(fetch);
		const a = createPlaceSearch({ debounceMs: 0 });
		const b = createPlaceSearch({ debounceMs: 0 });
		a.setQuery('one');
		b.setQuery('two');
		await vi.advanceTimersByTimeAsync(5);
		await Promise.resolve();
		await Promise.resolve();
		expect(a.suggestions[0].name).toBe('for:one');
		expect(b.suggestions[0].name).toBe('for:two');
	});
});
