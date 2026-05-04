/**
 * Firestore-driven chat state (plan §9).
 *
 * Four live Firestore reads drive the UI:
 *   1. **Sidebar listener** — `sessions where participants array-contains
 *      currentUid order by updatedAt desc`. Attaches once anon auth resolves;
 *      re-renders the sidebar as sessions are created, updated, or deleted.
 *   2. **Active session listener** — `sessions/{sid}`. Drives the activeSession
 *      reactive value, `canDelete`, `loadState`.
 *   3. **Active turns listener** — `sessions/{sid}/turns order by turnIndex`.
 *      Source of truth for the flattened `messages` array and the current
 *      turn's status.
 *   4. **Active events listener** — `sessions/{sid}/events where runId ==
 *      currentRunId order by (attempt, seqInAttempt)`. Attaches only while
 *      the latest turn is `queued`/`running`; detaches on the turn doc's
 *      terminal status (plan §10 / pin #6).
 *
 * There is no browser-local conversation store. Stage 6 deleted
 * `chat-recovery.ts` and `ios-sse-workaround.ts` — the Firestore SDK's
 * persistent cache + automatic listener resumption cover the reconnect cases
 * those modules used to mitigate.
 */

import type { Unsubscribe } from 'firebase/firestore';
import type { ChatSource, TimelineEvent, TurnSummary } from '$lib/chat-types';
import { ensureAnonAuth, getFirebase, getIdToken } from '$lib/firebase';

/** True iff `err` is `FirebaseUnavailableInSSRError` from `$lib/firebase`.
 *  Checked by name rather than `instanceof` so test-time module mocks that
 *  omit the class still compile. */
function isSSRBootstrapSkip(err: unknown): boolean {
	return err instanceof Error && err.name === 'FirebaseUnavailableInSSRError';
}

/** crypto.randomUUID() is only available in secure contexts (HTTPS / localhost).
 *  Fall back to crypto.getRandomValues() which works everywhere. */
function uuid(): string {
	if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
		return crypto.randomUUID();
	}
	return '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, (c) =>
		(+c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (+c / 4)))).toString(16)
	);
}

export interface ChatMessage {
	role: 'user' | 'agent';
	text: string;
	timestamp: number;
	turnIndex: number;
	animateText?: boolean;
	sources?: ChatSource[];
	turnSummary?: TurnSummary;
}

export interface PlaceContext {
	name: string;
	secondary: string;
	placeId: string;
}

/** Shape of the `sessions/{sid}` document as consumed by the client. */
export interface Session {
	sid: string;
	userId: string;
	participants: string[];
	title: string | null;
	placeContext: PlaceContext | null;
	status: 'queued' | 'running' | 'complete' | 'error' | null;
	currentRunId: string | null;
	lastTurnIndex: number;
	createdAtMs: number | null;
	updatedAtMs: number | null;
}

/** Sidebar entry — subset of Session shape exposed by the sidebar listener. */
export interface SessionSummary {
	sid: string;
	title: string | null;
	placeContext: PlaceContext | null;
	updatedAtMs: number | null;
	userId: string;
	lastTurnIndex: number;
	status: 'queued' | 'running' | 'complete' | 'error' | null;
}

/** Shape of a `sessions/{sid}/turns/{turnKey}` document. */
export interface Turn {
	turnIndex: number;
	runId: string;
	userMessage: string;
	status: 'pending' | 'running' | 'complete' | 'error';
	reply: string | null;
	sources: ChatSource[] | null;
	turnSummary: TurnSummary | null;
	createdAtMs: number | null;
	completedAtMs: number | null;
	error: string | null;
}

export type LoadState = 'idle' | 'loading' | 'loaded' | 'missing' | 'loadTimedOut';

const LOAD_TIMEOUT_MS = 10_000;

/** Events listener attaches only while latest turn is in these statuses. */
const IN_FLIGHT_STATUSES = new Set(['queued', 'running', 'pending']);

