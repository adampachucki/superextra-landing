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
 * There is no browser-local conversation store. Firestore SDK persistence and
 * listener resumption cover reconnects.
 */

import type { Unsubscribe } from 'firebase/firestore';
import type { ChatSource, TimelineEvent, TurnFeedback, TurnSummary } from '$lib/chat-types';
import { getFirebase } from '$lib/firebase';
import { auth } from '$lib/auth.svelte';
import { campaignCategory } from '$lib/campaign';
import * as analytics from '$lib/analytics';

// Cache the dynamic firestore import so every attach path resolves to the
// same module object. Avoids racing parallel dynamic imports under test
// (vitest's vi.mock factory can deliver inconsistent results across
// concurrent dynamic-import calls in the same module).
let firestoreModulePromise: Promise<typeof import('firebase/firestore')> | null = null;
function getFirestoreMod() {
	if (!firestoreModulePromise) firestoreModulePromise = import('firebase/firestore');
	return firestoreModulePromise;
}

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
	kind: 'user' | 'acknowledgement' | 'status' | 'final';
	turnKind?: TurnKind | null;
	text: string;
	timestamp: number;
	turnIndex: number;
	animateReveal?: boolean;
	sources?: ChatSource[];
	turnSummary?: TurnSummary;
	activityEvents?: TimelineEvent[];
	feedback?: TurnFeedback;
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
	activeAgent: string | null;
	activeStage: string | null;
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
	acknowledgement: string | null;
	sources: ChatSource[] | null;
	turnSummary: TurnSummary | null;
	feedback: Record<string, TurnFeedback> | null;
	createdAtMs: number | null;
	acknowledgedAtMs: number | null;
	completedAtMs: number | null;
	error: string | null;
	turnKind: TurnKind | null;
}

export type TurnKind =
	| 'agent_reply'
	| 'research_report'
	| 'continuation_reply'
	| 'intake_reply'
	| 'quota_block';

export type LoadState = 'idle' | 'loading' | 'loaded' | 'missing';

/** Events listener attaches only while latest turn is in these statuses. */
const IN_FLIGHT_STATUSES = new Set(['queued', 'running', 'pending']);

const ACTIVE_AGENT_LABEL: Record<string, string> = {
	router: 'Choosing next steps',
	context_enricher: 'Building context',
	research_lead: 'Planning research',
	report_writer: 'Drafting final report',
	continue_research: 'Continuing research',
	market_landscape: 'Researching market landscape',
	menu_pricing: 'Researching menu and pricing',
	revenue_sales: 'Researching revenue and sales',
	guest_intelligence: 'Researching guest signals',
	location_traffic: 'Researching location and traffic',
	operations: 'Researching operations',
	marketing_brand: 'Researching marketing and brand',
	review_analyst: 'Analyzing reviews',
	social_analyst: 'Analyzing social platforms',
	dynamic_researcher_1: 'Researching focused angle',
	dynamic_researcher_2: 'Researching focused angle',
	dynamic_researcher_3: 'Researching focused angle'
};

const ACTIVE_STAGE_LABEL: Record<string, string> = {
	routing: 'Choosing next steps',
	building_context: 'Building context',
	planning_research: 'Planning research',
	writing_final_report: 'Drafting final report',
	continuing_research: 'Continuing research',
	specialist_research: 'Researching market signals',
	agent_work: 'Working'
};

