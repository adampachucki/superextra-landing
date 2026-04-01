interface ChatSource {
	title: string;
	url: string;
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
	sessionId: string;
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
let error = $state('');
let active = $state(false);
let sessionId = $state('');
let placeContext = $state<PlaceContext | null>(null);
let currentId = $state<string | null>(null);

// All conversations
let conversations = $state<Conversation[]>([]);

// Restore from localStorage (or migrate from old single-conversation key)
if (typeof localStorage !== 'undefined') {
	try {
		const stored = localStorage.getItem(STORAGE_KEY);
		if (stored) {
			const data = JSON.parse(stored);
			conversations = data.conversations || [];
			if (data.activeId) {
				const conv = conversations.find((c: Conversation) => c.id === data.activeId);
				if (conv) loadConversation(conv);
			}
		} else {
			const old = localStorage.getItem(OLD_STORAGE_KEY);
			if (old) {
				const s = JSON.parse(old);
				if (s.messages?.length) {
					const conv: Conversation = {
						id: s.sessionId || crypto.randomUUID(),
						title: generateTitle(s.messages[0]?.text || 'Untitled'),
						messages: s.messages,
						sessionId: s.sessionId || '',
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
	sessionId = conv.sessionId;
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
			sessionId,
			placeContext,
			updatedAt: messages[messages.length - 1]?.timestamp || conversations[idx].updatedAt
		};
	}
}

function persist() {
	if (typeof localStorage === 'undefined') return;
	syncCurrentToList();
	localStorage.setItem(
		STORAGE_KEY,
		JSON.stringify({
			activeId: currentId,
			conversations
		})
	);
}

function getOrCreateSessionId(): string {
	if (sessionId) return sessionId;
	const id =
		globalThis.crypto?.randomUUID?.() ??
		Array.from(crypto.getRandomValues(new Uint8Array(16)))
			.map((b, i) => ([4, 6, 8, 10].includes(i) ? '-' : '') + b.toString(16).padStart(2, '0'))
			.join('');
	sessionId = id;
	return id;
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
	persist();

	try {
		const agentUrl = import.meta.env.DEV
			? '/api/agent'
			: 'https://us-central1-superextra-site.cloudfunctions.net/agent';
		const res = await fetch(agentUrl, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				message: trimmed,
				sessionId: getOrCreateSessionId(),
				placeContext,
				history
			})
		});

		const data = await res.json();

		if (!res.ok || !data.ok) {
			if (currentId === sendingConvId) {
				error = data.error || 'Something went wrong. Please try again.';
			}
			return;
		}

		const sources: ChatSource[] | undefined = data.sources?.length ? data.sources : undefined;
		const reply: ChatMessage = { role: 'agent', text: data.reply, timestamp: Date.now(), sources };
		if (currentId === sendingConvId) {
			messages.push(reply);
		} else if (sendingConvId) {
			appendToConversation(sendingConvId, reply);
		}

		// Update title if AI-generated one came back
		if (data.title && sendingConvId) {
			const idx = conversations.findIndex((c) => c.id === sendingConvId);
			if (idx >= 0) {
				conversations[idx] = { ...conversations[idx], title: data.title };
			}
		}
	} catch {
		if (currentId === sendingConvId) {
			error = 'Could not reach the server. Please check your connection.';
		}
	} finally {
		if (currentId === sendingConvId) {
			loading = false;
		}
		persist();
	}
}

function start(query: string, place: PlaceContext | null) {
	syncCurrentToList();

	const id = crypto.randomUUID();
	const sid = getOrCreateSessionId();
	const conv: Conversation = {
		id,
		title: generateTitle(query),
		messages: [],
		sessionId: sid,
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
	sessionId = sid;
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
	sessionId = '';
	placeContext = null;
	currentId = null;
	persist();
}

function switchTo(id: string) {
	if (id === currentId) return;
	syncCurrentToList();
	const conv = conversations.find((c) => c.id === id);
	if (!conv) return;
	loadConversation(conv);
	persist();
}

function switchToBySessionId(sid: string) {
	const conv = conversations.find((c) => c.sessionId === sid);
	if (!conv || conv.id === currentId) return;
	syncCurrentToList();
	loadConversation(conv);
	persist();
}

async function recover(): Promise<boolean> {
	if (!sessionId || loading) return false;
	loading = true;
	error = '';
	try {
		const checkUrl = import.meta.env.DEV
			? `/api/agent/check?sid=${sessionId}`
			: `https://us-central1-superextra-site.cloudfunctions.net/agentCheck?sid=${sessionId}`;
		const res = await fetch(checkUrl);
		const data = await res.json();
		if (
			data.ok &&
			data.reply &&
			!messages.some((m) => m.role === 'agent' && m.text === data.reply)
		) {
			const sources: ChatSource[] | undefined = data.sources?.length ? data.sources : undefined;
			messages.push({ role: 'agent', text: data.reply, timestamp: Date.now(), sources });
			persist();
			return true;
		}
	} catch {
		// recovery failed silently — caller will fall back to resend
	} finally {
		loading = false;
	}
	return false;
}

function deleteConversation(id: string) {
	conversations = conversations.filter((c) => c.id !== id);
	if (id === currentId) {
		messages = [];
		loading = false;
		error = '';
		active = false;
		sessionId = '';
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
	get error() {
		return error;
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
	get sessionId() {
		return sessionId;
	},
	send,
	start,
	reset,
	recover,
	switchTo,
	switchToBySessionId,
	deleteConversation
};
