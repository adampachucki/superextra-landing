import { postAgentStream, subscribeToSession, type ActivityEvent } from '$lib/firestore-stream';
import { ensureAnonAuth, getIdToken } from '$lib/firebase';
import { recoverStream } from '$lib/chat-recovery';
import { handleReturnFromHidden, type IosVisibilityHandle } from '$lib/ios-sse-workaround';

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

interface ChatSource {
	title: string;
	url: string;
	domain?: string;
}

interface StreamingStep {
	stage: string;
	status: string;
	label: string;
	previews?: Array<{ name: string; preview: string }>;
}

export type ActivityCategory = 'data' | 'search' | 'read' | 'analyze';

export interface ActivityItem {
	id: string;
	category: ActivityCategory;
	status: 'pending' | 'running' | 'complete';
	label: string;
	detail?: string;
	url?: string;
	agent?: string;
	timestamp: number;
}

interface ChatMessage {
	role: 'user' | 'agent';
	text: string;
	timestamp: number;
	sources?: ChatSource[];
}

interface PlaceContext {
	name: string;
	secondary: string;
	placeId: string;
}

interface Conversation {
	id: string;
	title: string;
	messages: ChatMessage[];
	placeContext: PlaceContext | null;
	createdAt: number;
	updatedAt: number;
}

const STORAGE_KEY = 'se_chats';
const OLD_STORAGE_KEY = 'se_chat';
const MAX_CONVERSATIONS = 50;

// Working state — the currently loaded conversation
let messages = $state<ChatMessage[]>([]);
let loading = $state(false);
let recovering = $state(false);
let error = $state('');
let active = $state(false);
let placeContext = $state<PlaceContext | null>(null);
let currentId = $state<string | null>(null);

// Streaming state (ephemeral — never persisted to localStorage)
let streamingProgress = $state<StreamingStep[]>([]);
let streamingActivities = $state<ActivityItem[]>([]);
let currentRunId = $state<string | null>(null);
// Terminal-reply dedup key. Set to the runId the first time a reply lands
// (via Firestore observer OR chat-recovery REST poll) so a second delivery
// of the same turn's terminal is a no-op. Reset to null at the start of a
// new subscription. Replaces the old text-equality dedup, which false-
// rejected legitimately-new short replies across turns.
let appendedReplyForRunId: string | null = null;
let subscriptionUnsubscribe: (() => void) | null = null;
let iosReturnHandle: IosVisibilityHandle | null = null;
let pageHidden = $state(false);

// All conversations
let conversations = $state<Conversation[]>([]);

// Restore from localStorage (or migrate from old single-conversation key).
// One-shot migration from se_chat (single-conv) to se_chats (multi-conv) +
// merge of legacy `sessionId` field into `id`. Safe to delete this whole
// block once no v1 clients remain (~6 months after rollout of multi-conv).
if (typeof localStorage !== 'undefined') {
	try {
		const stored = localStorage.getItem(STORAGE_KEY);
		if (stored) {
			const data = JSON.parse(stored);
			conversations = data.conversations || [];

			// One-time migration: merge old separate sessionId into id
			// sessionId is the Firestore-known value, so it becomes the canonical id
			let migrated = false;
			const oldIdToNewId: Record<string, string> = {};
			const claimedIds: Record<string, true> = {};
			for (const c of conversations) {
				const oldId = c.id;
				const oldSid = (c as unknown as Record<string, unknown>).sessionId as string | undefined;
				if (oldSid) {
					if (!claimedIds[oldSid]) {
						c.id = oldSid;
						claimedIds[oldSid] = true;
					}
					// else: duplicate sessionId from old reuse bug — keep existing c.id
				}
				claimedIds[c.id] = true;
				oldIdToNewId[oldId] = c.id;
				if ('sessionId' in c) {
					delete (c as unknown as Record<string, unknown>).sessionId;
					migrated = true;
				}
			}
			if (migrated) {
				data.activeId = data.activeId ? (oldIdToNewId[data.activeId] ?? null) : null;
				localStorage.setItem(
					STORAGE_KEY,
					JSON.stringify({ activeId: data.activeId, conversations })
				);
			}

			// URL ?sid= takes precedence over stored activeId on refresh
			let restored = false;
			if (typeof window !== 'undefined') {
				const urlSid = new URL(window.location.href).searchParams.get('sid');
				if (urlSid) {
					const conv = conversations.find((c: Conversation) => c.id === urlSid);
					if (conv) {
						loadConversation(conv);
						restored = true;
					}
				}
			}
			if (!restored && data.activeId) {
				const conv = conversations.find((c: Conversation) => c.id === data.activeId);
				if (conv) loadConversation(conv);
			}
		} else {
			const old = localStorage.getItem(OLD_STORAGE_KEY);
			if (old) {
				const s = JSON.parse(old);
				if (s.messages?.length) {
					const conv: Conversation = {
						id: s.sessionId || uuid(),
						title: generateTitle(s.messages[0]?.text || 'Untitled'),
						messages: s.messages,
						placeContext: s.placeContext || null,
						createdAt: s.messages[0]?.timestamp || Date.now(),
						updatedAt: s.messages[s.messages.length - 1]?.timestamp || Date.now()
					};
					conversations = [conv];
					loadConversation(conv);
				}
				localStorage.removeItem(OLD_STORAGE_KEY);
				persist();
			}
		}
	} catch {
		// localStorage parse failures are non-critical
	}
}

