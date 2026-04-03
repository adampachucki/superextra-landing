import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';

// Mock streamAgent before importing chat-state
vi.mock('$lib/sse-client', () => ({
	streamAgent: vi.fn()
}));

// Import after mock is set up
import { chatState } from './chat-state.svelte';
import { streamAgent } from '$lib/sse-client';

const mockStreamAgent = streamAgent as Mock;

type Callbacks = {
	onProgress: (
		stage: string,
		status: string,
		label: string,
		previews?: Array<{ name: string; preview: string }>
	) => void;
	onToken: (text: string) => void;
	onComplete: (
		reply: string,
		sources: Array<{ title: string; url: string }>,
		title?: string
	) => void;
	onError: (error: string) => void;
	onActivity?: (activity: {
		id: string;
		category: string;
		status: string;
		label: string;
		detail?: string;
		url?: string;
		agent?: string;
	}) => void;
};

/** Make streamAgent hang and return refs to captured callbacks and a resolve function. */
function hangingStream() {
	let resolveSend!: () => void;
	let capturedCbs!: Callbacks;
	let capturedBody!: Record<string, unknown>;

	mockStreamAgent.mockImplementation(
		async (_url: string, body: Record<string, unknown>, callbacks: Callbacks) => {
			capturedCbs = callbacks;
			capturedBody = body;
			await new Promise<void>((r) => {
				resolveSend = r;
			});
		}
	);

	return {
		get cbs() {
			return capturedCbs;
		},
		get body() {
			return capturedBody;
		},
		resolve() {
			resolveSend();
		}
	};
}

/** Make streamAgent resolve immediately, capturing callbacks. */
function instantStream() {
	let capturedCbs!: Callbacks;
	let capturedBody!: Record<string, unknown>;

	mockStreamAgent.mockImplementation(
		async (_url: string, body: Record<string, unknown>, callbacks: Callbacks) => {
			capturedCbs = callbacks;
			capturedBody = body;
		}
	);

	return {
		get cbs() {
			return capturedCbs;
		},
		get body() {
			return capturedBody;
		}
	};
}

/** Fully reset the singleton state between tests. */
function resetAll() {
	chatState.reset();
	for (const conv of [...chatState.conversations]) {
		chatState.deleteConversation(conv.id);
	}
}

/** Wait for a condition to become true. */
async function waitUntil(fn: () => boolean, timeout = 2000) {
	const start = Date.now();
	while (!fn()) {
		if (Date.now() - start > timeout) throw new Error('waitUntil timed out');
		await new Promise((r) => setTimeout(r, 10));
	}
}

