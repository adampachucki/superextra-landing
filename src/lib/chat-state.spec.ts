import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';

// Mock the Firestore stream + Firebase singletons before importing chat-state.

vi.mock('$lib/firestore-stream', () => ({
	postAgentStream: vi.fn(),
	subscribeToSession: vi.fn()
}));

vi.mock('$lib/firebase', () => ({
	ensureAnonAuth: vi.fn(async () => 'uid-test'),
	getFirebase: vi.fn(async () => ({ db: {}, auth: {} })),
	getIdToken: vi.fn(async () => 'mock-id-token')
}));

import { chatState } from './chat-state.svelte';
import { postAgentStream, subscribeToSession } from '$lib/firestore-stream';

const mockPost = postAgentStream as Mock;
const mockSubscribe = subscribeToSession as Mock;

type StreamCallbacks = Parameters<typeof subscribeToSession>[2];

/** Wire the mocks so subscribeToSession hangs until the test fires callbacks,
 *  and postAgentStream resolves immediately with a fresh runId. */
function hangingStream() {
	let capturedCbs!: StreamCallbacks;
	let unsubscribeCalled = false;
	const runId = `run-${Math.random().toString(36).slice(2, 10)}`;

	mockPost.mockResolvedValue({ sessionId: 'server-sid', runId });
	mockSubscribe.mockImplementation(
		async (_sid: string, _runId: string, callbacks: StreamCallbacks) => {
			capturedCbs = callbacks;
			return () => {
				unsubscribeCalled = true;
			};
		}
	);

	return {
		get cbs() {
			return capturedCbs;
		},
		get runId() {
			return runId;
		},
		get unsubscribed() {
			return unsubscribeCalled;
		}
	};
}

/** Reset the singleton conversation store between tests. */
function resetAll() {
	chatState.reset();
	for (const conv of [...chatState.conversations]) {
		chatState.deleteConversation(conv.id);
	}
}

async function waitUntil(fn: () => boolean, timeout = 2000) {
	const start = Date.now();
	while (!fn()) {
		if (Date.now() - start > timeout) throw new Error('waitUntil timed out');
		await new Promise((r) => setTimeout(r, 10));
	}
}

