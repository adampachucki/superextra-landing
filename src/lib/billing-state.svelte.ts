import type { Unsubscribe } from 'firebase/firestore';
import { browser } from '$app/environment';
import { auth } from '$lib/auth.svelte';
import { getFirebase } from '$lib/firebase';
import { resolveSupportedBrowserCountry } from '$lib/browser-country';

export type BillingMarket = 'us' | 'pl' | 'de' | 'other';
export type BillingStatus =
	| 'none'
	| 'checkout_pending'
	| 'active'
	| 'trialing'
	| 'past_due'
	| 'unpaid'
	| 'paused'
	| 'canceled'
	| 'incomplete'
	| 'incomplete_expired';

export interface BillingSnapshot {
	plan: 'free' | 'paid';
	status: BillingStatus;
	market: BillingMarket | null;
	currency: 'usd' | 'pln' | 'eur' | null;
	currentPeriodEndMs: number | null;
	cancelAtPeriodEnd: boolean;
	stripeCustomerId: string | null;
}

export const billingMarkets: {
	id: BillingMarket;
	label: string;
	price: string;
	currency: 'usd' | 'pln' | 'eur';
}[] = [
	{ id: 'pl', label: 'Poland', price: '19 PLN', currency: 'pln' },
	{ id: 'de', label: 'Germany', price: '9 EUR', currency: 'eur' },
	{ id: 'us', label: 'United States', price: '$9', currency: 'usd' },
	{ id: 'other', label: 'Other country', price: '$9', currency: 'usd' }
];

let firestoreModulePromise: Promise<typeof import('firebase/firestore')> | null = null;
function getFirestoreMod() {
	if (!firestoreModulePromise) firestoreModulePromise = import('firebase/firestore');
	return firestoreModulePromise;
}

function emptySnapshot(): BillingSnapshot {
	return {
		plan: 'free',
		status: 'none',
		market: null,
		currency: null,
		currentPeriodEndMs: null,
		cancelAtPeriodEnd: false,
		stripeCustomerId: null
	};
}

function toMillis(value: unknown): number | null {
	if (
		value &&
		typeof value === 'object' &&
		'toMillis' in value &&
		typeof (value as { toMillis?: unknown }).toMillis === 'function'
	) {
		try {
			return (value as { toMillis: () => number }).toMillis();
		} catch {
			return null;
		}
	}
	return null;
}

function preferredMarket(): BillingMarket {
	const code = resolveSupportedBrowserCountry(['pl', 'de', 'us'], 'other');
	return code === 'pl' || code === 'de' || code === 'us' ? code : 'other';
}

let snapshot = $state<BillingSnapshot>(emptySnapshot());
let modalVisible = $state(false);
let selectedMarket = $state<BillingMarket>(preferredMarket());
let posting = $state(false);
let error = $state<string | null>(null);
let initialized = false;
let currentUid: string | null = null;
let unsubscribe: Unsubscribe | null = null;

function detach() {
	unsubscribe?.();
	unsubscribe = null;
	snapshot = emptySnapshot();
	currentUid = null;
}

async function attach(uid: string) {
	if (currentUid === uid && unsubscribe) return;
	detach();
	currentUid = uid;
	try {
		const [{ db }, firestoreMod] = await Promise.all([getFirebase(), getFirestoreMod()]);
		if (currentUid !== uid) return;
		const { doc, onSnapshot } = firestoreMod;
		unsubscribe = onSnapshot(
			doc(db, 'users', uid),
			(snap) => {
				const data = snap.exists() ? (snap.data() as Record<string, unknown>) : {};
				const rawBilling =
					data.billing && typeof data.billing === 'object'
						? (data.billing as Record<string, unknown>)
						: {};
				snapshot = {
					plan: data.plan === 'paid' ? 'paid' : 'free',
					status: (rawBilling.status as BillingStatus | undefined) ?? 'none',
					market: (rawBilling.market as BillingMarket | undefined) ?? null,
					currency: (rawBilling.currency as BillingSnapshot['currency'] | undefined) ?? null,
					currentPeriodEndMs: toMillis(rawBilling.currentPeriodEnd),
					cancelAtPeriodEnd: rawBilling.cancelAtPeriodEnd === true,
					stripeCustomerId:
						typeof rawBilling.stripeCustomerId === 'string' ? rawBilling.stripeCustomerId : null
				};
			},
			(err) => {
				console.warn('[billing] user listener error', err);
			}
		);
	} catch (err) {
		if (!(err instanceof Error && err.name === 'FirebaseUnavailableInSSRError')) {
			console.warn('[billing] listener bootstrap failed', err);
		}
	}
}

function init() {
	if (initialized || !browser) return;
	initialized = true;
	auth.onAuthChange((uid) => {
		if (uid) {
			void attach(uid);
		} else {
			detach();
		}
	});
	void auth.init();
}

function openUpgrade(options?: { market?: BillingMarket }) {
	init();
	error = null;
	selectedMarket = options?.market ?? preferredMarket();
	if (!auth.user) {
		auth.openModal({
			afterSignIn: () => {
				selectedMarket = options?.market ?? preferredMarket();
				modalVisible = true;
			}
		});
		return;
	}
	modalVisible = true;
}

function closeUpgrade() {
	if (posting) return;
	modalVisible = false;
	error = null;
}

async function postBilling(path: string, body?: Record<string, unknown>): Promise<string> {
	const idToken = await auth.getIdToken();
	const res = await fetch(path, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${idToken}`
		},
		body: JSON.stringify(body ?? {})
	});
	const payload = (await res.json().catch(() => null)) as { url?: string; error?: string } | null;
	if (!res.ok || !payload?.url) {
		const reason = payload?.error ?? `http_${res.status}`;
		throw new Error(reason);
	}
	return payload.url;
}

async function startCheckout(market: BillingMarket = selectedMarket) {
	if (posting) return;
	init();
	if (!auth.user) {
		openUpgrade({ market });
		return;
	}
	posting = true;
	error = null;
	try {
		const url = await postBilling('/api/billing/checkout', { market });
		window.location.assign(url);
	} catch (err) {
		error = 'Could not open Checkout. Please try again.';
		console.warn('[billing] checkout failed', err);
	} finally {
		posting = false;
	}
}

async function openPortal() {
	if (posting) return;
	init();
	if (!auth.user) {
		auth.openModal();
		return;
	}
	posting = true;
	error = null;
	try {
		const url = await postBilling('/api/billing/portal');
		window.location.assign(url);
	} catch (err) {
		error = 'Could not open billing management. Please try again.';
		console.warn('[billing] portal failed', err);
	} finally {
		posting = false;
	}
}

export const billing = {
	get snapshot(): BillingSnapshot {
		init();
		return snapshot;
	},
	get modalVisible(): boolean {
		init();
		return modalVisible;
	},
	get selectedMarket(): BillingMarket {
		return selectedMarket;
	},
	set selectedMarket(value: BillingMarket) {
		selectedMarket = value;
	},
	get posting(): boolean {
		return posting;
	},
	get error(): string | null {
		return error;
	},
	get paid(): boolean {
		init();
		return snapshot.plan === 'paid';
	},
	get canManage(): boolean {
		init();
		return Boolean(snapshot.stripeCustomerId);
	},
	init,
	openUpgrade,
	closeUpgrade,
	startCheckout,
	openPortal
};
