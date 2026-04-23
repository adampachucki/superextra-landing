/**
 * Firestore-backed progress stream. Reads are from the durable Firestore
 * events stream + turn docs that the worker writes; writes never happen from
 * the browser.
 *
 * Under the server-stored-sessions schema (plan §5):
 *
 *   - `sessions/{sid}` — holds stable session-level metadata: `userId`
 *     (creator), `participants[]`, `title`, `currentRunId`, `currentAttempt`,
 *     `status`, `lastTurnIndex`, `updatedAt`. Title is the only terminal-ish
 *     field here; the rest are progress signals.
 *   - `sessions/{sid}/turns/{turnKey}` — the authoritative terminal source
 *     for answer rendering. Worker's fenced two-doc write lands
 *     `{status, reply, sources, turnSummary, completedAt, error}` here
 *     atomically with the session-doc flip.
 *   - `sessions/{sid}/events/{id}` — append-only progress events. Ordered
 *     by `(attempt, seqInAttempt)`, filtered by `runId`. Event writes are
 *     unfenced so a stale worker can leak one terminal event doc before
 *     hitting OwnershipLost; we deliberately ignore `type='complete'` /
 *     `type='error'` here to close that leak.
 *
 * We subscribe to three observers:
 *
 *   1. `sessions/{sid}` — delivers `title` for onComplete, drives
 *      `onAttemptChange` on retries. NOT the terminal source. (Plan §9.)
 *   2. `sessions/{sid}/turns/{turnKey}` — **the terminal source.** Terminal
 *      transitions on this doc are fenced, so a stale worker cannot flip
 *      them. `onComplete` and `onError` fire exclusively from here.
 *   3. `sessions/{sid}/events` filtered by runId — progress/activity only.
 *      Per-session path, no collection-group + no userId filter, matching
 *      the plan §6 path-scoped rules.
 *
 * Cache semantics: we ignore `fromCache` snapshots of the turn doc for
 * terminal-state transitions, which prevents a stale `status=complete`
 * cached from a previous run-of-this-browser from firing onComplete before
 * the server confirms.
 *
 * Events listener detach keys off the TURN doc's terminal status, not the
 * session's (pin #6 from Stage 4 handoff). Session-side and turn-side of
 * the fenced two-doc transaction can briefly disagree in the listener's
 * commit window; the turn-doc terminal status is authoritative.
 *
 * First-snapshot timeout: if none of the three observers delivers a
 * callback within 10s, we call `onFirstSnapshotTimeout`. Stage 6 will
 * decide whether to keep this safety net or replace it with the
 * fromCache-aware initial load state described in plan §7.
 */

import { getFirebase, ensureAnonAuth } from './firebase';

export interface ChatSource {
	title: string;
	url: string;
	domain?: string;
}

export interface TurnCounts {
	webQueries: number;
	sources: number;
	venues: number;
	platforms: number;
}

export interface TurnSummary {
	startedAtMs: number;
	finishedAtMs: number;
	elapsedMs: number;
	notes: Array<{
		text: string;
		noteSource: 'deterministic' | 'llm';
		counts: TurnCounts;
	}>;
	finalCounts: TurnCounts;
}

export type TimelineEvent =
	| {
			kind: 'note';
			id: string;
			text: string;
			noteSource: 'deterministic' | 'llm';
			counts: TurnCounts;
			ts?: number;
	  }
	| {
			kind: 'detail';
			id: string;
			group: 'search' | 'platform' | 'source' | 'warning';
			family:
				| 'Searching the web'
				| 'Google Maps'
				| 'TripAdvisor'
				| 'Google reviews'
				| 'Public sources'
				| 'Warnings';
			text: string;
			ts?: number;
	  }
	| {
			kind: 'drafting';
			id: string;
			text: 'Drafting the answer…';
			ts?: number;
	  };

export interface StreamCallbacks {
	onTimelineEvent?: (event: TimelineEvent) => void;
	onComplete: (
		reply: string,
		sources: ChatSource[],
		title?: string,
		turnSummary?: TurnSummary
	) => void;
	onError: (error: string) => void;
	/** Emitted when the session doc's `currentAttempt` increases mid-run.
	 *  Caller should clear streaming UI + render a brief "Retrying…" cue. */
	onAttemptChange?: (attempt: number) => void;
	/** Emitted once when any observer returns `PERMISSION_DENIED`. */
	onPermissionDenied?: () => void;
	/** Emitted if no snapshot has arrived within 10 s — caller should
	 *  fall back to REST polling via `chat-recovery`. */
	onFirstSnapshotTimeout?: () => void;
}

