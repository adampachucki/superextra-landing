/**
 * Firestore-backed progress stream. Reads are from the durable Firestore
 * events stream that the worker writes; writes never happen from the
 * browser.
 *
 * The worker emits events of shape:
 *   { userId, runId, attempt, seqInAttempt, type, data, ts, expiresAt }
 *
 * We subscribe to two observers:
 *
 *   1. `sessions/{sid}` — **the only terminal source**. Session-doc writes go
 *      through the worker's `_fenced_update` transaction, so a fenced-out
 *      stale worker cannot flip `status`/`reply`. `onComplete` and `onError`
 *      fire only from this observer.
 *   2. collection-group `events` filtered by (userId, runId) — progress and
 *      activity only. Event writes are unfenced (`ref.set(...)`), so a stale
 *      worker could leak one terminal event doc between its last write and
 *      hitting `OwnershipLost`. We deliberately ignore `type='complete'` /
 *      `type='error'` in this observer to close that leak.
 *
 * Cache semantics: we ignore the first `fromCache` snapshot of the session
 * doc for terminal-state transitions, which prevents a stale `status=complete`
 * cached from a previous run-of-this-browser from firing onComplete before
 * the server confirms.
 *
 * First-snapshot timeout: if neither observer delivers a callback within 10s,
 * we call `onFirstSnapshotTimeout` so the caller can fall back to the
 * `agentCheck` REST poll (`chat-recovery.ts`).
 */

import { getFirebase, ensureAnonAuth } from './firebase';

export interface ChatSource {
	title: string;
	url: string;
	domain?: string;
}

export interface ActivityEvent {
	id: string;
	category: 'data' | 'search' | 'read' | 'analyze';
	status: 'pending' | 'running' | 'complete' | 'all-complete';
	label: string;
	detail?: string;
	url?: string;
	agent?: string;
	specialists?: string[];
	sources?: ChatSource[];
}

export interface StreamCallbacks {
	onProgress: (
		stage: string,
		status: string,
		label: string,
		previews?: Array<{ name: string; preview: string }>
	) => void;
	onComplete: (reply: string, sources: ChatSource[], title?: string) => void;
	onError: (error: string) => void;
	onActivity?: (activity: ActivityEvent) => void;
	/** Emitted when the session doc's `currentAttempt` increases mid-run.
	 *  Caller should clear streaming UI + render a brief "Retrying…" cue. */
	onAttemptChange?: (attempt: number) => void;
	/** Emitted once when either observer returns `PERMISSION_DENIED`. */
	onPermissionDenied?: () => void;
	/** Emitted if no snapshot has arrived within 10 s — caller should
	 *  fall back to REST polling via `chat-recovery`. */
	onFirstSnapshotTimeout?: () => void;
}

const FIRST_SNAPSHOT_TIMEOUT_MS = 10_000;

/**
 * Subscribe to durable progress for a (sessionId, runId) pair.
 * Returns an unsubscribe function. Safe to call multiple times;
 * each call creates an independent subscription.
 */
