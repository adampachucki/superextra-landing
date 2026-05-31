/**
 * Ad-campaign attribution and hook-pillar mapping for the landing page.
 *
 * - `stampFirstTouch()` writes UTM + click-IDs from the current URL into
 *   localStorage on first arrival. First-touch semantics: subsequent ad
 *   clicks within the TTL window do NOT overwrite the original campaign.
 * - `firstTouch()` returns the stored attribution blob, or null.
 * - `campaignCategory()` resolves `utm_content` (current URL first, then the
 *   stored first-touch) to a pill category, so the prompt-area chips can
 *   surface the hook the click came from.
 *
 * Recognized `utm_content` values map to the four hook pillars from the
 * memo: where to open, how to price, when to hire, what's shifting.
 */

import { browser } from '$app/environment';

const STORAGE_KEY = 'se_first_touch';
const TTL_DAYS = 30;
const TTL_MS = TTL_DAYS * 86_400_000;

const UTM_PARAMS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content'] as const;
const CLICK_ID_PARAMS = ['fbclid', 'rdt_cid'] as const;

export interface FirstTouch {
	utm_source?: string;
	utm_medium?: string;
	utm_campaign?: string;
	utm_content?: string;
	fbclid?: string;
	rdt_cid?: string;
	stampedAt: number;
}

// One canonical key per hook pillar from the memo. Don't add aliases —
// matching reporting cohorts hinges on a single stable utm_content value
// per pillar.
const CONTENT_TO_PILL_CATEGORY: Record<string, string> = {
	price: 'pricing',
	hire: 'wage',
	open: 'site_selection',
	shifts: 'market_shifts'
};

function read(): FirstTouch | null {
	if (!browser) return null;
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return null;
		const parsed = JSON.parse(raw) as FirstTouch;
		const stampedAt = typeof parsed.stampedAt === 'number' ? parsed.stampedAt : 0;
		if (Date.now() - stampedAt > TTL_MS) {
			localStorage.removeItem(STORAGE_KEY);
			return null;
		}
		return parsed;
	} catch {
		return null;
	}
}

export function stampFirstTouch(): void {
	if (!browser) return;
	const params = new URLSearchParams(window.location.search);
	const payload: Partial<FirstTouch> = {};
	let hasAny = false;
	for (const key of [...UTM_PARAMS, ...CLICK_ID_PARAMS]) {
		const value = params.get(key);
		if (value) {
			payload[key] = value;
			hasAny = true;
		}
	}
	if (!hasAny) return;
	if (read()) return; // first-touch — don't overwrite
	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...payload, stampedAt: Date.now() }));
	} catch {
		// localStorage may be unavailable (private mode, full quota); silently skip.
	}
}

export function firstTouch(): FirstTouch | null {
	return read();
}

export function campaignCategory(): string | null {
	if (!browser) return null;
	const urlContent = new URLSearchParams(window.location.search).get('utm_content');
	if (urlContent && CONTENT_TO_PILL_CATEGORY[urlContent]) {
		return CONTENT_TO_PILL_CATEGORY[urlContent];
	}
	const content = read()?.utm_content;
	if (!content) return null;
	return CONTENT_TO_PILL_CATEGORY[content] ?? null;
}
