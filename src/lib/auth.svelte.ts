/**
 * Auth state singleton (mirrors the formState/theme pattern).
 *
 * Owns the Firebase Auth session for the agent surface. The only auth state
 * the app exposes to consumers — chat-state subscribes to onAuthChange, route
 * components read `auth.user` directly.
 *
 * Anonymous auth is retired. Any persisted anonymous user from the previous
 * regime is signed out on boot (belt-and-suspenders with server-side
 * `firebase.sign_in_provider === 'anonymous'` reject).
 */

import type { User, UserCredential } from 'firebase/auth';
import { browser } from '$app/environment';
import { getFirebase } from '$lib/firebase';
import { getLocale } from '$lib/paraglide/runtime';
import { firstTouch } from '$lib/campaign';
import * as analytics from '$lib/analytics';

export type AuthStatus = 'unknown' | 'signed-in' | 'signed-out';

export interface DraftPrompt {
	prompt: string;
	placeContext: { name: string; secondary: string; placeId: string } | null;
	expiresAt: number;
}

const DRAFT_KEY = 'superextra:draft';
const DRAFT_TTL_MS = 60 * 60 * 1000; // 1h
const MAGIC_LINK_EMAIL_KEY = 'superextra:magicLinkEmail';

let user = $state<User | null>(null);
let status = $state<AuthStatus>('unknown');

// Login modal state (formState-style). Opened by any page that needs to gate
// an action behind sign-in; LoginModal mounted globally in +layout.svelte
// reads `modalVisible` to render itself.
let modalVisible = $state(false);
let modalReturnTo: string | null = null;
let modalAfterSignIn: (() => void) | null = null;

let initPromise: Promise<void> | null = null;

type AuthChangeListener = (uid: string | null) => void;
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const authChangeListeners = new Set<AuthChangeListener>();

// --- Analytics --------------------------------------------------------------
// First-touch campaign attribution is forwarded into PostHog so a Meta/Reddit
// click that converts days later stitches to the same person. See
// docs/analytics-implementation.md.

const LAST_SEEN_KEY = 'se_ph_last_seen';

function firstTouchProps(): Record<string, string | undefined> {
	const ft = firstTouch();
	return {
		first_touch_source: ft?.utm_source,
		first_touch_medium: ft?.utm_medium,
		first_touch_campaign: ft?.utm_campaign,
		first_touch_content: ft?.utm_content
	};
}

/** Identify the PostHog person on every authenticated tick (idempotent), and
 *  fire `return_visit` the first time we see this user on a new calendar day. */
function onAuthenticated(u: User): void {
	// First-touch attribution is `$set_once` (3rd arg) so a later campaign can't
	// overwrite the original source; email is a normal `$set`.
	analytics.identify(u.uid, { email: u.email ?? undefined }, firstTouchProps());
	if (!browser) return;
	const today = new Date().toISOString().slice(0, 10);
	let last: string | null;
	try {
		last = localStorage.getItem(LAST_SEEN_KEY);
		localStorage.setItem(LAST_SEEN_KEY, today);
	} catch {
		return;
	}
	if (!last || last === today) return; // first sighting in this browser, or same day
	const createdMs = u.metadata?.creationTime ? Date.parse(u.metadata.creationTime) : NaN;
	const daysSinceSignup = Number.isFinite(createdMs)
		? Math.floor((Date.now() - createdMs) / 86_400_000)
		: undefined;
	analytics.capture('return_visit', { days_since_signup: daysSinceSignup });
}

/** Track a completed sign-in. Identify FIRST so the conversion events attach to
 *  the Firebase UID and merge the anonymous pre-login history into this person —
 *  rather than racing the `onAuthStateChanged` identify. Fires `signed_in` for
 *  every success (with the chosen method) and `signup` only for genuinely new
 *  Firebase users, so returning sign-ins don't re-count. */
function trackSignIn(
	authMod: typeof import('firebase/auth'),
	result: UserCredential,
	method: 'google' | 'magic_link'
): void {
	try {
		const isNewUser = authMod.getAdditionalUserInfo(result)?.isNewUser ?? false;
		analytics.identify(
			result.user.uid,
			{ email: result.user.email ?? undefined },
			firstTouchProps()
		);
		analytics.capture('signed_in', { method, is_new_user: isNewUser });
		if (isNewUser) analytics.capture('signup', firstTouchProps());
	} catch (err) {
		console.warn('[auth] sign-in tracking failed', err);
	}
}