export async function subscribeToSession(
	sessionId: string,
	runId: string,
	callbacks: StreamCallbacks
): Promise<() => void> {
	const uid = await ensureAnonAuth();
	const { db } = await getFirebase();
	const firestoreMod = await import('firebase/firestore');
	const { doc, onSnapshot, collectionGroup, query, where, orderBy } = firestoreMod;

	const sessionRef = doc(db, 'sessions', sessionId);
	const eventsQuery = query(
		collectionGroup(db, 'events'),
		where('userId', '==', uid),
		where('runId', '==', runId),
		orderBy('attempt'),
		orderBy('seqInAttempt')
	);

	let observedAttempt: number | null = null;
	let lastRenderedAttempt = -1;
	let lastRenderedSeq = -1;
	let firstSnapshotSeen = false;
	let terminal = false;
	// One-shot per subscription: both observers share `handleErr`, so a
	// permission-denied on both would double-fire `onPermissionDenied` and
	// start two recovery polls. JSDoc on `StreamCallbacks.onPermissionDenied`
	// already promised "Emitted once" — this enforces it.
	let permissionDeniedFired = false;

	const firstSnapTimer = setTimeout(() => {
		if (!firstSnapshotSeen && !terminal) {
			callbacks.onFirstSnapshotTimeout?.();
		}
	}, FIRST_SNAPSHOT_TIMEOUT_MS);

	function markFirst() {
		if (firstSnapshotSeen) return;
		firstSnapshotSeen = true;
		clearTimeout(firstSnapTimer);
	}

	function handleErr(err: { code?: string; message?: string } | unknown) {
		const code = (err as { code?: string })?.code;
		if (code === 'permission-denied') {
			if (permissionDeniedFired) return;
			permissionDeniedFired = true;
			callbacks.onPermissionDenied?.();
		} else {
			// Other Firestore errors (`unavailable`, etc.) — log and let the
			// first-snapshot timer or the session observer's terminal handler
			// drive the user-facing path.
			console.warn('[firestore-stream] snapshot error:', code, err);
		}
	}

	const unsubSession = onSnapshot(
		sessionRef,
		(snap) => {
			markFirst();
			if (!snap.exists()) return;
			const data = snap.data() as Record<string, unknown>;
			const docRunId = data.currentRunId as string | undefined;

			// Runs-scope guard first: because the app reuses `sid` across turns,
			// a listener can receive snapshots of a prior turn's state — either
			// from the local cache before the server version arrives, or as a
			// race between the agentStream txn flushing and our `onSnapshot`
			// firing. The subscription is tied to a specific `runId`; only
			// snapshots whose `currentRunId` matches belong to this observer.
			// Placing the guard before attempt-tracking prevents a stale
			// attempt count from polluting our baseline.
			if (docRunId !== runId) return;

			const nextAttempt = (data.currentAttempt as number | undefined) ?? 0;
			if (observedAttempt === null) {
				observedAttempt = nextAttempt;
				lastRenderedAttempt = nextAttempt;
			} else if (nextAttempt > observedAttempt) {
				// Cloud Tasks retry spawned a fresh attempt — reset render state.
				observedAttempt = nextAttempt;
				lastRenderedAttempt = nextAttempt;
				lastRenderedSeq = -1;
				callbacks.onAttemptChange?.(nextAttempt);
			}

			const status = data.status as string | undefined;
			const fromCache = snap.metadata.fromCache;

			// Cache guard on terminal transitions: Firebase docs note that the
			// first callback can be served from the local cache before the
			// server version arrives. Surface a cached terminal could leak a
			// prior-turn state even when currentRunId happens to match (e.g.
			// same sid, two subscribes on the same runId, second attempt).
			if (status === 'complete') {
				if (fromCache) return;
				const reply = data.reply as string | undefined;
				if (!reply || terminal) return;
				terminal = true;
				callbacks.onComplete(
					reply,
					(data.sources as ChatSource[] | undefined) ?? [],
					(data.title as string | undefined) ?? undefined
				);
			} else if (status === 'error') {
				if (fromCache) return;
				if (terminal) return;
				terminal = true;
				callbacks.onError((data.error as string | undefined) ?? 'unknown_error');
			}
		},
		handleErr
	);

	const unsubEvents = onSnapshot(
		eventsQuery,
		(snap) => {
			markFirst();
			for (const change of snap.docChanges()) {
				if (change.type !== 'added') continue;
				const doc = change.doc.data() as {
					attempt: number;
					seqInAttempt: number;
					type: string;
					data: Record<string, unknown>;
				};
				// Skip events already rendered (e.g. on `onSnapshot` reconnect).
				if (doc.attempt < lastRenderedAttempt) continue;
				if (doc.attempt === lastRenderedAttempt && doc.seqInAttempt <= lastRenderedSeq) continue;

				const payload = (doc.data ?? {}) as Record<string, unknown>;
				switch (doc.type) {
					case 'progress':
						callbacks.onProgress(
							(payload.stage as string) || '',
							(payload.status as string) || '',
							(payload.label as string) || '',
							payload.previews as Array<{ name: string; preview: string }> | undefined
						);
						break;
					case 'activity':
						callbacks.onActivity?.(payload as unknown as ActivityEvent);
						break;
					// `type='complete'` / `type='error'` are deliberately ignored —
					// event writes are unfenced so a stale worker could leak one
					// terminal doc before hitting OwnershipLost. The session doc
					// (fenced via `_fenced_update`) is the sole terminal source.
				}
				lastRenderedAttempt = doc.attempt;
				lastRenderedSeq = doc.seqInAttempt;
			}
		},
		handleErr
	);

	return () => {
		clearTimeout(firstSnapTimer);
		unsubSession();
		unsubEvents();
	};
}

/**
 * POST to agentStream with a Firebase ID token. Resolves to the server-
 * assigned `runId`. Throws with `status`/`reason` on non-2xx.
 */
export async function postAgentStream(
	url: string,
	body: Record<string, unknown>,
	idToken: string
): Promise<{ sessionId: string; runId: string }> {
	const res = await fetch(url, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${idToken}`
		},
		body: JSON.stringify(body)
	});
	const payload = await res.json().catch(() => null);
	if (!res.ok) {
		const reason = (payload as { error?: string } | null)?.error ?? `http_${res.status}`;
		const err = new Error(reason) as Error & { status?: number };
		err.status = res.status;
		throw err;
	}
	if (!payload || typeof payload !== 'object' || !('runId' in payload)) {
		throw new Error('malformed_response');
	}
	return payload as { sessionId: string; runId: string };
}
