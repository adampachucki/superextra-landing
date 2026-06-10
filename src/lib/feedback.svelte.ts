/**
 * Feedback state singleton (mirrors the tts/theme pattern).
 *
 * Two surfaces share one POST endpoint (`/api/agent/feedback`, server-only
 * write via the Admin SDK):
 *   1. Per-answer thumbs — 👍/👎 on each assistant answer. Only the binary
 *      rating is stored on the turn doc, so the "you rated this" state arrives
 *      back through the existing turns listener. `localRating` mirrors the click
 *      instantly so the button doesn't feel dead during the round-trip; on a
 *      failed write it clears so the server value (from the listener) wins.
 *      Writes are serialized so a quick 👎 and its detailed submit can't land
 *      out of order.
 *   2. Periodic value prompt — a single "did this help you decide?" card shown
 *      after a research report, capped to once per COOLDOWN_MS via a localStorage
 *      timestamp. Showing it starts the cooldown whether or not it's answered.
 *
 * All transient state is keyed by `sid:turnIndex` — turn indices repeat across
 * sessions, so keying by index alone would bleed state between chats.
 */

import { browser } from '$app/environment';
import { auth } from '$lib/auth.svelte';
import * as analytics from '$lib/analytics';

const FEEDBACK_URL = '/api/agent/feedback';
const LAST_PROMPT_KEY = 'se_feedback_lastPromptAt';
const COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000; // 1 week between value prompts

export const DOWNVOTE_REASONS = [
	'Inaccurate',
	'Incomplete',
	'Not relevant',
	'Wrong sources'
] as const;

const keyOf = (sid: string, turnIndex: number) => `${sid}:${turnIndex}`;

async function post(body: Record<string, unknown>): Promise<void> {
	const res = await auth.authedPost(FEEDBACK_URL, body);
	if (!res.ok) throw new Error(`feedback_${res.status}`);
	analytics.capture('feedback_submitted', {
		kind: body.kind,
		rating: body.rating ?? body.useful,
		reason: body.reasons,
		text: body.note
	});
}

// --- Per-answer thumbs -----------------------------------------------------

let localRating = $state<Record<string, 'up' | 'down'>>({});
let openReasonsKey = $state<string | null>(null);

// Serialize rating writes so an immediate 👎 and its later detailed submit (or a
// quick down→up flip) reach the server in click order.
let writeChain: Promise<unknown> = Promise.resolve();

async function rate(
	sid: string | null,
	turnIndex: number,
	rating: 'up' | 'down',
	reasons?: string[],
	note?: string
): Promise<void> {
	if (!sid) return;
	const key = keyOf(sid, turnIndex);
	localRating = { ...localRating, [key]: rating };
	const send = () => post({ sid, turnIndex, kind: 'rating', rating, reasons, note });
	const run = writeChain.then(send, send);
	writeChain = run.catch(() => {});
	try {
		await run;
	} catch (err) {
		console.warn('[feedback] rate failed', err);
		// Only clear if a newer click hasn't already replaced our optimistic value;
		// clearing lets the server value (from the turns listener) take over.
		if (localRating[key] === rating) {
			const next = { ...localRating };
			delete next[key];
			localRating = next;
		}
	}
}

// --- Periodic value prompt -------------------------------------------------

let lastPromptAt = $state<number>(browser ? Number(localStorage.getItem(LAST_PROMPT_KEY)) || 0 : 0);
let activeSurveyKey = $state<string | null>(null);
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const surveyClosed = new Set<string>();

/** Offer the prompt on `turnIndex` if the cooldown has elapsed and it hasn't
 *  already been shown/closed. Showing it starts the cooldown — the cap is "at
 *  most once per week," answered or not. */
function maybeOfferSurvey(sid: string | null, turnIndex: number): void {
	if (!sid) return;
	const key = keyOf(sid, turnIndex);
	if (activeSurveyKey !== null || surveyClosed.has(key)) return;
	if (Date.now() - lastPromptAt <= COOLDOWN_MS) return;
	activeSurveyKey = key;
	lastPromptAt = Date.now();
	if (browser) {
		try {
			localStorage.setItem(LAST_PROMPT_KEY, String(lastPromptAt));
		} catch {
			// Private mode — fall back to the in-memory cap for this session.
		}
	}
}

function recordSurvey(
	sid: string | null,
	turnIndex: number,
	useful: 'yes' | 'no',
	reasons?: string[],
	note?: string
): void {
	if (!sid) return;
	post({ sid, turnIndex, kind: 'survey', useful, reasons, note }).catch((err) =>
		console.warn('[feedback] survey submit failed', err)
	);
}

function closeSurvey(sid: string | null, turnIndex: number): void {
	if (!sid) return;
	const key = keyOf(sid, turnIndex);
	surveyClosed.add(key);
	if (activeSurveyKey === key) activeSurveyKey = null;
}

export const feedback = {
	/** Rating to render: the instant local click wins until the turn doc confirms. */
	ratingFor(sid: string | null, turnIndex: number, server?: 'up' | 'down'): 'up' | 'down' | null {
		if (!sid) return server ?? null;
		return localRating[keyOf(sid, turnIndex)] ?? server ?? null;
	},
	rate,
	isReasonsOpen(sid: string | null, turnIndex: number): boolean {
		return !!sid && openReasonsKey === keyOf(sid, turnIndex);
	},
	openReasons(sid: string | null, turnIndex: number) {
		if (sid) openReasonsKey = keyOf(sid, turnIndex);
	},
	toggleReasons(sid: string | null, turnIndex: number) {
		if (!sid) return;
		const key = keyOf(sid, turnIndex);
		openReasonsKey = openReasonsKey === key ? null : key;
	},
	closeReasons() {
		openReasonsKey = null;
	},
	isSurveyActive(sid: string | null, turnIndex: number): boolean {
		return !!sid && activeSurveyKey === keyOf(sid, turnIndex);
	},
	maybeOfferSurvey,
	recordSurvey,
	closeSurvey
};