describe('chatState (Firestore transport)', () => {
	beforeEach(() => {
		mockPost.mockReset();
		mockSubscribe.mockReset();
		resetAll();
	});

	describe('send()', () => {
		it('pushes user message, POSTs agentStream, subscribes with runId', async () => {
			const stream = hangingStream();
			chatState.start('hello world', null);

			// Wait for async POST + subscribe to settle.
			await waitUntil(() => !!stream.cbs);

			expect(mockPost).toHaveBeenCalledTimes(1);
			const [url, body, idToken] = mockPost.mock.calls[0];
			expect(typeof url).toBe('string');
			expect(body.message).toBe('hello world');
			expect(body.sessionId).toBeTruthy();
			expect(body.isFirstMessage).toBe(true);
			expect(idToken).toBe('mock-id-token');

			expect(mockSubscribe).toHaveBeenCalledTimes(1);
			const [subSid, subRun] = mockSubscribe.mock.calls[0];
			expect(subSid).toBeTruthy();
			expect(subRun).toBe(stream.runId);

			expect(chatState.messages.length).toBe(1);
			expect(chatState.messages[0].role).toBe('user');
			expect(chatState.loading).toBe(true);
		});

		it('onComplete appends agent message with sources and stops loading', async () => {
			const stream = hangingStream();
			chatState.start('test query', null);
			await waitUntil(() => !!stream.cbs);

			const sources = [{ title: 'Source 1', url: 'https://example.com' }];
			stream.cbs.onComplete('agent reply', sources);

			await waitUntil(() => !chatState.loading);
			const agentMsg = chatState.messages.find((m) => m.role === 'agent');
			expect(agentMsg?.text).toBe('agent reply');
			expect(agentMsg?.sources).toEqual(sources);
			expect(chatState.loading).toBe(false);
			expect(stream.unsubscribed).toBe(true);
		});

		it('dedupes when onComplete fires twice for the same runId', async () => {
			const stream = hangingStream();
			chatState.start('dedupe check', null);
			await waitUntil(() => !!stream.cbs);

			// Two onComplete calls within the same subscription carry the same
			// runId (closure-captured at buildStreamCallbacks time); the second
			// must be a no-op even if Firestore redelivers the terminal doc.
			stream.cbs.onComplete('once', [], undefined);
			stream.cbs.onComplete('once', [], undefined);
			await waitUntil(() => !chatState.loading);

			const agentReplies = () =>
				chatState.messages.filter((m) => m.role === 'agent' && m.text === 'once').length;
			expect(agentReplies()).toBe(1);
		});

		it('appends legitimately-new short reply on a fresh runId (no false dedup)', async () => {
			// Turn 1 — a short reply like "OK".
			const stream1 = hangingStream();
			chatState.start('turn one', null);
			await waitUntil(() => !!stream1.cbs);
			stream1.cbs.onComplete('OK', [], undefined);
			await waitUntil(() => !chatState.loading);

			// Turn 2 — same reply text, different runId. Must append again.
			const stream2 = hangingStream();
			await chatState.send('turn two');
			await waitUntil(() => !!stream2.cbs);
			stream2.cbs.onComplete('OK', [], undefined);
			await waitUntil(() => !chatState.loading);

			const okReplies = chatState.messages.filter(
				(m) => m.role === 'agent' && m.text === 'OK'
			).length;
			expect(okReplies).toBe(2);
		});

		it('onComplete syncs the server-generated title onto the conversation', async () => {
			// P3a — the Firestore observer path already carried title through,
			// but a regression here would silently drop the auto-generated title
			// in favour of the user's client-side placeholder (the first 50 chars
			// of their prompt). This test anchors the contract.
			const stream = hangingStream();
			chatState.start('generic question about pasta', null);
			await waitUntil(() => !!stream.cbs);

			stream.cbs.onComplete('agent reply', [], 'Weeknight Italian pricing');
			await waitUntil(() => !chatState.loading);

			expect(chatState.conversations[0].title).toBe('Weeknight Italian pricing');
		});

		it('onComplete without a title leaves the existing conversation title alone', async () => {
			const stream = hangingStream();
			chatState.start('my question', null);
			await waitUntil(() => !!stream.cbs);
			const initialTitle = chatState.conversations[0].title;

			stream.cbs.onComplete('agent reply', [], undefined);
			await waitUntil(() => !chatState.loading);

			expect(chatState.conversations[0].title).toBe(initialTitle);
		});

		it('onPermissionDenied + onFirstSnapshotTimeout double-fire starts recovery only once', async () => {
			// P3b — both fallback triggers share the same recover() path. The
			// StreamCallbacks.onPermissionDenied JSDoc promises "Emitted once"
			// (enforced at the firestore-stream layer), but as belt-and-braces
			// against future regressions a closure-level guard in chat-state
			// also ensures we never start two concurrent agentCheck polls for
			// the same run.
			const fetchMock = vi.fn(async () => ({
				json: async () => ({ ok: true, status: 'running', reply: null })
			}));
			vi.stubGlobal('fetch', fetchMock);

			const stream = hangingStream();
			chatState.start('double fire', null);
			await waitUntil(() => !!stream.cbs);

			// Simulate a stream layer that DID double-fire (defence-in-depth
			// test) plus an independent firstSnapshotTimeout:
			stream.cbs.onPermissionDenied!();
			stream.cbs.onPermissionDenied!();
			stream.cbs.onFirstSnapshotTimeout!();

			await new Promise((r) => setTimeout(r, 10));
			// recover() makes exactly one fetch for this runId (it may poll
			// again later if the first response is non-terminal, but the first
			// call count should be 1, not 3).
			expect(fetchMock).toHaveBeenCalledTimes(1);

			vi.unstubAllGlobals();
		});

		it('onError sets error and stops loading', async () => {
			const stream = hangingStream();
			chatState.start('test query', null);
			await waitUntil(() => !!stream.cbs);

			stream.cbs.onError('pipeline_error');
			await waitUntil(() => !chatState.loading);
			expect(chatState.error).toBe('pipeline_error');
		});

		it('onAttemptChange clears streaming state and seeds a Retrying cue', async () => {
			const stream = hangingStream();
			chatState.start('will retry', null);
			await waitUntil(() => !!stream.cbs);

			stream.cbs.onActivity!({
				id: 'a1',
				category: 'data',
				status: 'running',
				label: 'Loading'
			});
			expect(chatState.streamingActivities.length).toBe(1);

			stream.cbs.onAttemptChange!(2);
			expect(chatState.streamingActivities.length).toBe(0);
			// Retrying cue surfaces through streamingProgress so the existing
			// StreamingProgress component renders it without new UI wiring.
			expect(chatState.streamingProgress).toEqual([
				{ stage: 'retrying', status: 'running', label: 'Retrying…' }
			]);
		});

		it('maps 409 response to previous_turn_in_flight error', async () => {
			mockPost.mockRejectedValueOnce(
				Object.assign(new Error('previous_turn_in_flight'), { status: 409 })
			);
			chatState.start('collision', null);
			await waitUntil(() => !chatState.loading);
			expect(chatState.error).toBe('previous_turn_in_flight');
		});

		it('maps 403 response to ownership_mismatch error', async () => {
			mockPost.mockRejectedValueOnce(
				Object.assign(new Error('ownership_mismatch'), { status: 403 })
			);
			chatState.start('wrong-owner', null);
			await waitUntil(() => !chatState.loading);
			expect(chatState.error).toBe('ownership_mismatch');
		});

		it('rejects empty message and skips POST', async () => {
			mockPost.mockResolvedValue({ sessionId: 'x', runId: 'r' });
			mockSubscribe.mockResolvedValue(() => {});
			chatState.start('setup', null);
			await waitUntil(() => !chatState.loading || chatState.messages.length > 0);
			// Give subscribe time to settle
			await new Promise((r) => setTimeout(r, 10));

			mockPost.mockClear();
			await chatState.send('');
			await chatState.send('   ');
			expect(mockPost).not.toHaveBeenCalled();
		});

		it('rejects second send while loading', async () => {
			const stream = hangingStream();
			chatState.start('first', null);
			await waitUntil(() => !!stream.cbs);

			expect(chatState.loading).toBe(true);
			mockPost.mockClear();
			await chatState.send('second');
			expect(mockPost).not.toHaveBeenCalled();
		});
	});

	describe('start()', () => {
		it('creates a conversation with UUID and adds it to the front of the list', async () => {
			hangingStream();
			chatState.start('my question', null);

			expect(chatState.conversations.length).toBe(1);
			expect(chatState.conversations[0].title).toBe('my question');
			expect(chatState.activeId).toMatch(
				/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
			);
		});
	});

	describe('streamingActivities', () => {
		it('upserts activity items by id', async () => {
			const stream = hangingStream();
			chatState.start('test', null);
			await waitUntil(() => !!stream.cbs);

			stream.cbs.onActivity!({
				id: 'data-0',
				category: 'data',
				status: 'running',
				label: 'Loading restaurant details'
			});
			expect(chatState.streamingActivities).toHaveLength(1);
			expect(chatState.streamingActivities[0].status).toBe('running');

			stream.cbs.onActivity!({
				id: 'data-0',
				category: 'data',
				status: 'complete',
				label: 'Loading restaurant details'
			});
			expect(chatState.streamingActivities).toHaveLength(1);
			expect(chatState.streamingActivities[0].status).toBe('complete');
		});

		it('all-complete marks every item in category as complete', async () => {
			const stream = hangingStream();
			chatState.start('test', null);
			await waitUntil(() => !!stream.cbs);

			stream.cbs.onActivity!({ id: 'd1', category: 'data', status: 'running', label: 'A' });
			stream.cbs.onActivity!({ id: 'd2', category: 'data', status: 'running', label: 'B' });
			stream.cbs.onActivity!({ id: '', category: 'data', status: 'all-complete', label: '' });
			expect(chatState.streamingActivities.every((a) => a.status === 'complete')).toBe(true);
		});

		it('next send clears streamingActivities from previous turn', async () => {
			const stream1 = hangingStream();
			chatState.start('first', null);
			await waitUntil(() => !!stream1.cbs);
			stream1.cbs.onActivity!({
				id: 'data-0',
				category: 'data',
				status: 'running',
				label: 'Loading'
			});
			stream1.cbs.onComplete('reply', [], undefined);
			await waitUntil(() => !chatState.loading);
			expect(chatState.streamingActivities).toHaveLength(1);

			const stream2 = hangingStream();
			chatState.send('follow-up');
			await waitUntil(() => !!stream2.cbs);
			expect(chatState.streamingActivities).toHaveLength(0);
		});
	});

	describe('deleteConversation()', () => {
		it('removes from list and clears state if active', async () => {
			hangingStream();
			chatState.start('to delete', null);
			const id = chatState.activeId!;
			expect(chatState.conversations.length).toBe(1);
			chatState.deleteConversation(id);
			expect(chatState.conversations.length).toBe(0);
			expect(chatState.activeId).toBeNull();
			expect(chatState.active).toBe(false);
		});
	});

	describe('generateTitle (via start)', () => {
		it('truncates long text at a word boundary with "..."', async () => {
			hangingStream();
			const longQuery =
				'What are the best strategies for restaurant marketing in a competitive urban market segment';
			chatState.start(longQuery, null);
			const title = chatState.conversations[0].title;
			expect(title.endsWith('...')).toBe(true);
			expect(title.length).toBeLessThanOrEqual(54);
		});
	});
});