async function doInit(): Promise<void> {
	if (!browser) return;
	const { auth: fbAuth } = await getFirebase();
	const authMod = await import('firebase/auth');
	// Sign out any persisted anonymous user from the previous regime so it
	// can't continue minting valid tokens after the cutover.
	if (fbAuth.currentUser?.isAnonymous) {
		try {
			await authMod.signOut(fbAuth);
		} catch (err) {
			console.warn('[auth] failed to sign out persisted anonymous user', err);
		}
	}
	// Wait for the first onAuthStateChanged tick before resolving init. Firebase
	// docs note that `currentUser` is null during the brief window between page
	// load and the SDK's initial check against persisted state; resolving on
	// the first callback ensures callers like the chat-page auth guard don't
	// mistake "still booting" for "signed out".
	await new Promise<void>((resolve) => {
		let first = true;
		authMod.onAuthStateChanged(fbAuth, async (next) => {
			// Belt-and-suspenders — any anonymous user that somehow appears gets
			// signed out immediately, never propagated to consumers.
			if (next?.isAnonymous) {
				try {
					await authMod.signOut(fbAuth);
				} catch (err) {
					console.warn('[auth] failed to sign out anonymous user', err);
				}
				return;
			}
			user = next;
			status = next ? 'signed-in' : 'signed-out';
			if (next) onAuthenticated(next);
			else analytics.reset();
			const uid = next?.uid ?? null;
			for (const listener of authChangeListeners) {
				try {
					listener(uid);
				} catch (err) {
					console.warn('[auth] listener error', err);
				}
			}
			if (first) {
				first = false;
				resolve();
			}
		});
	});
}

function init(): Promise<void> {
	if (initPromise) return initPromise;
	initPromise = doInit().catch((err) => {
		// SSR has no DOM; firebase.ts rejects with the recognisable sentinel.
		if (err instanceof Error && err.name === 'FirebaseUnavailableInSSRError') return;
		console.warn('[auth] init failed', err);
	});
	return initPromise;
}

async function signInWithGoogle(): Promise<User> {
	await init();
	const { auth: fbAuth } = await getFirebase();
	const authMod = await import('firebase/auth');
	const provider = new authMod.GoogleAuthProvider();
	const result = await authMod.signInWithPopup(fbAuth, provider);
	trackSignIn(authMod, result, 'google');
	return result.user;
}

async function sendMagicLink(email: string, returnTo?: string | null): Promise<void> {
	// Per Firebase docs, the return-leg needs the email back. Stash it locally so
	// same-device flows can complete without a prompt. Cross-device users will be
	// asked for their email on /login when they click the link.
	if (browser) {
		try {
			localStorage.setItem(MAGIC_LINK_EMAIL_KEY, email);
		} catch (err) {
			console.warn('[auth] localStorage write failed for magic link email', err);
		}
	}
	const res = await fetch('/api/auth/send-magic-link', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ email, returnTo: returnTo ?? null, locale: getLocale() })
	});
	if (!res.ok) {
		const body = await res.json().catch(() => null);
		const code = (body as { error?: string } | null)?.error ?? `http_${res.status}`;
		throw new Error(code);
	}
}

export type MagicLinkResult =
	| { kind: 'not-magic-link' }
	| { kind: 'signed-in'; user: User }
	| { kind: 'needs-email' };

async function isMagicLink(url: string): Promise<boolean> {
	await init();
	const { auth: fbAuth } = await getFirebase();
	const authMod = await import('firebase/auth');
	return authMod.isSignInWithEmailLink(fbAuth, url);
}

async function completeMagicLinkSignIn(url: string): Promise<MagicLinkResult> {
	if (!(await isMagicLink(url))) return { kind: 'not-magic-link' };
	const email = browser ? localStorage.getItem(MAGIC_LINK_EMAIL_KEY) : null;
	if (!email) return { kind: 'needs-email' };
	const user = await finishMagicLinkSignIn(url, email);
	return { kind: 'signed-in', user };
}

async function finishMagicLinkSignIn(url: string, email: string): Promise<User> {
	await init();
	const { auth: fbAuth } = await getFirebase();
	const authMod = await import('firebase/auth');
	const result = await authMod.signInWithEmailLink(fbAuth, email, url);
	trackSignIn(authMod, result, 'magic_link');
	if (browser) {
		try {
			localStorage.removeItem(MAGIC_LINK_EMAIL_KEY);
		} catch {
			// noop
		}
	}
	return result.user;
}