function activeStatusLabel(session: Session | null): string | null {
	if (session?.status !== 'running') return null;
	const agentLabel = session.activeAgent ? ACTIVE_AGENT_LABEL[session.activeAgent] : null;
	if (agentLabel) return agentLabel;
	const stageLabel = session.activeStage ? ACTIVE_STAGE_LABEL[session.activeStage] : null;
	return stageLabel ?? null;
}

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
// Friendly error from the last failing agentStream call. Surfaces transport
// failures (handoff errors, auth) into the UI. Daily-research limits are
// no longer a 429 — the agent's quota gate writes the limit-reached message
// as a normal agent reply in the chat thread.
let lastError = $state<string | null>(null);
// While a startNewChat POST is in flight, the active-session listener can
// race it: the listener attaches optimistically and the first server-
// confirmed snapshot can land before agentStream's Firestore txn does (gap
// is ~0.5–1.5 s). Without this guard, `loadState` would briefly flip to
// 'missing' and the user would see "Couldn't load this chat". The guard
// suppresses that transition while a POST for `optimisticPendingSid` is
// still in flight. Cleared on POST success (listener takes over) or on
// pre-Firestore-failure local rollback.
let optimisticPendingSid: string | null = null;
let optimisticTurnSid: string | null = null;
let optimisticTurnStartedAtMs: number | null = null;
let optimisticTurnIndex: number | null = null;
let optimisticTurnMessage: string | null = null;

// Listener unsubscribes — kept outside $state because they're opaque cleanup
// handles, not reactive values.
let sessionsListUnsubscribe: Unsubscribe | null = null;
let activeSessionUnsubscribe: Unsubscribe | null = null;
let activeTurnsUnsubscribe: Unsubscribe | null = null;
let activeEventsUnsubscribe: Unsubscribe | null = null;
let activeEventsAttachInFlight: Promise<void> | null = null;
let currentEventsRunId: string | null = null;
let currentEventsCompletedTurnIndex: number | null = null;

// Events dedup — reconnects replay the same doc; key on (runId, attempt,
// seqInAttempt) to avoid duplicating timeline rows across resubscribes.
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const renderedEventKeys = new Set<string>();
// Final-answer reveal state is intentionally local to turns observed live
// in this browser session. Historical complete turns render immediately.
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const previousTurnStatus = new Map<number, Turn['status']>();
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const replyRevealTurns = new Set<number>();
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const completedActivityByTurn = new Map<number, TimelineEvent[]>();
// Analytics dedup — `research_started` fires at most once per agent run.
// eslint-disable-next-line svelte/prefer-svelte-reactivity
const analyticsStartedRuns = new Set<string>();

// Sidebar listener state — attached lazily on first consumer access.
let sidebarAttachStarted = false;
let authSubscribed = false;
let authUnsubscribe: (() => void) | null = null;

// ---------------------------------------------------------------------------
// Derived state (plain getters over $state — read inside components)
// ---------------------------------------------------------------------------

function flattenTurnsToMessages(turnList: Turn[]): ChatMessage[] {
	const msgs: ChatMessage[] = [];
	for (const turn of turnList) {
		msgs.push({
			role: 'user',
			kind: 'user',
			text: turn.userMessage,
			timestamp: turn.createdAtMs ?? Date.now(),
			turnIndex: turn.turnIndex
		});
		if (turn.acknowledgement) {
			msgs.push({
				role: 'agent',
				kind: 'acknowledgement',
				text: turn.acknowledgement,
				timestamp: turn.acknowledgedAtMs ?? turn.createdAtMs ?? Date.now(),
				turnIndex: turn.turnIndex
			});
		}
		if (turn.status === 'complete' && turn.reply) {
			const activityEvents = completedActivityByTurn.get(turn.turnIndex);
			msgs.push({
				role: 'agent',
				kind: 'final',
				turnKind: turn.turnKind,
				text: turn.reply,
				timestamp: turn.completedAtMs ?? Date.now(),
				turnIndex: turn.turnIndex,
				animateReveal: replyRevealTurns.has(turn.turnIndex),
				sources: turn.sources?.length ? turn.sources : undefined,
				turnSummary: turn.turnSummary ?? undefined,
				activityEvents: activityEvents?.length ? activityEvents : undefined,
				feedback: currentUid ? turn.feedback?.[currentUid] : undefined
			});
		}
		if (turn.status === 'error') {
			msgs.push({
				role: 'agent',
				kind: 'status',
				text: turn.error ?? 'pipeline_error',
				timestamp: turn.completedAtMs ?? Date.now(),
				turnIndex: turn.turnIndex
			});
		}
	}
	return msgs;
}

