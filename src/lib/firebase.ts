import type { FirebaseApp } from 'firebase/app';
import type { Auth } from 'firebase/auth';
import type { Firestore } from 'firebase/firestore';

// Firebase web config is public — all fields are safe in client code
// (the API key identifies the project, it does NOT authorize access; rules do).
// We fetch it at runtime from /__/firebase/init.json, which Firebase Hosting
// auto-generates. In dev we fall back to the production hosting URL — same
// public config.
const DEV_CONFIG_URL = 'https://agent.superextra.ai/__/firebase/init.json';

export interface FirebaseHandle {
	app: FirebaseApp;
	auth: Auth;
	db: Firestore;
}

let handlePromise: Promise<FirebaseHandle> | null = null;

function isLocalOrigin(): boolean {
	if (typeof window === 'undefined') return false;
	const host = window.location.hostname;
	return (
		host === 'localhost' ||
		host === '127.0.0.1' ||
		host.startsWith('192.168.') ||
		host.startsWith('10.') ||
		host.endsWith('.local')
	);
}

async function loadConfig(): Promise<Record<string, string>> {
	const url = isLocalOrigin() ? DEV_CONFIG_URL : '/__/firebase/init.json';
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
