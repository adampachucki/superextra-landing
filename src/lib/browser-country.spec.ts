import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
	__resetBrowserCountryCache,
	resolveBrowserCountry,
	resolveBrowserCountryCandidates,
	resolveSupportedBrowserCountry
} from './browser-country';

beforeEach(() => {
	__resetBrowserCountryCache();
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('browser country inference', () => {
	it('maps Intl timezone to country code', () => {
		vi.stubGlobal('Intl', {
			DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'Europe/Warsaw' }) })
		});

		expect(resolveBrowserCountry()).toBe('pl');
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
	});

	it('falls back to navigator language when timezone has no mapping', () => {
		vi.stubGlobal('Intl', {
			DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'Unknown/Tz' }) })
		});
		vi.stubGlobal('navigator', { languages: ['en-CA'], language: 'en-CA' });

		expect(resolveBrowserCountry()).toBe('ca');
	});

	it('keeps timezone and locale candidates in priority order', () => {
		vi.stubGlobal('Intl', {
			DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'Europe/Paris' }) })
		});
		vi.stubGlobal('navigator', { languages: ['en-GB', 'pl-PL'], language: 'en-GB' });

		expect(resolveBrowserCountryCandidates()).toEqual(['fr', 'gb', 'pl']);
	});

	it('selects the first supported market from browser candidates', () => {
		vi.stubGlobal('Intl', {
			DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'Europe/Paris' }) })
		});
		vi.stubGlobal('navigator', { languages: ['en-GB'], language: 'en-GB' });

		expect(resolveSupportedBrowserCountry(['de', 'pl', 'gb', 'us'], 'de')).toBe('gb');
	});

	it('uses the configured fallback when no candidate is supported', () => {
		vi.stubGlobal('Intl', {
			DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'Asia/Tokyo' }) })
		});
		vi.stubGlobal('navigator', { languages: ['ja-JP'], language: 'ja-JP' });

		expect(resolveSupportedBrowserCountry(['de', 'pl', 'gb', 'us'], 'de')).toBe('de');
	});
});