async function signOutUser(): Promise<void> {
	await init();
	const { auth: fbAuth } = await getFirebase();
	const authMod = await import('firebase/auth');
	await authMod.signOut(fbAuth);
}

async function getIdToken(): Promise<string> {
	await init();
	const { auth: fbAuth } = await getFirebase();
	const u = fbAuth.currentUser;
	if (!u || u.isAnonymous) throw new Error('not_signed_in');
	return u.getIdToken(/* forceRefresh */ false);
}

/** POST JSON to an API endpoint with the signed-in user's ID token. Returns
 *  the raw Response — callers own status handling and body parsing. */
async function authedPost(url: string, body?: Record<string, unknown>): Promise<Response> {
	const idToken = await getIdToken();
	return fetch(url, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${idToken}` },
		body: JSON.stringify(body ?? {})
	});
}

function saveDraft(input: { prompt: string; placeContext: DraftPrompt['placeContext'] }) {
	if (!browser) return;
	const draft: DraftPrompt = {
		prompt: input.prompt,
		placeContext: input.placeContext,
		expiresAt: Date.now() + DRAFT_TTL_MS
	};
	try {
		localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
	} catch (err) {
		console.warn('[auth] failed to save draft', err);
	}
}

function readDraft(): DraftPrompt | null {
	if (!browser) return null;
	const raw = localStorage.getItem(DRAFT_KEY);
	if (!raw) return null;
	try {
		const parsed = JSON.parse(raw) as DraftPrompt;
		if (!parsed || typeof parsed !== 'object') return null;
		if (typeof parsed.expiresAt !== 'number' || parsed.expiresAt < Date.now()) {
			localStorage.removeItem(DRAFT_KEY);
			return null;
		}
		if (typeof parsed.prompt !== 'string' || !parsed.prompt.trim()) return null;
		return parsed;
	} catch {
		return null;
	}
}

function consumeDraft(): DraftPrompt | null {
	const draft = readDraft();
	if (draft && browser) {
		try {
			localStorage.removeItem(DRAFT_KEY);
		} catch {
			// noop
		}
	}
	return draft;
}

function peekDraft(): DraftPrompt | null {
	return readDraft();
}

function onAuthChange(listener: AuthChangeListener): () => void {
	authChangeListeners.add(listener);
	// Fire immediately if state is already known so consumers can sync without
	// missing the first transition. Deferred to a microtask because consumers
	// typically subscribe from inside a Svelte tracked read (e.g. chat-state's
	// sidebar getter): a synchronous fire would mutate $state during render,
	// and the downstream Firestore subscribe would race the SDK's own auth
	// listener — manifesting as an empty sidebar until the next page load.
	if (status !== 'unknown') {
		const uidNow = user?.uid ?? null;
		queueMicrotask(() => {
			if (!authChangeListeners.has(listener)) return;
			try {
				listener(uidNow);
			} catch (err) {
				console.warn('[auth] listener immediate fire failed', err);
			}
		});
	}
	return () => {
		authChangeListeners.delete(listener);
	};
}

function openModal(options?: {
	returnTo?: string | null;
	afterSignIn?: () => void;
	trigger?: string;
}) {
	modalReturnTo = options?.returnTo ?? null;
	modalAfterSignIn = options?.afterSignIn ?? null;
	modalVisible = true;
	analytics.capture('login_shown', { trigger: options?.trigger ?? 'unknown' });
}

function closeModal() {
	modalVisible = false;
	modalReturnTo = null;
	modalAfterSignIn = null;
}

function consumeAfterSignIn(): (() => void) | null {
	const cb = modalAfterSignIn;
	modalAfterSignIn = null;
	return cb;
}

export const auth = {
	get user(): User | null {
		return user;
	},
	get status(): AuthStatus {
		return status;
	},
	get uid(): string | null {
		return user?.uid ?? null;
	},
	get modalVisible(): boolean {
		return modalVisible;
	},
	get modalReturnTo(): string | null {
		return modalReturnTo;
	},
	init,
	signInWithGoogle,
	sendMagicLink,
	completeMagicLinkSignIn,
	finishMagicLinkSignIn,
	signOut: signOutUser,
	getIdToken,
	authedPost,
	saveDraft,
	consumeDraft,
	peekDraft,
	onAuthChange,
	openModal,
	closeModal,
	consumeAfterSignIn
};
