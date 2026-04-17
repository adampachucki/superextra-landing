import { streamAgent, type ActivityEvent } from '$lib/sse-client';
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
	partial?: boolean;
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
let streamingText = $state('');
let streamingProgress = $state<StreamingStep[]>([]);
let streamingActivities = $state<ActivityItem[]>([]);
let abortController: AbortController | null = null;
let iosReturnHandle: IosVisibilityHandle | null = null;
let pageHidden = $state(false);

// All conversations
let conversations = $state<Conversation[]>([]);

// Restore from localStorage (or migrate from old single-conversation key)
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

async function send(text: string) {
	const trimmed = text.trim();
	if (!trimmed || loading) return;

	const sendingConvId = currentId;
	const history = buildHistory();
	messages.push({ role: 'user', text: trimmed, timestamp: Date.now() });
	loading = true;
	error = '';
	streamingText = '';
	streamingProgress = [];
	streamingActivities = [];
	persist();

	abortController = new AbortController();

	const agentUrl = import.meta.env.DEV
		? '/api/agent/stream'
		: 'https://agentstream-907466498524.us-central1.run.app';

	try {
		await streamAgent(
			agentUrl,
			{
				message: trimmed,
				sessionId: currentId,
				placeContext,
				history
			},
			{
				onProgress(stage, status, label, previews) {
					const step: StreamingStep = { stage, status, label, previews };
					const idx = streamingProgress.findIndex((p) => p.stage === stage);
					if (idx >= 0) {
						streamingProgress[idx] = step;
					} else {
						streamingProgress = [...streamingProgress, step];
					}
				},
				onToken(text) {
					streamingText += text;
				},
				onComplete(reply, sources, title) {
					const msg: ChatMessage = {
						role: 'agent',
						text: reply,
						timestamp: Date.now(),
						sources: sources?.length ? sources : undefined
					};
					if (currentId === sendingConvId) {
						messages.push(msg);
					} else if (sendingConvId) {
						appendToConversation(sendingConvId, msg);
					}
					if (title && sendingConvId) {
						const idx = conversations.findIndex((c) => c.id === sendingConvId);
						if (idx >= 0) {
							conversations[idx] = { ...conversations[idx], title };
						}
					}
				},
				onError(err) {
					if (currentId !== sendingConvId || pageHidden) return;
					if (err === 'timeout' && streamingText.trim()) {
						// Pipeline timed out but we have partial text — promote it
						messages.push({
							role: 'agent',
							text: streamingText,
							timestamp: Date.now(),
							partial: true
						});
						streamingText = '';
						error = 'timeout';
					} else if (err === 'timeout') {
						error = 'timeout';
					} else {
						error = err;
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
						// Only overwrite fields that are defined in the incoming event
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
				}
			},
			abortController.signal
		);
	} catch (e: unknown) {
		if (
			e instanceof Error &&
			e.name !== 'AbortError' &&
			currentId === sendingConvId &&
			!pageHidden
		) {
			error = 'Could not reach the server. Please check your connection.';
		}
	} finally {
		if (currentId === sendingConvId) {
			loading = false;
			streamingText = '';
			streamingProgress = [];
		}
		abortController = null;
		persist();
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
	messages = [];
	loading = false;
	error = '';
	active = false;
	placeContext = null;
	currentId = null;
	persist();
}

function switchTo(id: string) {
	if (id === currentId) return;
	if (loading) {
		abortController?.abort();
		loading = false;
		streamingText = '';
		streamingProgress = [];
		streamingActivities = [];
	}
	syncCurrentToList();
	const conv = conversations.find((c) => c.id === id);
	if (!conv) return;
	loadConversation(conv);
	persist();

	// If the last message was from the user, the agent response may still be pending
	const msgs = conv.messages;
	if (msgs.length > 0 && msgs[msgs.length - 1].role === 'user') {
		recover();
	}
}

async function recover(): Promise<boolean> {
	if (!currentId || loading) return false;
	const recoveringConvId = currentId;
	loading = true;
	recovering = true;
	error = '';
	try {
		return await recoverStream({
			getSessionId: () => recoveringConvId,
			isCurrentSession: (sid) => currentId === sid,
			onReply: (reply, sources) => {
				messages.push({ role: 'agent', text: reply, timestamp: Date.now(), sources });
				persist();
			},
			onError: (msg) => {
				error = msg;
			},
			checkUrl: (sid) =>
				import.meta.env.DEV
					? `/api/agent/check?sid=${sid}`
					: `https://us-central1-superextra-site.cloudfunctions.net/agentCheck?sid=${sid}`,
			isDuplicateReply: (reply) => messages.some((m) => m.role === 'agent' && m.text === reply)
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
			abortStream: () => abortController?.abort(),
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
		messages = [];
		loading = false;
		error = '';
		active = false;
		placeContext = null;
		currentId = null;
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
	get streamingText() {
		return streamingText;
	},
	get streamingProgress() {
		return streamingProgress;
	},
	get streamingActivities() {
		return streamingActivities;
	},
	get isStreaming() {
		return (
			streamingText.length > 0 || streamingProgress.length > 0 || streamingActivities.length > 0
		);
	},
	abort() {
		abortController?.abort();
	},
	send,
	start,
	reset,
	recover,
	handleReturn,
	switchTo,
	deleteConversation
};