function generateTitle(text: string): string {
	const clean = text.trim();
	if (clean.length <= 50) return clean;
	const truncated = clean.slice(0, 50);
	const lastSpace = truncated.lastIndexOf(' ');
	return (lastSpace > 20 ? truncated.slice(0, lastSpace) : truncated) + '...';
}

function loadConversation(conv: Conversation) {
	messages = [...conv.messages];
	placeContext = conv.placeContext;
	currentId = conv.id;
	active = conv.messages.length > 0;
	error = '';
	loading = false;
}

function syncCurrentToList() {
	if (!currentId || !messages.length) return;
	const idx = conversations.findIndex((c) => c.id === currentId);
	if (idx >= 0) {
		conversations[idx] = {
			...conversations[idx],
			messages: [...messages],
			placeContext,
			updatedAt: messages[messages.length - 1]?.timestamp || conversations[idx].updatedAt
		};
	}
}

function persist() {
	if (typeof localStorage === 'undefined') return;
	syncCurrentToList();
	try {
		localStorage.setItem(
			STORAGE_KEY,
			JSON.stringify({
				activeId: currentId,
				conversations
			})
		);
	} catch {
		// Storage full or unavailable — non-critical
	}
}

function buildHistory(): Array<{ role: string; parts: Array<{ text: string }> }> {
	return messages.map((m) => ({
		role: m.role === 'agent' ? 'model' : 'user',
		parts: [{ text: m.text }]
	}));
}

function appendToConversation(convId: string, msg: ChatMessage) {
	const idx = conversations.findIndex((c) => c.id === convId);
	if (idx < 0) return;
	conversations[idx] = {
		...conversations[idx],
		messages: [...conversations[idx].messages, msg],
		updatedAt: msg.timestamp
	};
}

// Same-origin rewrites for both dev and prod. `firebase.json` defines
// `/api/agent/stream` → `agentStream` and `/api/agent/check` → `agentCheck`
// under the `agent` hosting target, and the Vite dev proxy mirrors them.
// Post-decoupling `agentStream` is a plain POST-returns-JSON enqueue (no
// SSE), so the earlier `cloudfunctions.net` GFE-proxy SSE workaround is no
// longer load-bearing — see docs/deployment-gotchas.md "Cloud Functions".
function agentStreamUrl() {
	return '/api/agent/stream';
}

function agentCheckUrl(sid: string, runId: string) {
	return `/api/agent/check?sid=${encodeURIComponent(sid)}&runId=${encodeURIComponent(runId)}`;
}

function cleanupSubscription() {
	if (subscriptionUnsubscribe) {
		subscriptionUnsubscribe();
		subscriptionUnsubscribe = null;
	}
}

