interface ChatMessage {
	role: 'user' | 'agent';
	text: string;
	timestamp: number;
}

interface PlaceContext {
	name: string;
	secondary: string;
	placeId: string;
}

let messages = $state<ChatMessage[]>([]);
let loading = $state(false);
let error = $state('');
let active = $state(false);
let sessionId = $state('');
let placeContext = $state<PlaceContext | null>(null);

function getOrCreateSessionId(): string {
	if (sessionId) return sessionId;
	const stored = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('se_chat_session') : null;
	if (stored) {
		sessionId = stored;
		return stored;
	}
	const id = globalThis.crypto?.randomUUID?.()
		?? Array.from(crypto.getRandomValues(new Uint8Array(16)))
			.map((b, i) => ([4, 6, 8, 10].includes(i) ? '-' : '') + b.toString(16).padStart(2, '0'))
			.join('');
	sessionId = id;
	if (typeof sessionStorage !== 'undefined') sessionStorage.setItem('se_chat_session', id);
	return id;
}

function buildHistory(): Array<{ role: string; parts: Array<{ text: string }> }> {
	return messages.map((m) => ({
		role: m.role === 'agent' ? 'model' : 'user',
		parts: [{ text: m.text }]
	}));
}

async function send(text: string) {
	const trimmed = text.trim();
	if (!trimmed || loading) return;

	const history = buildHistory();
	messages.push({ role: 'user', text: trimmed, timestamp: Date.now() });
	loading = true;
	error = '';

	try {
		const res = await fetch('/api/agent', {
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
			error = data.error || 'Something went wrong. Please try again.';
			return;
		}

		messages.push({ role: 'agent', text: data.reply, timestamp: Date.now() });
	} catch {
		error = 'Could not reach the server. Please check your connection.';
	} finally {
		loading = false;
	}
}

function start(query: string, place: PlaceContext | null) {
	placeContext = place;
	active = true;
	send(query);
}

function reset() {
	messages = [];
	loading = false;
	error = '';
	active = false;
	sessionId = '';
	placeContext = null;
	if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem('se_chat_session');
}

export const chatState = {
	get messages() { return messages; },
	get loading() { return loading; },
	get error() { return error; },
	get active() { return active; },
	get placeContext() { return placeContext; },
	set placeContext(p: PlaceContext | null) { placeContext = p; },
	send,
	start,
	reset
};
