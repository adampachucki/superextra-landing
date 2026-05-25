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

let cachedCandidates: string[] | null = null;

function addCandidate(candidates: string[], code: string): void {
	const normalized = code.trim().toLowerCase();
	if (!/^[a-z]{2}$/.test(normalized) || candidates.includes(normalized)) return;
	candidates.push(normalized);
}

function countryFromLocale(locale: string): string {
	const parts = locale.trim().replace('_', '-').split('-');
	const language = parts[0] ?? '';
	for (const tag of parts.slice(1)) {
		if (/^[a-z]{2}$/i.test(tag)) return tag;
		if (tag.length === 1) break;
	}
	if (language === 'de' || language === 'pl') return language;
	return '';
}

export function resolveBrowserCountryCandidates(): string[] {
	if (cachedCandidates !== null) return [...cachedCandidates];

	const candidates: string[] = [];
	try {
		const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
		for (const [prefix, code] of Object.entries(TZ_COUNTRY_MAP)) {
			if (tz.startsWith(prefix) || tz === prefix) {
				addCandidate(candidates, code);
				break;
			}
		}
	} catch {
		// Browser region hints are optional; callers provide deterministic fallbacks.
	}

	const locales =
		typeof navigator !== 'undefined' ? navigator.languages || [navigator.language || ''] : [''];
	for (const locale of locales) {
		addCandidate(candidates, countryFromLocale(locale));
	}

	cachedCandidates = candidates;
	return [...candidates];
}

export function resolveBrowserCountry(): string {
	return resolveBrowserCountryCandidates()[0] ?? '';
}

export function resolveSupportedBrowserCountry(
	supportedCountryCodes: readonly string[],
	fallbackCountryCode: string
): string {
	const supported = new Set(supportedCountryCodes.map((code) => code.toLowerCase()));
	for (const code of resolveBrowserCountryCandidates()) {
		if (supported.has(code)) return code;
	}
	return fallbackCountryCode;
}

export function __resetBrowserCountryCache(): void {
	cachedCandidates = null;
}