function buildStreamCallbacks(sendingConvId: string | null, sendingRunId: string) {
	return {
		onProgress(
			stage: string,
			status: string,
			label: string,
			previews?: Array<{ name: string; preview: string }>
		) {
			if (currentId !== sendingConvId) return;
			const step: StreamingStep = { stage, status, label, previews };
			const idx = streamingProgress.findIndex((p) => p.stage === stage);
			if (idx >= 0) {
				streamingProgress[idx] = step;
			} else {
				streamingProgress = [...streamingProgress, step];
			}
		},
		onActivity(activity: ActivityEvent) {
			if (currentId !== sendingConvId) return;
			if (activity.status === 'all-complete') {
				streamingActivities = streamingActivities.map((a) =>
					a.category === activity.category && a.status !== 'complete'
						? { ...a, status: 'complete' as const }
						: a
				);
				return;
			}
			const { status, id, category, label, detail, url, agent } = activity;
			const idx = streamingActivities.findIndex((a) => a.id === id);
			if (idx >= 0) {
				const update: Partial<ActivityItem> = { status };
				if (label !== undefined) update.label = label;
				if (detail !== undefined) update.detail = detail;
				if (url !== undefined) update.url = url;
				if (agent !== undefined) update.agent = agent;
				streamingActivities[idx] = { ...streamingActivities[idx], ...update };
			} else {
				streamingActivities = [
					...streamingActivities,
					{ id, category, status, label, detail, url, agent, timestamp: Date.now() }
				];
			}
		},
		onAttemptChange() {
			if (currentId !== sendingConvId) return;
			// Cloud Tasks retry — drop UI state from the failed attempt so it
			// doesn't mingle with the retry's events. Seed a visible cue so
			// the UI doesn't show a blank panel during the gap before the new
			// attempt's first real event arrives (plan Phase 5 / Tier 2.1).
			streamingActivities = [];
			streamingProgress = [{ stage: 'retrying', status: 'running', label: 'Retrying…' }];
		},
		onComplete(reply: string, sources: ChatSource[] | undefined, title?: string) {
			if (pageHidden) return;
			// Dedup by runId — chat-recovery may surface the same turn's reply
			// first if Firestore was briefly blocked. Old text-equality dedup
			// false-rejected legitimately-new short replies across turns
			// ("OK", "Yes"). Since the terminal is written once per turn and
			// keyed on runId, the runId is the right dedup key.
			if (appendedReplyForRunId === sendingRunId) {
				// Already appended for this turn (recover() raced us).
			} else {
				appendedReplyForRunId = sendingRunId;
				const msg: ChatMessage = {
					role: 'agent',
					text: reply,
					timestamp: Date.now(),
					sources: sources?.length ? sources : undefined
				};
				if (currentId === sendingConvId) {
					messages.push(msg);
				} else if (sendingConvId) {
					const idx = conversations.findIndex((c) => c.id === sendingConvId);
					if (idx >= 0) {
						appendToConversation(sendingConvId, msg);
					}
				}
			}
			if (title && sendingConvId) {
				const idx = conversations.findIndex((c) => c.id === sendingConvId);
				if (idx >= 0) {
					conversations[idx] = { ...conversations[idx], title };
				}
			}
			if (currentId === sendingConvId) {
				loading = false;
				streamingProgress = [];
			}
			cleanupSubscription();
			currentRunId = null;
			persist();
		},
		onError(err: string) {
			if (currentId !== sendingConvId || pageHidden) return;
			error = err || 'unknown_error';
			loading = false;
			streamingProgress = [];
			cleanupSubscription();
			currentRunId = null;
			persist();
		},
		onPermissionDenied() {
			if (currentId !== sendingConvId) return;
			// Fall back to the REST poll. Usually caused by ad-blockers on
			// *.googleapis.com or corporate proxies killing the WebSocket
			// channel used by Firestore.
			console.warn('Firestore PERMISSION_DENIED — falling back to agentCheck poll');
			recover().catch(() => {});
		},
		onFirstSnapshotTimeout() {
			if (currentId !== sendingConvId) return;
			// Same fallback shape as PERMISSION_DENIED. We keep the live
			// subscription running in case it recovers; the poll just
			// races it.
			console.warn('Firestore first-snapshot timeout — falling back to agentCheck poll');
			recover().catch(() => {});
		}
	};
}

async function send(text: string) {
	const trimmed = text.trim();
	if (!trimmed || loading) return;

	const sendingConvId = currentId;
	const sessionId = sendingConvId;
	if (!sessionId) return;
	const history = buildHistory();
	const isFirstMessageForApi = messages.filter((m) => m.role === 'agent').length === 0;
	messages.push({ role: 'user', text: trimmed, timestamp: Date.now() });
	loading = true;
	error = '';
	streamingProgress = [];
	streamingActivities = [];
	cleanupSubscription();
	persist();

	let runId: string;
	try {
		await ensureAnonAuth();
		const idToken = await getIdToken();
		const resp = await postAgentStream(
			agentStreamUrl(),
			{
				message: trimmed,
				sessionId,
				placeContext,
				history,
				isFirstMessage: isFirstMessageForApi
			},
			idToken
		);
		runId = resp.runId;
	} catch (e: unknown) {
		const err = e as { status?: number; message?: string };
		if (currentId === sendingConvId && !pageHidden) {
			if (err.status === 401) error = 'auth_required';
			else if (err.status === 403) error = 'ownership_mismatch';
			else if (err.status === 409) error = 'previous_turn_in_flight';
			else if (err.status === 429) error = err.message || 'rate_limited';
			else error = 'Could not reach the server. Please check your connection.';
			loading = false;
		}
		persist();
		return;
	}

	currentRunId = runId;
	appendedReplyForRunId = null;
	recoveryStartedForRunId = null;

	try {
		const unsubscribe = await subscribeToSession(
			sessionId,
			runId,
			buildStreamCallbacks(sendingConvId, runId)
		);
		// If the user already moved on, drop the subscription immediately.
		if (currentId !== sendingConvId) {
			unsubscribe();
			return;
		}
		subscriptionUnsubscribe = unsubscribe;
	} catch (e: unknown) {
		if (currentId === sendingConvId && !pageHidden) {
			const msg = e instanceof Error ? e.message : 'subscribe_failed';
			console.warn('subscribeToSession failed, falling back to poll:', msg);
			// Try REST polling as a last resort.
			await recover().catch(() => {
				error = 'Could not subscribe to progress. Please try again.';
				loading = false;
			});
		}
	}
}

