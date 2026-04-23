import type { FirebaseApp } from 'firebase/app';
import type { Auth } from 'firebase/auth';
import type { Firestore } from 'firebase/firestore';

// Firebase web config is public — all fields are safe in client code
// (the API key identifies the project, it does NOT authorize access; rules do).
// Always fetched same-origin from `/__/firebase/init.json`, which Firebase
// Hosting auto-generates in production. In dev, vite proxies that path to
// `agent.superextra.ai` (see vite.config.ts) — Firebase Hosting doesn't set
// CORS on the endpoint, so cross-origin fetch isn't an option.
export interface FirebaseHandle {
	app: FirebaseApp;
	auth: Auth;
	db: Firestore;
}

let handlePromise: Promise<FirebaseHandle> | null = null;

/** Sentinel: Firebase can't bootstrap server-side because the config is at a
 *  browser-relative URL (`/__/firebase/init.json`) with no origin in Node.
 *  Callers (e.g. `attachSidebarListener`) recognise this by message and
 *  swallow it silently during prerender — vs. logging real errors on the
 *  client. */
class FirebaseUnavailableInSSRError extends Error {
	constructor() {
		super('Firebase bootstrap skipped: server-side');
		this.name = 'FirebaseUnavailableInSSRError';
	}
}
export function isFirebaseUnavailableInSSR(err: unknown): boolean {
	return err instanceof FirebaseUnavailableInSSRError;
}

async function loadConfig(): Promise<Record<string, string>> {
	const url = '/__/firebase/init.json';
	const response = await fetch(url);
	if (!response.ok) {
		throw new Error(`Firebase config fetch failed: ${response.status} at ${url}`);
	}
	return response.json();
}

export function getFirebase(): Promise<FirebaseHandle> {
	// In SSR/prerender there's no origin to resolve `/__/firebase/init.json`
	// against. Reject cleanly with a recognisable sentinel so callers can
	// swallow the error silently during prerender, and log real errors
	// normally on the client.
	if (typeof window === 'undefined') {
		return Promise.reject(new FirebaseUnavailableInSSRError());
	}
	if (handlePromise) return handlePromise;
	handlePromise = (async () => {
		const [{ initializeApp, getApps }, authMod, firestoreMod] = await Promise.all([
			import('firebase/app'),
			import('firebase/auth'),
			import('firebase/firestore')
		]);
		const config = await loadConfig();
		// Guard against double-init when the module is re-imported in dev HMR.
		const appAlreadyExists = getApps().length > 0;
		const app = appAlreadyExists ? getApps()[0] : initializeApp(config);
		// `initializeFirestore(...)` MUST stay inside this lazy async path.
		// `persistentMultipleTabManager()` touches `window` and IndexedDB,
		// which would throw during prerender if hoisted to module scope.
		// Plan §7 SDK config block: persistent local cache + multi-tab
		// coordination for automatic listener resumption after offline →
		// online transitions. Cache size uses the SDK default (100 MB).
		//
		// On HMR the FirebaseApp persists across module reloads but our
		// `handlePromise` memo does not. Calling `initializeFirestore` twice
		// on the same app throws; fall back to `getFirestore` in that case so
		// a stale editor save doesn't hard-crash the dev page.
		let db: Firestore;
		if (appAlreadyExists) {
			db = firestoreMod.getFirestore(app);
		} else {
			db = firestoreMod.initializeFirestore(app, {
				localCache: firestoreMod.persistentLocalCache({
					tabManager: firestoreMod.persistentMultipleTabManager()
				})
			});
		}
		return {
			app,
			auth: authMod.getAuth(app),
			db
		};
	})();
	return handlePromise;
}

/**
 * Ensure the current user is signed in anonymously. Resolves with the UID.
 * Safe to call repeatedly — returns the same UID across calls in the same
 * session.
 */
export async function ensureAnonAuth(): Promise<string> {
	const { auth } = await getFirebase();
	if (auth.currentUser) return auth.currentUser.uid;

	const { signInAnonymously, onAuthStateChanged } = await import('firebase/auth');
	return new Promise<string>((resolve, reject) => {
		const unsubscribe = onAuthStateChanged(
			auth,
			(user) => {
				if (user) {
					unsubscribe();
					resolve(user.uid);
				}
			},
			(err) => {
				unsubscribe();
				reject(err);
			}
		);
		signInAnonymously(auth).catch((err) => {
			unsubscribe();
			reject(err);
		});
	});
}

/**
 * Fetch a Firebase ID token for the current anonymous user, for sending to
 * server-side endpoints (agentStream, agentDelete) that verify via Admin SDK.
 * We pass `forceRefresh=false` — the Firebase Auth SDK automatically refreshes
 * the token ~5 min before expiry, so forcing refresh on every call would just
 * add latency without improving safety.
 */
export async function getIdToken(): Promise<string> {
	const { auth } = await getFirebase();
	const user = auth.currentUser;
	if (!user) throw new Error('No authenticated user');
	return user.getIdToken(/* forceRefresh */ false);
}