// ---------------------------------------------------------------------------
// Auth coordination — subscribe once; on sign-in, attach sidebar + user-doc
// listeners; on sign-out, detach everything and clear state.
// ---------------------------------------------------------------------------

function ensureAuthSubscribed() {
	if (authSubscribed) return;
	authSubscribed = true;
	authUnsubscribe = auth.onAuthChange((uid) => {
		detachSidebarListener();
		if (uid) {
			currentUid = uid;
			void attachSidebarListener();
		} else {
			currentUid = null;
			detachActiveListeners();
			clearActiveState();
		}
	});
	void auth.init();
}

// ---------------------------------------------------------------------------
// Sidebar listener
// ---------------------------------------------------------------------------

function detachSidebarListener() {
	sessionsListUnsubscribe?.();
	sessionsListUnsubscribe = null;
	sidebarAttachStarted = false;
	sessionsList = [];
}

async function attachSidebarListener() {
	if (sidebarAttachStarted) return;
	const uid = currentUid;
	if (!uid) return;
	sidebarAttachStarted = true;
	try {
		const { db } = await getFirebase();
		if (currentUid !== uid) {
			sidebarAttachStarted = false;
			return;
		}
		const { collection, query, where, orderBy, onSnapshot } = await getFirestoreMod();
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
}

function detachActiveEventsListener() {
	activeEventsUnsubscribe?.();
	activeEventsUnsubscribe = null;
	currentEventsRunId = null;
	currentEventsCompletedTurnIndex = null;
}

function clearActiveState() {
	activeSid = null;
	activeSession = null;
	turns = [];
	liveTimeline = [];
	loadState = 'idle';
	placeContextState = null;
	optimisticTurnSid = null;
	optimisticTurnStartedAtMs = null;
	optimisticTurnIndex = null;
	optimisticTurnMessage = null;
	renderedEventKeys.clear();
	previousTurnStatus.clear();
	replyRevealTurns.clear();
	completedActivityByTurn.clear();
	analyticsStartedRuns.clear();
}

function makeOptimisticTurn(turnIndex: number, userMessage: string, startedAtMs: number): Turn {
	return {
		turnIndex,
		runId: '',
		userMessage,
		status: 'pending',
		reply: null,
		acknowledgement: null,
		sources: null,
		turnSummary: null,
		feedback: null,
		createdAtMs: startedAtMs,
		acknowledgedAtMs: null,
		completedAtMs: null,
		error: null,
		turnKind: null
	};
}

function installOptimisticTurn(sid: string, userMessage: string, turnIndex = 1) {
	const nowMs = Date.now();
	optimisticTurnStartedAtMs = nowMs;
	optimisticTurnSid = sid;
	optimisticTurnIndex = turnIndex;
	optimisticTurnMessage = userMessage;
	if (activeSid !== sid) return;
	const optimistic = makeOptimisticTurn(turnIndex, userMessage, nowMs);
	turns = [...turns.filter((turn) => turn.turnIndex !== turnIndex), optimistic].sort(
		(a, b) => a.turnIndex - b.turnIndex
	);
	previousTurnStatus.set(turnIndex, 'pending');
	loadState = 'loading';
}

function clearOptimisticTurn() {
	optimisticTurnSid = null;
	optimisticTurnStartedAtMs = null;
	optimisticTurnIndex = null;
	optimisticTurnMessage = null;
}

function removeOptimisticTurn(sid: string, turnIndex: number) {
	if (optimisticTurnSid !== sid || optimisticTurnIndex !== turnIndex) return;
	clearOptimisticTurn();
	if (activeSid === sid) {
		turns = turns.filter(
			(turn) => !(turn.turnIndex === turnIndex && turn.runId === '' && turn.status === 'pending')
		);
	}
}

async function attachActiveListeners(sid: string) {
	// The Firestore SDK needs a signed-in user for reads even though rules are
	// path-scoped to participants. Wait for auth to resolve before subscribing.
	ensureAuthSubscribed();
	await auth.init();
	const uid = auth.uid;
	if (!uid) return;
	currentUid = uid;
	const { db } = await getFirebase();
	const firestoreMod = await getFirestoreMod();
	const { collection, doc, onSnapshot, orderBy, query } = firestoreMod;

	// Bail if the active sid has changed by the time we resolved.
	if (activeSid !== sid) return;

	const sessionRef = doc(db, 'sessions', sid);
	const turnsQuery = query(collection(db, 'sessions', sid, 'turns'), orderBy('turnIndex'));

	// Load state is resolved only by server-confirmed presence/absence.
	// Cache-only "missing" snapshots are not authoritative for fresh sids.
	loadState = 'loading';

	activeSessionUnsubscribe = onSnapshot(
		sessionRef,
		(snap) => {
			if (activeSid !== sid) return;
			const fromCache = snap.metadata.fromCache;
			const exists = snap.exists();

			// fromCache-aware initial load state (plan §7). A cache-only
			// first snapshot with exists=false is NOT authoritative.
			if (!fromCache) {
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
				activeAgent: (data.activeAgent as string | undefined) ?? null,
				activeStage: (data.activeStage as string | undefined) ?? null,
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
			const fromCache = snap.metadata.fromCache;
			let next: Turn[] = [];
			snap.forEach((docSnap) => {
				const data = docSnap.data() as Record<string, unknown>;
				const turnIndex = (data.turnIndex as number | undefined) ?? Number(docSnap.id);
				const status = ((data.status as string | undefined) ?? 'pending') as Turn['status'];
				const sourcesRaw = data.sources as ChatSource[] | null | undefined;
				const feedbackRaw = data.feedback;
				const turn: Turn = {
					turnIndex,
					runId: (data.runId as string | undefined) ?? '',
					userMessage: (data.userMessage as string | undefined) ?? '',
					status,
					reply: (data.reply as string | null | undefined) ?? null,
					acknowledgement: (data.acknowledgement as string | null | undefined) ?? null,
					sources: Array.isArray(sourcesRaw) ? sourcesRaw : null,
					turnSummary: (data.turnSummary as TurnSummary | null | undefined) ?? null,
					feedback:
						feedbackRaw && typeof feedbackRaw === 'object'
							? (feedbackRaw as Record<string, TurnFeedback>)
							: null,
					createdAtMs: toMillis(data.createdAt),
					acknowledgedAtMs: toMillis(data.acknowledgedAt),
					completedAtMs: toMillis(data.completedAt),
					error: (data.error as string | null | undefined) ?? null,
					turnKind: (data.turnKind as TurnKind | null | undefined) ?? null
				};
				next.push(turn);
				const prev = previousTurnStatus.get(turnIndex);
				const inFlight = IN_FLIGHT_STATUSES.has(status);
				if (inFlight) completedActivityByTurn.delete(turnIndex);
				if (
					!fromCache &&
					prev &&
					IN_FLIGHT_STATUSES.has(prev) &&
					!inFlight &&
					currentEventsRunId === turn.runId &&
					liveTimeline.length
				) {
					completedActivityByTurn.set(turnIndex, [...liveTimeline]);
				}
				if (
					!fromCache &&
					prev &&
					IN_FLIGHT_STATUSES.has(prev) &&
					status === 'complete' &&
					turn.reply
				) {
					replyRevealTurns.add(turnIndex);
				}
				if (!fromCache) previousTurnStatus.set(turnIndex, status);
				// Analytics — agent run lifecycle. `research_started` is deduped per
				// runId; completion transitions are naturally once-only because
				// `prev` must have been in-flight (the map is cleared on reload).
				if (
					!fromCache &&
					status === 'running' &&
					turn.runId &&
					!analyticsStartedRuns.has(turn.runId)
				) {
					analyticsStartedRuns.add(turn.runId);
					analytics.capture('research_started', { session_id: sid, run_id: turn.runId });
				}
				if (!fromCache && prev && IN_FLIGHT_STATUSES.has(prev) && status === 'complete') {
					if (turn.turnKind === 'quota_block') {
						analytics.capture('quota_block_hit', { session_id: sid });
					} else if (turn.reply) {
						analytics.capture('research_completed', {
							session_id: sid,
							run_id: turn.runId,
							duration_ms:
								turn.completedAtMs && turn.createdAtMs
									? turn.completedAtMs - turn.createdAtMs
									: undefined
						});
					}
				}
			});
			// A send can receive a cache/server snapshot before agentStream's
			// transaction-created turn is observed. For follow-ups this snapshot
			// often contains older completed turns, so preserve the local pending
			// turn until the matching server turn appears.
			if (
				optimisticTurnSid === sid &&
				optimisticTurnIndex !== null &&
				optimisticTurnStartedAtMs !== null &&
				optimisticTurnMessage !== null
			) {
				const serverOptimistic = next.find((turn) => turn.turnIndex === optimisticTurnIndex);
				if (!serverOptimistic) {
					next = [
						...next,
						makeOptimisticTurn(
							optimisticTurnIndex,
							optimisticTurnMessage,
							optimisticTurnStartedAtMs
						)
					].sort((a, b) => a.turnIndex - b.turnIndex);
				} else if (!IN_FLIGHT_STATUSES.has(serverOptimistic.status)) {
					clearOptimisticTurn();
				}
			}
			if (next.length > 0 || optimisticTurnSid !== sid || turns.length === 0) {
				turns = next;
			}
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
		liveTimeline = [];
		if (
			latest.status === 'complete' &&
			latest.turnSummary &&
			latest.runId &&
			!completedActivityByTurn.has(latest.turnIndex)
		) {
			void ensureEventsListener(sid, latest.runId, latest.turnIndex);
		} else {
			detachActiveEventsListener();
		}
		return;
	}
	const runId =
		latest.runId ||
		(session?.lastTurnIndex === latest.turnIndex ? (session.currentRunId ?? null) : null);
	if (!runId) return;
	void ensureEventsListener(sid, runId);
}

async function ensureEventsListener(
	sid: string,
	runId: string,
	completedTurnIndex: number | null = null
) {
	if (
		activeEventsUnsubscribe &&
		currentEventsRunId === runId &&
		currentEventsCompletedTurnIndex === completedTurnIndex
	) {
		return;
	}
	// In-flight dedup: when session and turn snapshots both fire close together
	// they each trigger maybeAttachEventsListener → ensureEventsListener. The
	// first call hasn't set `activeEventsUnsubscribe` yet (it's still awaiting
	// dynamic imports), so the second call would race a duplicate attach.
	// Wait for any in-flight attach to settle, then re-check the early-return
	// condition before doing the work again.
	if (
		activeEventsAttachInFlight &&
		currentEventsRunId === runId &&
		currentEventsCompletedTurnIndex === completedTurnIndex
	) {
		return;
	}
	// Different runId — detach the old listener first.
	detachActiveEventsListener();
	currentEventsRunId = runId;
	currentEventsCompletedTurnIndex = completedTurnIndex;
	// Reset the per-run dedup set; different runs legitimately share keys.
	renderedEventKeys.clear();
	liveTimeline = [];

	let resolveAttach!: () => void;
	const attachPromise = new Promise<void>((r) => {
		resolveAttach = r;
	});
	activeEventsAttachInFlight = attachPromise;
	try {
		const { db } = await getFirebase();
		const firestoreMod = await getFirestoreMod();
		const { collection, onSnapshot, orderBy, query, where } = firestoreMod;
		// Bail if the active sid/runId moved while we awaited imports.
		if (
			activeSid !== sid ||
			currentEventsRunId !== runId ||
			currentEventsCompletedTurnIndex !== completedTurnIndex
		) {
			return;
		}
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
				const added: TimelineEvent[] = [];
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
					added.push(payload);
				}
				if (!added.length) return;
				if (completedTurnIndex !== null) {
					const existing = completedActivityByTurn.get(completedTurnIndex) ?? [];
					completedActivityByTurn.set(completedTurnIndex, [...existing, ...added]);
					turns = [...turns];
				} else {
					liveTimeline = [...liveTimeline, ...added];
				}
			},
			(err) => {
				console.warn('[chat-state] events listener error:', err);
			}
		);
	} catch (err) {
		console.warn('[chat-state] events listener bootstrap failed:', err);
	} finally {
		resolveAttach();
		// Identity-check: a newer attach may have already replaced our marker
		// (different runId / completedTurnIndex). Only clear the slot if it
		// still points to OUR promise.
		if (activeEventsAttachInFlight === attachPromise) {
			activeEventsAttachInFlight = null;
		}
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

function agentCancelUrl() {
	return '/api/agent/cancel';
}

async function postAgentStream(body: Record<string, unknown>): Promise<void> {
	const idToken = await auth.getIdToken();
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

function friendlyAgentError(code: string): string {
	switch (code) {
		case 'AUTH_REQUIRED':
			return 'Sign in to continue.';
		case 'previous_turn_in_flight':
			return 'A previous message is still being processed. Try again in a moment.';
		default:
			return 'Could not send message. Please try again.';
	}
}

function startNewChat(query: string, place: PlaceContext | null): string {
	const trimmed = query.trim();
	if (!trimmed) throw new Error('empty_message');
	analytics.capture('prompt_submitted', {
		prompt_length: trimmed.length,
		is_first_message: true,
		pillar: campaignCategory() ?? undefined
	});
	const sid = uuid();
	// Optimistic submission. Flip local state FIRST so the chat panel
	// renders immediately; the snapshot listener attaches with
	// `optimisticPendingSid === sid` so the pre-txn `exists=false` snapshot
	// doesn't briefly flip `loadState` to 'missing'.
	optimisticPendingSid = sid;
	selectSession(sid);
	placeContextState = place;
	installOptimisticTurn(sid, trimmed);

	void postAgentStream({
		sessionId: sid,
		message: trimmed,
		placeContext: place,
		isFirstMessage: true
	})
		.then(() => {
			if (optimisticPendingSid === sid) optimisticPendingSid = null;
		})
		.catch(async (err: unknown) => {
			// Distinguish pre-Firestore failure (POST rejected before txn ran
			// — no doc materialized) from post-Firestore failure (txn ran,
			// then gearHandoff failed and gearHandoffCleanup wrote
			// status='error'). Single getDoc check tells us which side of the
			// fence we're on. Post-Firestore failures are rendered by the
			// listener via the existing loadState machinery; pre-Firestore
			// failures need an explicit local flip to 'missing' so the chat
			// page surfaces "Couldn't start this chat".
			let docExists = false;
			try {
				const { db } = await getFirebase();
				const firestoreMod = await getFirestoreMod();
				const snap = await firestoreMod.getDoc(firestoreMod.doc(db, 'sessions', sid));
				docExists = snap.exists();
			} catch (e) {
				console.warn('[chat-state] getDoc check failed; treating as pre-Firestore failure:', e);
			}
			if (optimisticPendingSid === sid) optimisticPendingSid = null;
			if (!docExists && activeSid === sid) {
				detachActiveListeners();
				clearActiveState();
				loadState = 'missing';
			}
			const code = err instanceof Error ? err.message : String(err);
			lastError = friendlyAgentError(code);
			console.warn('[chat-state] startNewChat POST failed:', err);
		});

	return sid;
}

async function sendFollowUp(message: string): Promise<void> {
	const trimmed = message.trim();
	if (!trimmed) return;
	analytics.capture('prompt_submitted', {
		prompt_length: trimmed.length,
		is_first_message: false,
		pillar: campaignCategory() ?? undefined
	});
	const sid = activeSid;
	if (!sid) throw new Error('no_active_session');
	const turnIndex = Math.max(activeSession?.lastTurnIndex ?? 0, turns.at(-1)?.turnIndex ?? 0) + 1;
	installOptimisticTurn(sid, trimmed, turnIndex);
	try {
		await postAgentStream({
			sessionId: sid,
			message: trimmed,
			placeContext: placeContextState,
			isFirstMessage: false
		});
	} catch (err) {
		removeOptimisticTurn(sid, turnIndex);
		const code = err instanceof Error ? err.message : String(err);
		lastError = friendlyAgentError(code);
		throw err;
	}
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
	const idToken = await auth.getIdToken();
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

function activeCancelTarget(): { sid: string; runId: string; turnIndex: number } | null {
	if (!activeSid || !activeSession || !currentUid) return null;
	if (!activeSession.participants.includes(currentUid)) return null;
	if (activeSession.status !== 'running') return null;
	if (!activeSession.currentRunId || !Number.isInteger(activeSession.lastTurnIndex)) return null;
	const latest = turns[turns.length - 1];
	if (latest) {
		if (latest.turnIndex !== activeSession.lastTurnIndex) return null;
		if (latest.runId !== activeSession.currentRunId) return null;
		if (latest.status !== 'running') return null;
	}
	return {
		sid: activeSid,
		runId: activeSession.currentRunId,
		turnIndex: activeSession.lastTurnIndex
	};
}

async function cancelActiveTurn(): Promise<void> {
	if (!activeSid) throw new Error('no_active_session');
	const target = activeCancelTarget();
	if (!target) throw new Error('cancel_not_active');
	const idToken = await auth.getIdToken();
	const res = await fetch(agentCancelUrl(), {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${idToken}`
		},
		body: JSON.stringify(target)
	});
	if (!res.ok) {
		const payload = await res.json().catch(() => null);
		const reason = (payload as { error?: string } | null)?.error ?? `http_${res.status}`;
		const err = new Error(reason) as Error & { status?: number };
		err.status = res.status;
		throw err;
	}
}

function reset() {
	detachActiveListeners();
	clearActiveState();
}

function markReplyRevealed(turnIndex: number) {
	replyRevealTurns.delete(turnIndex);
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
		if (latest) return IN_FLIGHT_STATUSES.has(latest.status);
		if (optimisticPendingSid && optimisticPendingSid === activeSid) return true;
		// No turn doc yet, but agentStream was invoked — session status
		// signals the in-flight window before the turn doc lands.
		const status = activeSession?.status;
		return !!status && IN_FLIGHT_STATUSES.has(status);
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
		// Lazy-attach on first read from the UI. The auth subscription is the
		// real gate — sidebar listener only fires once auth resolves to a UID.
		ensureAuthSubscribed();
		if (!sidebarAttachStarted && currentUid) void attachSidebarListener();
		return sessionsList;
	},
	get lastError(): string | null {
		return lastError;
	},
	clearError() {
		lastError = null;
	},
	get currentTurnStartedAtMs(): number | null {
		const latest = turns[turns.length - 1];
		if (!latest) return null;
		if (!IN_FLIGHT_STATUSES.has(latest.status)) return null;
		if (
			optimisticTurnSid === activeSid &&
			optimisticTurnStartedAtMs !== null &&
			optimisticTurnIndex === latest.turnIndex
		) {
			return Math.min(latest.createdAtMs ?? optimisticTurnStartedAtMs, optimisticTurnStartedAtMs);
		}
		return latest.createdAtMs ?? null;
	},
	get liveTimeline(): TimelineEvent[] {
		return liveTimeline;
	},
	get liveStatusLabel(): string | null {
		return activeStatusLabel(activeSession);
	},
	get canDelete(): boolean {
		if (!currentUid || !activeSession) return false;
		return activeSession.userId === currentUid;
	},
	get canCancel(): boolean {
		return activeCancelTarget() !== null;
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
	cancelActiveTurn,
	deleteSession,
	markReplyRevealed,
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
		authUnsubscribe?.();
		authUnsubscribe = null;
		authSubscribed = false;
		sidebarAttachStarted = false;
		clearActiveState();
		currentUid = null;
		sessionsList = [];
		lastError = null;
	},
	setCurrentUid(uid: string | null) {
		currentUid = uid;
	},
	// For tests that want to avoid the real attach path.
	markSidebarAttached() {
		sidebarAttachStarted = true;
	}
};
