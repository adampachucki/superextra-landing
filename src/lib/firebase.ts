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

async function loadConfig(): Promise<Record<string, string>> {
	const url = '/__/firebase/init.json';
	const response = await fetch(url);
	if (!response.ok) {
		throw new Error(`Firebase config fetch failed: ${response.status} at ${url}`);
	}
	return response.json();
}

export function getFirebase(): Promise<FirebaseHandle> {
	if (handlePromise) return handlePromise;
	handlePromise = (async () => {
		const [{ initializeApp, getApps }, authMod, firestoreMod] = await Promise.all([
			import('firebase/app'),
			import('firebase/auth'),
			import('firebase/firestore')
		]);
		const config = await loadConfig();
		// Guard against double-init when the module is re-imported in dev HMR.
		const app = getApps().length > 0 ? getApps()[0] : initializeApp(config);
		return {
			app,
			auth: authMod.getAuth(app),
			db: firestoreMod.getFirestore(app)
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
 * server-side endpoints (agentStream, agentCheck) that verify via Admin SDK.
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