function start(query: string, place: PlaceContext | null) {
	syncCurrentToList();

	const id = uuid();
	const conv: Conversation = {
		id,
		title: generateTitle(query),
		messages: [],
		placeContext: place,
		createdAt: Date.now(),
		updatedAt: Date.now()
	};

	conversations.unshift(conv);
	if (conversations.length > MAX_CONVERSATIONS) {
		conversations = conversations.slice(0, MAX_CONVERSATIONS);
	}

	currentId = id;
	messages = [];
	loading = false;
	placeContext = place;
	active = true;
	error = '';

	send(query);
}

function reset() {
	syncCurrentToList();
	cleanupSubscription();
	messages = [];
	loading = false;
	error = '';
	active = false;
	placeContext = null;
	currentId = null;
	currentRunId = null;
	persist();
}

function switchTo(id: string) {
	if (id === currentId) return;
	if (loading) {
		cleanupSubscription();
		loading = false;
		streamingProgress = [];
		streamingActivities = [];
	}
	cleanupSubscription();
	currentRunId = null;
	syncCurrentToList();
	const conv = conversations.find((c) => c.id === id);
	if (!conv) return;
	loadConversation(conv);
	persist();

	// If the last message was from the user, there's an in-flight turn to
	// resume. Firestore is the source of truth for the current runId; read
	// it, then either subscribe (queued/running) or render a terminal state.
	const msgs = conv.messages;
	if (msgs.length > 0 && msgs[msgs.length - 1].role === 'user') {
		resumeIfInFlight(id).catch((err) => {
			console.warn('resumeIfInFlight failed:', err);
		});
	}
}

async function resumeIfInFlight(sessionId: string): Promise<void> {
	if (currentId !== sessionId) return;
	loading = true;
	recovering = true;
	error = '';
	try {
		await ensureAnonAuth();
		const { db } = await import('$lib/firebase').then((m) => m.getFirebase());
		const { doc, getDoc } = await import('firebase/firestore');
		const snap = await getDoc(doc(db, 'sessions', sessionId));
		if (currentId !== sessionId) return;
		if (!snap.exists()) {
			error = 'Session not found. Please start a new conversation.';
			loading = false;
			recovering = false;
			return;
		}
		const data = snap.data() as Record<string, unknown>;
		const status = data.status as string | undefined;
		const runId = data.currentRunId as string | undefined;
		if (status === 'complete') {
			const reply = data.reply as string | undefined;
			// RunId dedup — same contract as `buildStreamCallbacks.onComplete`
			// and `recover().isDuplicateReply`. Text-equality dedup here was
			// the last surviving spot that false-rejected legitimately-new
			// short replies across turns on refresh-after-complete.
			if (reply && runId && appendedReplyForRunId !== runId) {
				appendedReplyForRunId = runId;
				messages.push({
					role: 'agent',
					text: reply,
					timestamp: Date.now(),
					sources: (data.sources as ChatSource[] | undefined)?.length
						? (data.sources as ChatSource[])
						: undefined
				});
				// Mirror the server-generated title. Firestore observer's
				// `onComplete` already does this for fresh runs, but the
				// resume-after-reload path missed it — so titles persisted
				// for users who stayed on the tab and dropped for cold reloads.
				const serverTitle = data.title as string | undefined;
				if (serverTitle) {
					const idx = conversations.findIndex((c) => c.id === sessionId);
					if (idx >= 0) {
						conversations[idx] = { ...conversations[idx], title: serverTitle };
					}
				}
				persist();
			}
			loading = false;
			recovering = false;
			return;
		}
		if (status === 'error') {
			error = (data.error as string) || 'pipeline_error';
			loading = false;
			recovering = false;
			return;
		}
		if (!runId) {
			loading = false;
			recovering = false;
			return;
		}
		// status is queued or running — subscribe with the server-authoritative runId.
		currentRunId = runId;
		appendedReplyForRunId = null;
		recoveryStartedForRunId = null;
		const unsub = await subscribeToSession(
			sessionId,
			runId,
			buildStreamCallbacks(sessionId, runId)
		);
		if (currentId !== sessionId) {
			unsub();
			return;
		}
		subscriptionUnsubscribe = unsub;
		recovering = false;
	} catch (err) {
		console.warn('resumeIfInFlight error:', err);
		if (currentId === sessionId) {
			await recover().catch(() => {
				error = 'Could not subscribe to progress. Please try again.';
				loading = false;
				recovering = false;
			});
		}
	}
}