const FIRST_SNAPSHOT_TIMEOUT_MS = 10_000;

/** Turn doc IDs are zero-padded 4-digit strings (plan §5 / Stage 4). */
function turnDocKey(turnIdx: number): string {
	return String(turnIdx).padStart(4, '0');
}

/**
 * Subscribe to durable progress for a (sessionId, runId, turnIdx) triple.
 * Returns an unsubscribe function. Safe to call multiple times; each call
 * creates an independent subscription.
 *
 * `turnIdx` is required — it names the turn doc this subscription targets.
 * Callers (chat-state) already know this from agentStream's response or
 * from the session doc's `lastTurnIndex`; passing it explicitly avoids an
 * extra round-trip to read the session doc just to derive the turn path.
 */
export async function subscribeToSession(
	sessionId: string,
	runId: string,
	turnIdx: number,
	callbacks: StreamCallbacks
): Promise<() => void> {
	// Even though path-scoped rules no longer require a uid filter, we still
	// gate the subscription on anonymous auth so the SDK has a token for
	// the read — Firestore rules gate everything behind `request.auth`.
	await ensureAnonAuth();
	const { db } = await getFirebase();
	const firestoreMod = await import('firebase/firestore');
	const { doc, onSnapshot, collection, query, where, orderBy } = firestoreMod;

	const sessionRef = doc(db, 'sessions', sessionId);
	const turnRef = doc(db, 'sessions', sessionId, 'turns', turnDocKey(turnIdx));
	const eventsQuery = query(
		collection(db, 'sessions', sessionId, 'events'),
		where('runId', '==', runId),
		orderBy('attempt'),
		orderBy('seqInAttempt')
	);

	let observedAttempt: number | null = null;
	let lastRenderedAttempt = -1;
	let lastRenderedSeq = -1;
	let firstSnapshotSeen = false;
	let terminal = false;
	// Latest title from the session-doc observer — merged into the terminal
	// callback when the turn doc settles. May be undefined if the session
	// observer hasn't emitted yet by the time the turn terminal fires; in
	// that case `onComplete` receives `title=undefined` which callers
	// already tolerate (the callback signature marks it optional).
	let latestTitle: string | undefined;
	// One-shot per subscription: all three observers share `handleErr`, so
	// a permission-denied on multiple would double-fire `onPermissionDenied`
	// and start two recovery polls. JSDoc on `StreamCallbacks.onPermissionDenied`
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
			// first-snapshot timer or the turn observer's terminal handler
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

			// Runs-scope guard: the app reuses `sid` across turns, so a
			// listener can receive snapshots of a prior turn's state (either
			// from the local cache before the server version arrives, or as
			// a race between agentStream's txn flushing and our `onSnapshot`
			// firing). The subscription is tied to a specific `runId`; only
			// snapshots whose `currentRunId` matches belong here. Placing
			// the guard before attempt tracking prevents a stale attempt
			// count from polluting our baseline.
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

			// Capture the title so the turn observer can merge it into its
			// terminal callback. Title is session-level under the new schema
			// (plan §5).
			const title = data.title as string | undefined;
			if (typeof title === 'string' && title.length > 0) {
				latestTitle = title;
			}
		},
		handleErr
	);

	const unsubTurn = onSnapshot(
		turnRef,
		(snap) => {
			markFirst();
			if (!snap.exists()) return;
			const data = snap.data() as Record<string, unknown>;
			// Defensive: turn docs carry their own `runId`. If somehow a
			// stale turn doc for a prior run is observed, ignore it.
			const docRunId = data.runId as string | undefined;
			if (docRunId !== undefined && docRunId !== runId) return;

			const status = data.status as string | undefined;
			const fromCache = snap.metadata.fromCache;

			// Cache guard on terminal transitions: Firebase docs note the
			// first callback can be served from the local cache before the
			// server version arrives. A cached terminal could leak a prior
			// turn's final state.
			if (status === 'complete') {
				if (fromCache) return;
				const reply = data.reply as string | undefined;
				if (!reply || terminal) return;
				terminal = true;
				callbacks.onComplete(
					reply,
					(data.sources as ChatSource[] | undefined) ?? [],
					latestTitle,
					(data.turnSummary as TurnSummary | undefined) ?? undefined
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
					case 'timeline':
						callbacks.onTimelineEvent?.(payload as TimelineEvent);
						break;
					// `type='complete'` / `type='error'` are deliberately ignored —
					// event writes are unfenced so a stale worker could leak one
					// terminal doc before hitting OwnershipLost. The turn doc
					// (fenced via `_fenced_update_session_and_turn`) is the sole
					// terminal source.
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
		unsubTurn();
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
