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
 *  Callers recognise this by `err.name === 'FirebaseUnavailableInSSRError'`
 *  and swallow it silently during prerender. */
class FirebaseUnavailableInSSRError extends Error {
	constructor() {
		super('Firebase bootstrap skipped: server-side');
		this.name = 'FirebaseUnavailableInSSRError';
	}
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
		// Override authDomain to our current host so OAuth popups (Google
		// account picker, etc.) say "agent.superextra.ai" instead of
		// "{projectId}.firebaseapp.com". Firebase Hosting auto-serves
		// `/__/auth/handler` and `/__/auth/iframe` at any associated site, so
		// the redirect target works at our domain too. Skipped on localhost
		// (dev) — the popup needs an authorized domain, and localhost is
		// already configured.
		if (window.location.hostname === 'agent.superextra.ai') {
			config.authDomain = 'agent.superextra.ai';
		}
		// Guard against double-init when the module is re-imported in dev HMR.
		const appAlreadyExists = getApps().length > 0;
		const app = appAlreadyExists ? getApps()[0] : initializeApp(config);
		// `initializeFirestore(...)` MUST stay inside this lazy async path.
		// `persistentMultipleTabManager()` touches `window` and IndexedDB,
		// which would throw during prerender if hoisted to module scope.
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