// One-shot guard: `onPermissionDenied` can fire from both Firestore observers
// (session doc + events collection-group) and `onFirstSnapshotTimeout` fires
// independently. Without this guard two polls would race for the same run.
// Reset per new subscription in `send()` / `resumeIfInFlight()` / `switchTo()`.
let recoveryStartedForRunId: string | null = null;

async function recover(): Promise<boolean> {
	if (!currentId) return false;
	const recoveringConvId = currentId;
	const runId = currentRunId;
	if (!runId) return false;
	if (recoveryStartedForRunId === runId) return false;
	recoveryStartedForRunId = runId;
	if (!loading) loading = true;
	recovering = true;
	error = '';
	try {
		return await recoverStream({
			getSession: () => ({ sessionId: recoveringConvId, runId }),
			isCurrentSession: (sid) => currentId === sid,
			onReply: (reply, sources, title) => {
				// Dedup by runId — buildStreamCallbacks' onComplete may have
				// already appended this same reply via Firestore.
				if (appendedReplyForRunId === runId) return;
				appendedReplyForRunId = runId;
				messages.push({ role: 'agent', text: reply, timestamp: Date.now(), sources });
				// Sync server-generated title — mirrors the Firestore observer's
				// onComplete path (chat-state `buildStreamCallbacks`). Without
				// this, the REST-recovered conversation keeps its client
				// placeholder instead of the worker-generated title.
				if (title && recoveringConvId) {
					const idx = conversations.findIndex((c) => c.id === recoveringConvId);
					if (idx >= 0) {
						conversations[idx] = { ...conversations[idx], title };
					}
				}
				persist();
			},
			onError: (msg) => {
				error = msg;
			},
			checkUrl: (sid, rid) => agentCheckUrl(sid, rid),
			getIdToken: async () => {
				try {
					return await getIdToken();
				} catch {
					return null;
				}
			},
			// `reply` is ignored — runId is the canonical dedup key. The
			// signature still passes reply for compatibility but we only use
			// the runId-scoped closure flag here.
			isDuplicateReply: () => appendedReplyForRunId === runId
		});
	} finally {
		loading = false;
		recovering = false;
	}
}

function handleReturn(hiddenMs = Infinity) {
	// Clear any pending poll/timeout from a prior visibilitychange.
	iosReturnHandle?.cancel();
	iosReturnHandle = handleReturnFromHidden(
		{
			isLoading: () => loading,
			setLoading: (v) => {
				loading = v;
			},
			abortStream: () => cleanupSubscription(),
			recover: () => {
				recover();
			},
			hasPendingUserMessage: () =>
				messages.length > 0 && messages[messages.length - 1].role === 'user',
			getSessionId: () => currentId
		},
		hiddenMs
	);
}

function deleteConversation(id: string) {
	conversations = conversations.filter((c) => c.id !== id);
	if (id === currentId) {
		cleanupSubscription();
		messages = [];
		loading = false;
		error = '';
		active = false;
		placeContext = null;
		currentId = null;
		currentRunId = null;
	}
	persist();
}

export const chatState = {
	get messages() {
		return messages;
	},
	get loading() {
		return loading;
	},
	get recovering() {
		return recovering;
	},
	get error() {
		return error;
	},
	set pageHidden(v: boolean) {
		pageHidden = v;
	},
	get active() {
		return active;
	},
	get placeContext() {
		return placeContext;
	},
	set placeContext(p: PlaceContext | null) {
		placeContext = p;
	},
	get conversations() {
		return conversations;
	},
	get activeId() {
		return currentId;
	},
	get streamingProgress() {
		return streamingProgress;
	},
	get streamingActivities() {
		return streamingActivities;
	},
	get isStreaming() {
		return streamingProgress.length > 0 || streamingActivities.length > 0;
	},
	abort() {
		cleanupSubscription();
	},
	send,
	start,
	reset,
	recover,
	handleReturn,
	switchTo,
	deleteConversation
};