function toMillis(value: unknown): number | null {
	if (typeof value === 'number' && Number.isFinite(value)) return value;
	if (
		typeof value === 'object' &&
		value !== null &&
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

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let currentUid = $state<string | null>(null);
let sessionsList = $state<SessionSummary[]>([]);
let activeSid = $state<string | null>(null);
let activeSession = $state<Session | null>(null);
let turns = $state<Turn[]>([]);
let liveTimeline = $state<TimelineEvent[]>([]);
let loadState = $state<LoadState>('idle');
let placeContextState = $state<PlaceContext | null>(null);
// While a startNewChat POST is in flight, the active-session listener can
// race it: the listener attaches optimistically and the first server-
// confirmed snapshot can land before agentStream's Firestore txn does (gap
// is ~0.5–1.5 s). Without this guard, `loadState` would briefly flip to
// 'missing' and the user would see "Couldn't load this chat". The guard
// suppresses that transition while a POST for `optimisticPendingSid` is
// still in flight. Cleared on POST success (listener takes over) or on
// pre-Firestore-failure local rollback.
let optimisticPendingSid: string | null = null;

// Listener unsubscribes — kept outside $state because they're opaque cleanup
// handles, not reactive values.
let sessionsListUnsubscribe: Unsubscribe | null = null;
let activeSessionUnsubscribe: Unsubscribe | null = null;
let activeTurnsUnsubscribe: Unsubscribe | null = null;
let activeEventsUnsubscribe: Unsubscribe | null = null;
let loadTimeoutHandle: ReturnType<typeof setTimeout> | null = null;
let currentEventsRunId: string | null = null;

// Events dedup — reconnects replay the same doc; key on (runId, attempt,
// seqInAttempt) to avoid duplicating timeline rows across resubscribes.
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const renderedEventKeys = new Set<string>();
// Final-answer typewriter state is intentionally local to turns observed live
// in this browser session. Historical complete turns render immediately.
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const previousTurnStatus = new Map<number, Turn['status']>();
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const replyTypewriterTurns = new Set<number>();

// Sidebar listener state — attached lazily on first consumer access.
let sidebarAttachStarted = false;

// ---------------------------------------------------------------------------
// Derived state (plain getters over $state — read inside components)
// ---------------------------------------------------------------------------

function flattenTurnsToMessages(turnList: Turn[]): ChatMessage[] {
	const msgs: ChatMessage[] = [];
	for (const turn of turnList) {
		msgs.push({
			role: 'user',
			text: turn.userMessage,
			timestamp: turn.createdAtMs ?? Date.now(),
			turnIndex: turn.turnIndex
		});
		if (turn.status === 'complete' && turn.reply) {
			msgs.push({
				role: 'agent',
				text: turn.reply,
				timestamp: turn.completedAtMs ?? Date.now(),
				turnIndex: turn.turnIndex,
				animateText: replyTypewriterTurns.has(turn.turnIndex),
				sources: turn.sources?.length ? turn.sources : undefined,
				turnSummary: turn.turnSummary ?? undefined
			});
		}
	}
	return msgs;
}

// ---------------------------------------------------------------------------
// Sidebar listener
// ---------------------------------------------------------------------------

async function attachSidebarListener() {
	if (sidebarAttachStarted) return;
	sidebarAttachStarted = true;
	try {
		const uid = await ensureAnonAuth();
		currentUid = uid;
		const { db } = await getFirebase();
		const firestoreMod = await import('firebase/firestore');
		const { collection, query, where, orderBy, onSnapshot } = firestoreMod;
		const q = query(
			collection(db, 'sessions'),
			where('participants', 'array-contains', uid),
			orderBy('updatedAt', 'desc')
		);
		sessionsListUnsubscribe = onSnapshot(
			q,
			(snap) => {
				const next: SessionSummary[] = [];
				snap.forEach((docSnap) => {
					const data = docSnap.data() as Record<string, unknown>;
					next.push({
						sid: docSnap.id,
						title: (data.title as string | undefined) ?? null,
						placeContext: (data.placeContext as PlaceContext | undefined) ?? null,
						updatedAtMs: toMillis(data.updatedAt),
						userId: (data.userId as string | undefined) ?? '',
						lastTurnIndex: (data.lastTurnIndex as number | undefined) ?? 0,
						status: (data.status as SessionSummary['status']) ?? null
					});
				});
				sessionsList = next;
			},
			(err) => {
				console.warn('[chat-state] sidebar listener error:', err);
			}
		);
	} catch (err) {
		// In SSR/prerender, Firebase can't bootstrap — swallow silently.
		// Any real runtime error on the client still logs.
		if (!isSSRBootstrapSkip(err)) {
			console.warn('[chat-state] sidebar listener bootstrap failed:', err);
		}
		sidebarAttachStarted = false;
	}
}

// ---------------------------------------------------------------------------
// Active session + turns + events listeners
// ---------------------------------------------------------------------------

function detachActiveListeners() {
	activeSessionUnsubscribe?.();
	activeSessionUnsubscribe = null;
	activeTurnsUnsubscribe?.();
	activeTurnsUnsubscribe = null;
	detachActiveEventsListener();
	if (loadTimeoutHandle) {
		clearTimeout(loadTimeoutHandle);
		loadTimeoutHandle = null;
	}
}

function detachActiveEventsListener() {
	activeEventsUnsubscribe?.();
	activeEventsUnsubscribe = null;
	currentEventsRunId = null;
}

function clearActiveState() {
	activeSid = null;
	activeSession = null;
	turns = [];
	liveTimeline = [];
	loadState = 'idle';
	placeContextState = null;
	renderedEventKeys.clear();
	previousTurnStatus.clear();
	replyTypewriterTurns.clear();
}

async function attachActiveListeners(sid: string) {
	// Ensure anon auth has resolved before subscribing — the SDK needs a token
	// even though rules are now path-scoped.
	await ensureAnonAuth();
	const { db } = await getFirebase();
	const firestoreMod = await import('firebase/firestore');
	const { collection, doc, onSnapshot, orderBy, query } = firestoreMod;

	// Bail if the active sid has changed by the time we resolved.
	if (activeSid !== sid) return;

	const sessionRef = doc(db, 'sessions', sid);
	const turnsQuery = query(collection(db, 'sessions', sid, 'turns'), orderBy('turnIndex'));

	// Load state: arm the 10 s cache-only timeout. Server-confirmed snapshots
	// clear it; cache-only snapshots do not.
	loadState = 'loading';
	if (loadTimeoutHandle) clearTimeout(loadTimeoutHandle);
	loadTimeoutHandle = setTimeout(() => {
		if (activeSid === sid && loadState === 'loading') {
			loadState = 'loadTimedOut';
		}
	}, LOAD_TIMEOUT_MS);

	activeSessionUnsubscribe = onSnapshot(
		sessionRef,
		(snap) => {
			if (activeSid !== sid) return;
			const fromCache = snap.metadata.fromCache;
			const exists = snap.exists();

			// fromCache-aware initial load state (plan §7). A cache-only
			// first snapshot with exists=false is NOT authoritative.
			if (!fromCache) {
				if (loadTimeoutHandle) {
					clearTimeout(loadTimeoutHandle);
					loadTimeoutHandle = null;
				}
				if (exists) {
					loadState = 'loaded';
					// Doc materialized — clear pending guard if it was for this sid.
					if (optimisticPendingSid === sid) optimisticPendingSid = null;
				} else if (optimisticPendingSid !== sid) {
					// Only flip to 'missing' once the optimistic window has closed.
					// While a startNewChat POST is in flight for this sid, the
					// pre-txn gap can show exists=false; suppress the flip and
					// stay in 'loading' until the doc materializes (success path)
					// or the POST rejects and clears the guard (failure path).
					loadState = 'missing';
				}
				// else: keep loadState='loading'.
			} else if (exists) {
				// Cache-only but the doc exists — safe to flip to loaded
				// for render purposes; the server version will confirm soon.
				loadState = 'loaded';
			}

			if (!exists) {
				activeSession = null;
				return;
			}
			const data = snap.data() as Record<string, unknown>;
			const next: Session = {
				sid,
				userId: (data.userId as string | undefined) ?? '',
				participants: (data.participants as string[] | undefined) ?? [],
				title: (data.title as string | undefined) ?? null,
				placeContext: (data.placeContext as PlaceContext | undefined) ?? null,
				status: (data.status as Session['status']) ?? null,
				currentRunId: (data.currentRunId as string | undefined) ?? null,
				lastTurnIndex: (data.lastTurnIndex as number | undefined) ?? 0,
				createdAtMs: toMillis(data.createdAt),
				updatedAtMs: toMillis(data.updatedAt)
			};
			activeSession = next;
			// Keep placeContextState in sync so consumers that read it for
			// follow-up submissions have the server-stored context.
			if (next.placeContext) {
				placeContextState = next.placeContext;
			}
			maybeAttachEventsListener();
		},
		(err) => {
			console.warn('[chat-state] active session listener error:', err);
		}
	);

	activeTurnsUnsubscribe = onSnapshot(
		turnsQuery,
		(snap) => {
			if (activeSid !== sid) return;
			const next: Turn[] = [];
			snap.forEach((docSnap) => {
				const data = docSnap.data() as Record<string, unknown>;
				const turnIndex = (data.turnIndex as number | undefined) ?? Number(docSnap.id);
				const status = ((data.status as string | undefined) ?? 'pending') as Turn['status'];
				const sourcesRaw = data.sources as ChatSource[] | null | undefined;
				const turn: Turn = {
					turnIndex,
					runId: (data.runId as string | undefined) ?? '',
					userMessage: (data.userMessage as string | undefined) ?? '',
					status,
					reply: (data.reply as string | null | undefined) ?? null,
					sources: Array.isArray(sourcesRaw) ? sourcesRaw : null,
					turnSummary: (data.turnSummary as TurnSummary | null | undefined) ?? null,
					createdAtMs: toMillis(data.createdAt),
					completedAtMs: toMillis(data.completedAt),
					error: (data.error as string | null | undefined) ?? null
				};
				next.push(turn);
				const prev = previousTurnStatus.get(turnIndex);
				if (prev && prev !== 'complete' && status === 'complete' && turn.reply) {
					replyTypewriterTurns.add(turnIndex);
				}
				previousTurnStatus.set(turnIndex, status);
			});
			turns = next;
			maybeAttachEventsListener();
		},
		(err) => {
			console.warn('[chat-state] active turns listener error:', err);
		}
	);
}

/** Attach (or detach) the events listener based on the latest turn's status.
 *  Per plan §10 / pin #6 the detach trigger is the TURN doc's terminal
 *  status, not the session's — during the worker's fenced two-doc write the
 *  two can briefly disagree. */
function maybeAttachEventsListener() {
	const sid = activeSid;
	if (!sid) {
		detachActiveEventsListener();
		return;
	}
	const latest = turns[turns.length - 1];
	const session = activeSession;
	if (!latest || !session) {
		// No turn yet — session doc's currentRunId may still be useful if
		// the user just sent a message and we're waiting for agentStream's
		// transaction to land the turn doc.
		const runId = session?.currentRunId ?? null;
		const inFlight = session?.status && IN_FLIGHT_STATUSES.has(session.status);
		if (runId && inFlight) {
			void ensureEventsListener(sid, runId);
		} else {
			detachActiveEventsListener();
		}
		return;
	}
	const inFlight = IN_FLIGHT_STATUSES.has(latest.status);
	if (!inFlight) {
		detachActiveEventsListener();
		liveTimeline = [];
		return;
	}
	const runId = latest.runId || session?.currentRunId || null;
	if (!runId) return;
	void ensureEventsListener(sid, runId);
}

async function ensureEventsListener(sid: string, runId: string) {
	if (activeEventsUnsubscribe && currentEventsRunId === runId) return;
	// Different runId — detach the old listener first.
	detachActiveEventsListener();
	currentEventsRunId = runId;
	// Reset the per-run dedup set; different runs legitimately share keys.
	renderedEventKeys.clear();
	liveTimeline = [];

	try {
		const { db } = await getFirebase();
		const firestoreMod = await import('firebase/firestore');
		const { collection, onSnapshot, orderBy, query, where } = firestoreMod;
		// Bail if the active sid/runId moved while we awaited imports.
		if (activeSid !== sid || currentEventsRunId !== runId) return;
		const q = query(
			collection(db, 'sessions', sid, 'events'),
			where('runId', '==', runId),
			orderBy('attempt'),
			orderBy('seqInAttempt')
		);
		activeEventsUnsubscribe = onSnapshot(
			q,
			(snap) => {
				if (activeSid !== sid || currentEventsRunId !== runId) return;
				for (const change of snap.docChanges()) {
					if (change.type !== 'added') continue;
					const data = change.doc.data() as {
						attempt?: number;
						seqInAttempt?: number;
						type?: string;
						data?: Record<string, unknown>;
					};
					const attempt = data.attempt ?? 0;
					const seq = data.seqInAttempt ?? 0;
					const key = `${runId}:${attempt}:${seq}`;
					if (renderedEventKeys.has(key)) continue;
					renderedEventKeys.add(key);
					// `type='complete'` / `type='error'` events are ignored by
					// design — the turn doc is the sole terminal source.
					if (data.type !== 'timeline') continue;
					const payload = (data.data ?? {}) as TimelineEvent;
					liveTimeline = [...liveTimeline, payload];
				}
			},
			(err) => {
				console.warn('[chat-state] events listener error:', err);
			}
		);
	} catch (err) {
		console.warn('[chat-state] events listener bootstrap failed:', err);
	}
}

// ---------------------------------------------------------------------------
// Submission
// ---------------------------------------------------------------------------

function agentStreamUrl() {
	return '/api/agent/stream';
}

function agentDeleteUrl() {
	return '/api/agent/delete';
}

async function postAgentStream(body: Record<string, unknown>): Promise<void> {
	const idToken = await getIdToken();
	const res = await fetch(agentStreamUrl(), {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${idToken}`
		},
		body: JSON.stringify(body)
	});
	if (!res.ok) {
		const payload = await res.json().catch(() => null);
		const reason = (payload as { error?: string } | null)?.error ?? `http_${res.status}`;
		const err = new Error(reason) as Error & { status?: number };
		err.status = res.status;
		throw err;
	}
}

async function startNewChat(query: string, place: PlaceContext | null): Promise<string> {
	const trimmed = query.trim();
	if (!trimmed) throw new Error('empty_message');
	const sid = uuid();
	// Optimistic submission (plan §6). agentStream now blocks ~60–90 s on
	// the gear path waiting for the first NDJSON line; without this flip
	// the user sees a blank screen until the POST returns. Flip local state
	// FIRST so the chat panel renders immediately; the snapshot listener
	// attaches with `optimisticPendingSid === sid` so the pre-txn
	// `exists=false` snapshot doesn't briefly flip `loadState` to 'missing'.
	optimisticPendingSid = sid;
	selectSession(sid);
	placeContextState = place;

	try {
		await postAgentStream({
			sessionId: sid,
			message: trimmed,
			placeContext: place,
			isFirstMessage: true
		});
		// Success: doc has materialized (or will any moment). Listener takes
		// over for normal lifecycle.
		if (optimisticPendingSid === sid) optimisticPendingSid = null;
	} catch (err) {
		// Distinguish pre-Firestore failure (POST rejected before txn ran —
		// no doc materialized) from post-Firestore failure (txn ran, then
		// gearHandoff failed and gearHandoffCleanup wrote status='error').
		// Single getDoc check tells us which side of the fence we're on.
		// IMPORTANT (plan §v3.9 P2): wrap getFirebase + dynamic import inside
		// the same try — both can throw (offline import failure, Firebase
		// init error, auth missing). Without the wrap, a Firebase-bootstrap
		// failure would propagate from the catch and skip the local
		// rollback, leaving the session selected with no doc ever
		// materializing.
		let docExists = false;
		try {
			const { db } = await getFirebase();
			const firestoreMod = await import('firebase/firestore');
			const snap = await firestoreMod.getDoc(firestoreMod.doc(db, 'sessions', sid));
			docExists = snap.exists();
		} catch (e) {
			// any read/bootstrap error → treat as pre-Firestore failure
			console.warn('[chat-state] getDoc check failed; treating as pre-Firestore failure:', e);
		}
		if (optimisticPendingSid === sid) optimisticPendingSid = null;
		if (!docExists && activeSid === sid) {
			// Pre-Firestore failure — clean up local state.
			detachActiveListeners();
			clearActiveState();
			activeSid = null;
			loadState = 'idle';
		}
		// Otherwise post-Firestore failure: doc has status='error' from
		// gearHandoffCleanup; the listener renders the error state via the
		// existing loadState machinery. No frontend rollback needed.
		throw err;
	}
	return sid;
}

async function sendFollowUp(message: string): Promise<void> {
	const trimmed = message.trim();
	if (!trimmed) return;
	const sid = activeSid;
	if (!sid) throw new Error('no_active_session');
	await postAgentStream({
		sessionId: sid,
		message: trimmed,
		placeContext: placeContextState,
		isFirstMessage: false
	});
}

function selectSession(sid: string) {
	if (activeSid === sid) return;
	detachActiveListeners();
	clearActiveState();
	activeSid = sid;
	loadState = 'loading';
	void attachActiveListeners(sid);
	// Kick the sidebar listener too if it hasn't started — entering a chat
	// implies the user is interacting with the agent UI.
	void attachSidebarListener();
}

async function deleteSession(sid: string): Promise<void> {
	const idToken = await getIdToken();
	const res = await fetch(agentDeleteUrl(), {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${idToken}`
		},
		body: JSON.stringify({ sid })
	});
	if (!res.ok) {
		const payload = await res.json().catch(() => null);
		const reason = (payload as { error?: string } | null)?.error ?? `http_${res.status}`;
		const err = new Error(reason) as Error & { status?: number };
		err.status = res.status;
		throw err;
	}
	if (activeSid === sid) {
		detachActiveListeners();
		clearActiveState();
	}
	// Sidebar listener picks up the removal via its own snapshot; no manual
	// splice needed.
}

function reset() {
	detachActiveListeners();
	clearActiveState();
}

function markReplyTyped(turnIndex: number) {
	replyTypewriterTurns.delete(turnIndex);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export const chatState = {
	get messages(): ChatMessage[] {
		return flattenTurnsToMessages(turns);
	},
	get turns(): Turn[] {
		return turns;
	},
	get loading(): boolean {
		const latest = turns[turns.length - 1];
		if (!latest) {
			// No turn doc yet, but agentStream was invoked — session status
			// signals the in-flight window before the turn doc lands.
			const status = activeSession?.status;
			return !!status && IN_FLIGHT_STATUSES.has(status);
		}
		return IN_FLIGHT_STATUSES.has(latest.status);
	},
	get error(): string {
		const latest = turns[turns.length - 1];
		if (latest?.status === 'error') return latest.error ?? 'pipeline_error';
		return '';
	},
	get active(): boolean {
		return activeSid !== null;
	},
	get placeContext(): PlaceContext | null {
		return activeSession?.placeContext ?? placeContextState;
	},
	set placeContext(p: PlaceContext | null) {
		placeContextState = p;
	},
	get activeSid(): string | null {
		return activeSid;
	},
	get activeSession(): Session | null {
		return activeSession;
	},
	get sessionsList(): SessionSummary[] {
		// Lazy-attach on first read from the UI.
		if (!sidebarAttachStarted) void attachSidebarListener();
		return sessionsList;
	},
	get currentTurnStartedAtMs(): number | null {
		const latest = turns[turns.length - 1];
		if (!latest) return null;
		if (!IN_FLIGHT_STATUSES.has(latest.status)) return null;
		return latest.createdAtMs ?? null;
	},
	get liveTimeline(): TimelineEvent[] {
		return liveTimeline;
	},
	get canDelete(): boolean {
		if (!currentUid || !activeSession) return false;
		return activeSession.userId === currentUid;
	},
	get loadState(): LoadState {
		return loadState;
	},
	get currentUid(): string | null {
		return currentUid;
	},

	startNewChat,
	sendFollowUp,
	selectSession,
	deleteSession,
	markReplyTyped,
	reset
};

// ---------------------------------------------------------------------------
// Test-only helpers — enable deterministic resets between tests.
// ---------------------------------------------------------------------------

export const _testing = {
	reset() {
		detachActiveListeners();
		sessionsListUnsubscribe?.();
		sessionsListUnsubscribe = null;
		sidebarAttachStarted = false;
		clearActiveState();
		currentUid = null;
		sessionsList = [];
	},
	setCurrentUid(uid: string | null) {
		currentUid = uid;
	},
	// For tests that want to avoid the real attach path.
	markSidebarAttached() {
		sidebarAttachStarted = true;
	}
};
