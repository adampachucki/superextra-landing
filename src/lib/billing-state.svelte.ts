import type { Unsubscribe } from 'firebase/firestore';
import { browser } from '$app/environment';
import { auth } from '$lib/auth.svelte';
import { getFirebase } from '$lib/firebase';
import { resolveSupportedBrowserCountry } from '$lib/browser-country';

export type BillingMarket = 'us' | 'pl' | 'de' | 'other';
export type BillingMode = 'live' | 'test';
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
	livePlan: 'free' | 'paid';
	status: BillingStatus;
	market: BillingMarket | null;
	currency: 'usd' | 'pln' | 'eur' | null;
	currentPeriodEndMs: number | null;
	cancelAtPeriodEnd: boolean;
	stripeCustomerId: string | null;
	stripeSubscriptionId: string | null;
}

export const billingMarkets: {
	id: BillingMarket;
	label: string;
	currency: 'usd' | 'pln' | 'eur';
}[] = [
	{ id: 'pl', label: 'Poland', currency: 'pln' },
	{ id: 'de', label: 'Germany', currency: 'eur' },
	{ id: 'us', label: 'United States', currency: 'usd' },
	{ id: 'other', label: 'Other country', currency: 'usd' }
];

const BILLING_MODE_STORAGE_KEY = 'superextra.billingMode';
const PORTAL_SUBSCRIPTION_STATUSES = new Set<BillingStatus>([
	'active',
	'trialing',
	'past_due',
	'unpaid',
	'paused',
	'incomplete'
]);

let firestoreModulePromise: Promise<typeof import('firebase/firestore')> | null = null;
function getFirestoreMod() {
	if (!firestoreModulePromise) firestoreModulePromise = import('firebase/firestore');
	return firestoreModulePromise;
}

function emptySnapshot(): BillingSnapshot {
	return {
		plan: 'free',
		livePlan: 'free',
		status: 'none',
		market: null,
		currency: null,
		currentPeriodEndMs: null,
		cancelAtPeriodEnd: false,
		stripeCustomerId: null,
		stripeSubscriptionId: null
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

function billingMarketOptions() {
	const preferred = preferredMarket();
	const preferredOption = billingMarkets.find((market) => market.id === preferred);
	return preferredOption
		? [preferredOption, ...billingMarkets.filter((market) => market.id !== preferred)]
		: billingMarkets;
}

function billingCanManage(snapshot: BillingSnapshot): boolean {
	return Boolean(
		snapshot.stripeCustomerId &&
		snapshot.stripeSubscriptionId &&
		PORTAL_SUBSCRIPTION_STATUSES.has(snapshot.status)
	);
}

function normalizeBillingMode(value: string | null): BillingMode | null {
	if (value === 'test' || value === 'sandbox') return 'test';
	if (value === 'live' || value === 'prod' || value === 'production') return 'live';
	return null;
}

function billingModeFromBrowser(): BillingMode {
	if (!browser) return 'live';
	const url = new URL(window.location.href);
	const requested =
		normalizeBillingMode(url.searchParams.get('billingMode')) ??
		normalizeBillingMode(url.searchParams.get('stripeMode'));
	if (requested) {
		if (requested === 'test') {
			window.localStorage.setItem(BILLING_MODE_STORAGE_KEY, requested);
		} else {
			window.localStorage.removeItem(BILLING_MODE_STORAGE_KEY);
		}
		return requested;
	}
	return normalizeBillingMode(window.localStorage.getItem(BILLING_MODE_STORAGE_KEY)) ?? 'live';
}

function initBillingModeFromBrowser() {
	if (!browser || modeInitialized) return;
	modeInitialized = true;
	const nextMode = billingModeFromBrowser();
	if (billingMode !== nextMode) billingMode = nextMode;
}

function activeBillingField(): 'billing' | 'billingTest' {
	return billingMode === 'test' ? 'billingTest' : 'billing';
}

function activePlanField(): 'plan' | 'planTest' {
	return billingMode === 'test' ? 'planTest' : 'plan';
}

function billingEndpoint(resource: 'checkout' | 'portal') {
	return billingMode === 'test' ? `/api/billing/test/${resource}` : `/api/billing/${resource}`;
}

let snapshot = $state<BillingSnapshot>(emptySnapshot());
let billingMode = $state<BillingMode>(billingModeFromBrowser());
let modalVisible = $state(false);
let selectedMarket = $state<BillingMarket>(preferredMarket());
let posting = $state(false);
let error = $state<string | null>(null);
let initialized = false;
let modeInitialized = browser;
let currentUid: string | null = null;
let unsubscribe: Unsubscribe | null = null;

function detach() {
	unsubscribe?.();
	unsubscribe = null;
	snapshot = emptySnapshot();
	currentUid = null;
}

async function attach(uid: string, force = false) {
	if (!force && currentUid === uid && unsubscribe) return;
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
				const billingField = activeBillingField();
				const rawBilling =
					data[billingField] && typeof data[billingField] === 'object'
						? (data[billingField] as Record<string, unknown>)
						: {};
				snapshot = {
					plan: data[activePlanField()] === 'paid' ? 'paid' : 'free',
					livePlan: data.plan === 'paid' ? 'paid' : 'free',
					status: (rawBilling.status as BillingStatus | undefined) ?? 'none',
					market: (rawBilling.market as BillingMarket | undefined) ?? null,
					currency: (rawBilling.currency as BillingSnapshot['currency'] | undefined) ?? null,
					currentPeriodEndMs: toMillis(rawBilling.currentPeriodEnd),
					cancelAtPeriodEnd: rawBilling.cancelAtPeriodEnd === true,
					stripeCustomerId:
						typeof rawBilling.stripeCustomerId === 'string' ? rawBilling.stripeCustomerId : null,
					stripeSubscriptionId:
						typeof rawBilling.stripeSubscriptionId === 'string'
							? rawBilling.stripeSubscriptionId
							: null
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
	initBillingModeFromBrowser();
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

function setMode(mode: BillingMode) {
	initBillingModeFromBrowser();
	if (billingMode === mode) return;
	billingMode = mode;
	error = null;
	if (browser) {
		if (mode === 'test') {
			window.localStorage.setItem(BILLING_MODE_STORAGE_KEY, mode);
		} else {
			window.localStorage.removeItem(BILLING_MODE_STORAGE_KEY);
		}
	}
	const uid = currentUid;
	if (uid) {
		void attach(uid, true);
	} else {
		snapshot = emptySnapshot();
	}
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
		const url = await postBilling(billingEndpoint('checkout'), { market });
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
		const url = await postBilling(billingEndpoint('portal'));
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
	get marketOptions(): typeof billingMarkets {
		return billingMarketOptions();
	},
	get posting(): boolean {
		return posting;
	},
	get error(): string | null {
		return error;
	},
	get mode(): BillingMode {
		init();
		return billingMode;
	},
	get paid(): boolean {
		init();
		return snapshot.plan === 'paid';
	},
	get entitled(): boolean {
		init();
		return snapshot.livePlan === 'paid';
	},
	get canManage(): boolean {
		init();
		return billingCanManage(snapshot);
	},
	init,
	setMode,
	openUpgrade,
	closeUpgrade,
	startCheckout,
	openPortal
};