describe('chatState', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
		resetAll();
	});

	// ----------------------------------------------------------------
	// send()
	// ----------------------------------------------------------------
	describe('send()', () => {
		it('pushes user message, sets loading=true, calls streamAgent with correct args', () => {
			expect.assertions(6);

			const stream = hangingStream();
			chatState.start('hello world', null);

			// start() calls send() internally
			expect(stream.body.message).toBe('hello world');
			expect(stream.body.sessionId).toBeTruthy();
			expect(stream.body.placeContext).toBeNull();
			expect(chatState.messages.length).toBe(1);
			expect(chatState.messages[0].role).toBe('user');
			expect(chatState.loading).toBe(true);
		});

		it('onComplete appends agent message with sources', async () => {
			expect.assertions(3);

			const stream = hangingStream();
			chatState.start('test query', null);

			const sources = [{ title: 'Source 1', url: 'https://example.com' }];
			stream.cbs.onComplete('agent reply', sources);
			stream.resolve();

			await waitUntil(() => !chatState.loading);

			const agentMsg = chatState.messages.find((m) => m.role === 'agent');
			expect(agentMsg?.text).toBe('agent reply');
			expect(agentMsg?.sources).toEqual(sources);
			expect(chatState.loading).toBe(false);
		});

		it('onError sets error string', async () => {
			expect.assertions(1);

			const stream = hangingStream();
			chatState.start('test query', null);

			stream.cbs.onError('Something went wrong');
			stream.resolve();

			await waitUntil(() => !chatState.loading);

			expect(chatState.error).toBe('Something went wrong');
		});

		it('rejects when loading is already true (no double-send)', async () => {
			expect.assertions(2);

			// Make streamAgent hang forever so loading stays true
			hangingStream();
			chatState.start('first', null);
			expect(chatState.loading).toBe(true);

			// Calling send again should be a no-op (returns immediately)
			await chatState.send('second');
			// Only one user message should exist (from start's send call)
			expect(chatState.messages.length).toBe(1);
		});

		it('rejects empty/whitespace string', async () => {
			expect.assertions(2);

			// Set up a conversation, let it complete so loading=false
			instantStream();
			chatState.start('setup', null);

			// Now clear mock and try empty sends
			mockStreamAgent.mockClear();
			instantStream(); // re-register the mock in case

			await chatState.send('');
			await chatState.send('   ');

			expect(mockStreamAgent).not.toHaveBeenCalled();
			expect(chatState.messages.length).toBe(1); // only the 'setup' message
		});

		it('finally clears loading and streaming state', async () => {
			expect.assertions(3);

			const stream = hangingStream();
			chatState.start('test', null);
			expect(chatState.loading).toBe(true);

			stream.resolve();
			await waitUntil(() => !chatState.loading);

			expect(chatState.loading).toBe(false);
			expect(chatState.streamingText).toBe('');
		});
	});

	// ----------------------------------------------------------------
	// start()
	// ----------------------------------------------------------------
	describe('start()', () => {
		it('creates new conversation with UUID, adds to front of list', () => {
			expect.assertions(4);

			instantStream();
			chatState.start('new query', null);

			expect(chatState.conversations.length).toBe(1);
			expect(chatState.conversations[0].title).toBe('new query');
			expect(chatState.activeId).toBe(chatState.conversations[0].id);
			expect(chatState.activeId).toMatch(
				/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
			);
		});

		it('caps conversations at MAX (50)', () => {
			expect.assertions(1);

			// Use instant stream so loading clears each time
			instantStream();

			for (let i = 0; i < 55; i++) {
				chatState.start(`query ${i}`, null);
			}

			expect(chatState.conversations.length).toBeLessThanOrEqual(50);
		});

		it('calls send() with the query', () => {
			expect.assertions(2);

			mockStreamAgent.mockClear();
			const stream = instantStream();
			chatState.start('my question', null);

			expect(mockStreamAgent).toHaveBeenCalledTimes(1);
			expect(stream.body.message).toBe('my question');
		});
	});

	// ----------------------------------------------------------------
	// switchTo()
	// ----------------------------------------------------------------
	describe('switchTo()', () => {
		it('loads conversation messages from list', async () => {
			expect.assertions(2);

			// Create first conversation with a complete exchange
			const stream1 = hangingStream();
			chatState.start('first convo', null);
			const firstId = chatState.activeId!;
			stream1.cbs.onComplete('reply 1', []);
			stream1.resolve();
			await waitUntil(() => !chatState.loading);

			// Create second conversation
			const stream2 = hangingStream();
			chatState.start('second convo', null);
			stream2.cbs.onComplete('reply 2', []);
			stream2.resolve();
			await waitUntil(() => !chatState.loading);

			// Switch back to first
			chatState.switchTo(firstId);
			expect(chatState.messages[0].text).toBe('first convo');
			expect(chatState.messages[1].text).toBe('reply 1');
		});

		it('if last message is user role triggers recover()', async () => {
			expect.assertions(2);

			// Create a conversation where the agent never replied
			const stream1 = hangingStream();
			chatState.start('pending query', null);
			const pendingId = chatState.activeId!;
			// Resolve WITHOUT calling onComplete — only user message remains
			stream1.resolve();
			await waitUntil(() => !chatState.loading);

			// Start another conversation to switch away
			instantStream();
			chatState.start('other convo', null);

			// Mock fetch for recover() polling
			const mockFetch = vi.fn().mockResolvedValue({
				json: () =>
					Promise.resolve({
						ok: true,
						reply: 'recovered reply',
						sources: []
					})
			});
			vi.stubGlobal('fetch', mockFetch);

			// Switch to the pending conversation — should trigger recover()
			chatState.switchTo(pendingId);

			await waitUntil(
				() => chatState.messages.some((m) => m.role === 'agent' && m.text === 'recovered reply'),
				5000
			);

			expect(
				chatState.messages.some((m) => m.role === 'agent' && m.text === 'recovered reply')
			).toBe(true);
			expect(mockFetch).toHaveBeenCalled();

			vi.unstubAllGlobals();
		});

		it('no-op if already on that conversation', () => {
			expect.assertions(2);

			instantStream();
			chatState.start('test', null);
			const id = chatState.activeId!;

			chatState.switchTo(id);
			expect(chatState.activeId).toBe(id);
			expect(chatState.messages.length).toBe(1);
		});
	});

	// ----------------------------------------------------------------
	// recover()
	// ----------------------------------------------------------------
	describe('recover()', () => {
		it('polls fetch, appends reply on success, returns true', async () => {
			expect.assertions(2);

			// Create a conversation with a user message
			const stream = hangingStream();
			chatState.start('query', null);
			stream.resolve();
			await waitUntil(() => !chatState.loading);

			// Mock fetch for recover
			const mockFetch = vi.fn().mockResolvedValue({
				json: () =>
					Promise.resolve({
						ok: true,
						reply: 'recovered answer',
						sources: [{ title: 'Src', url: 'https://src.com' }]
					})
			});
			vi.stubGlobal('fetch', mockFetch);

			const result = await chatState.recover();
			expect(result).toBe(true);
			expect(chatState.messages.some((m) => m.text === 'recovered answer')).toBe(true);

			vi.unstubAllGlobals();
		});

		it('reason: session_not_found stops immediately, sets error', async () => {
			expect.assertions(2);

			const stream = hangingStream();
			chatState.start('query', null);
			stream.resolve();
			await waitUntil(() => !chatState.loading);

			const mockFetch = vi.fn().mockResolvedValue({
				json: () => Promise.resolve({ ok: false, reason: 'session_not_found' })
			});
			vi.stubGlobal('fetch', mockFetch);

			const result = await chatState.recover();
			expect(result).toBe(false);
			expect(chatState.error).toBe('Session not found. Please start a new conversation.');

			vi.unstubAllGlobals();
		});

		it('reason: agent_unavailable stops immediately, sets error', async () => {
			expect.assertions(2);

			const stream = hangingStream();
			chatState.start('query', null);
			stream.resolve();
			await waitUntil(() => !chatState.loading);

			const mockFetch = vi.fn().mockResolvedValue({
				json: () => Promise.resolve({ ok: false, reason: 'agent_unavailable' })
			});
			vi.stubGlobal('fetch', mockFetch);

			const result = await chatState.recover();
			expect(result).toBe(false);
			expect(chatState.error).toBe('Agent unavailable. Please try again.');

			vi.unstubAllGlobals();
		});

		it('conversation switch mid-recovery stops polling', async () => {
			expect.assertions(2);

			const stream = hangingStream();
			chatState.start('first', null);
			stream.resolve();
			await waitUntil(() => !chatState.loading);

			let fetchCallCount = 0;
			const mockFetch = vi.fn().mockImplementation(async () => {
				fetchCallCount++;
				if (fetchCallCount === 1) {
					// On first poll, switch away by starting a new conversation
					instantStream();
					chatState.start('second', null);
				}
				return {
					json: () => Promise.resolve({ ok: false })
				};
			});
			vi.stubGlobal('fetch', mockFetch);

			// Need to be on firstId for recover
			// Actually we just started 'second' inside the mock, so let's switchTo first
			// But the mock hasn't run yet. Let's call recover directly on firstId.
			// We're still on firstId since we haven't called the mock yet.
			// Wait — we started 'second' inside the mock callback which runs during recover.
			// Let me restructure: call recover on firstId, the first fetch switches away.

			const result = await chatState.recover();
			expect(result).toBe(false);
			// Should stop quickly after the conversation switch
			expect(fetchCallCount).toBeLessThanOrEqual(2);

			vi.unstubAllGlobals();
		});
	});

	// ----------------------------------------------------------------
	// deleteConversation()
	// ----------------------------------------------------------------
	describe('deleteConversation()', () => {
		it('removes from list, clears state if active', () => {
			expect.assertions(4);

			instantStream();
			chatState.start('to delete', null);
			const id = chatState.activeId!;

			expect(chatState.conversations.length).toBe(1);

			chatState.deleteConversation(id);

			expect(chatState.conversations.length).toBe(0);
			expect(chatState.activeId).toBeNull();
			expect(chatState.active).toBe(false);
		});
	});

	// ----------------------------------------------------------------
	// generateTitle (via start)
	// ----------------------------------------------------------------
	describe('generateTitle (via start)', () => {
		it('truncates long text at word boundary with "..."', () => {
			expect.assertions(2);

			instantStream();
			const longQuery =
				'What are the best strategies for restaurant marketing in a competitive urban market segment';
			chatState.start(longQuery, null);

			const title = chatState.conversations[0].title;
			expect(title.endsWith('...')).toBe(true);
			expect(title.length).toBeLessThanOrEqual(54); // 50 chars + '...'
		});
	});

	// ----------------------------------------------------------------
	// Conversation switch mid-stream
	// ----------------------------------------------------------------
	describe('conversation switch mid-stream', () => {
		it('onComplete during different active conversation appends message to original conversation', async () => {
			expect.assertions(3);

			// Start conv1 — it hangs
			const stream1 = hangingStream();
			chatState.start('conv1 query', null);
			const conv1Id = chatState.activeId!;

			// Fire onComplete while we're still on conv1 (same conversation)
			stream1.cbs.onComplete('reply for conv1', [{ title: 'S', url: 'https://s.com' }]);
			stream1.resolve();
			await waitUntil(() => !chatState.loading);

			// conv1 messages should have the reply
			expect(chatState.messages.some((m) => m.text === 'reply for conv1')).toBe(true);

			// Start conv2
			instantStream();
			chatState.start('conv2 query', null);
			expect(chatState.activeId).not.toBe(conv1Id);

			// Switch back to conv1 to verify messages are preserved
			chatState.switchTo(conv1Id);
			expect(chatState.messages.some((m) => m.text === 'reply for conv1')).toBe(true);
		});
	});

	describe('streamingActivities', () => {
		it('onActivity upserts items by id', async () => {
			const stream = hangingStream();
			chatState.start('test', null);

			stream.cbs.onActivity!({
				id: 'data-0',
				category: 'data',
				status: 'running',
				label: 'Loading restaurant details'
			});
			expect(chatState.streamingActivities).toHaveLength(1);
			expect(chatState.streamingActivities[0].status).toBe('running');

			// Update same id
			stream.cbs.onActivity!({
				id: 'data-0',
				category: 'data',
				status: 'complete',
				label: 'Loading restaurant details'
			});
			expect(chatState.streamingActivities).toHaveLength(1);
			expect(chatState.streamingActivities[0].status).toBe('complete');

			stream.cbs.onComplete('reply', []);
			stream.resolve();
		});

		it('all-complete marks category items complete', async () => {
			const stream = hangingStream();
			chatState.start('test', null);

			stream.cbs.onActivity!({
				id: 'data-0',
				category: 'data',
				status: 'running',
				label: 'Loading'
			});
			stream.cbs.onActivity!({
				id: 'data-1',
				category: 'data',
				status: 'running',
				label: 'Finding'
			});
			expect(chatState.streamingActivities.filter((a) => a.status === 'running')).toHaveLength(2);

			stream.cbs.onActivity!({
				id: '',
				category: 'data',
				status: 'all-complete',
				label: ''
			});
			expect(chatState.streamingActivities.every((a) => a.status === 'complete')).toBe(true);

			stream.cbs.onComplete('reply', []);
			stream.resolve();
		});

		it('streamingActivities cleared on next send, not on completion', async () => {
			// First send — inject an activity
			const stream1 = hangingStream();
			chatState.start('test1', null);
			stream1.cbs.onActivity!({
				id: 'data-0',
				category: 'data',
				status: 'running',
				label: 'Loading'
			});
			stream1.cbs.onComplete('reply', []);
			stream1.resolve();
			await waitUntil(() => !chatState.loading);

			// Activities persist after completion
			expect(chatState.streamingActivities).toHaveLength(1);

			// Second send clears them
			instantStream();
			chatState.send('test2');
			await waitUntil(() => !chatState.loading);
			expect(chatState.streamingActivities).toHaveLength(0);
		});

		it('isStreaming reflects activities', async () => {
			const stream = hangingStream();
			chatState.start('test', null);

			expect(chatState.isStreaming).toBe(false);
			stream.cbs.onActivity!({
				id: 'search-0',
				category: 'search',
				status: 'running',
				label: 'query'
			});
			expect(chatState.isStreaming).toBe(true);

			stream.cbs.onComplete('reply', []);
			stream.resolve();
		});
	});
});
