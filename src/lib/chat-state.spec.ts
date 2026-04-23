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

vi.mock('firebase/firestore', () => ({
	doc: vi.fn((_db, _collection, id) => ({ _id: id })),
	getDoc: vi.fn()
}));

import { chatState } from './chat-state.svelte';
import { postAgentStream, subscribeToSession } from '$lib/firestore-stream';
import { getDoc } from 'firebase/firestore';

const mockPost = postAgentStream as Mock;
const mockSubscribe = subscribeToSession as Mock;
const mockGetDoc = getDoc as unknown as Mock;

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

function docSnap(data: Record<string, unknown> | null) {
	return {
		exists: () => data !== null,
		data: () => data ?? {}
	};
}

describe('chatState (Firestore transport)', () => {
	beforeEach(() => {
		mockPost.mockReset();
		mockSubscribe.mockReset();
		mockGetDoc.mockReset();
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

		it('onComplete marks the live reply for typing after drafting starts', async () => {
			const stream = hangingStream();
			chatState.start('typed reply', null);
			await waitUntil(() => !!stream.cbs);

			stream.cbs.onTimelineEvent!({
				kind: 'drafting',
				id: 'd1',
				text: 'Drafting the answer…'
			});
			stream.cbs.onComplete('agent reply', []);

			await waitUntil(() => !chatState.loading);
			const agentMsg = chatState.messages.find((m) => m.role === 'agent');
			expect(agentMsg).toBeTruthy();
			expect(chatState.typingMessageTimestamp).toBe(agentMsg?.timestamp);
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

			stream.cbs.onTimelineEvent!({
				kind: 'detail',
				id: 'a1',
				group: 'platform',
				family: 'Google Maps',
				text: 'Loading'
			});
			expect(chatState.liveTimeline.length).toBe(1);

			stream.cbs.onAttemptChange!(2);
			expect(chatState.liveTimeline).toHaveLength(1);
			expect(chatState.liveTimeline[0]).toMatchObject({
				kind: 'note',
				text: 'Retrying…'
			});
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

	describe('liveTimeline', () => {
		it('appends timeline rows and dedupes identical detail rows', async () => {
			const stream = hangingStream();
			chatState.start('test', null);
			await waitUntil(() => !!stream.cbs);

			stream.cbs.onTimelineEvent!({
				kind: 'detail',
				id: 'data-0',
				group: 'platform',
				family: 'Google Maps',
				text: 'Profile for Umami'
			});
			stream.cbs.onTimelineEvent!({
				kind: 'detail',
				id: 'data-1',
				group: 'platform',
				family: 'Google Maps',
				text: 'Profile for Umami'
			});
			expect(chatState.liveTimeline).toHaveLength(1);
		});

		it('keeps distinct note and drafting rows in order', async () => {
			const stream = hangingStream();
			chatState.start('test', null);
			await waitUntil(() => !!stream.cbs);

			stream.cbs.onTimelineEvent!({
				kind: 'note',
				id: 'n1',
				text: 'Checking the venue',
				noteSource: 'deterministic',
				counts: { webQueries: 0, sources: 0, venues: 1, platforms: 1 }
			});
			stream.cbs.onTimelineEvent!({
				kind: 'drafting',
				id: 'd1',
				text: 'Drafting the answer…'
			});
			expect(chatState.liveTimeline.map((event) => event.kind)).toEqual(['note', 'drafting']);
		});

		it('next send clears liveTimeline from previous turn', async () => {
			const stream1 = hangingStream();
			chatState.start('first', null);
			await waitUntil(() => !!stream1.cbs);
			stream1.cbs.onTimelineEvent!({
				kind: 'detail',
				id: 'data-0',
				group: 'platform',
				family: 'Google Maps',
				text: 'Loading'
			});
			stream1.cbs.onComplete('reply', [], undefined);
			await waitUntil(() => !chatState.loading);
			expect(chatState.liveTimeline).toHaveLength(0);

			const stream2 = hangingStream();
			chatState.send('follow-up');
			await waitUntil(() => !!stream2.cbs);
			expect(chatState.liveTimeline).toHaveLength(0);
		});
	});

	describe('resumeCurrentIfNeeded()', () => {
		it('returns false when there is no active conversation', async () => {
			await expect(chatState.resumeCurrentIfNeeded()).resolves.toBe(false);
			expect(mockGetDoc).not.toHaveBeenCalled();
		});

		it('returns false when the last message is not from the user', async () => {
			const stream = hangingStream();
			chatState.start('finished turn', null);
			await waitUntil(() => !!stream.cbs);
			stream.cbs.onComplete('agent reply', [], undefined);
			await waitUntil(() => !chatState.loading);

			await expect(chatState.resumeCurrentIfNeeded()).resolves.toBe(false);
			expect(mockGetDoc).not.toHaveBeenCalled();
		});

		it('reattaches through Firestore when the last message is from the user', async () => {
			mockPost.mockRejectedValueOnce(new Error('offline'));
			chatState.start('resume me', null);
			await waitUntil(() => !chatState.loading);

			mockGetDoc.mockResolvedValue(
				docSnap({
					status: 'running',
					currentRunId: 'resume-run',
					queuedAt: { toMillis: () => 123 }
				})
			);

			await expect(chatState.resumeCurrentIfNeeded()).resolves.toBe(true);
			expect(mockGetDoc).toHaveBeenCalledTimes(1);
			expect(mockSubscribe).toHaveBeenCalledTimes(1);
			expect(mockSubscribe.mock.calls[0][1]).toBe('resume-run');
		});

		it('tries Firestore resume before recover on visibility return when runId is missing', async () => {
			mockPost.mockRejectedValueOnce(new Error('offline'));
			chatState.start('resume on return', null);
			await waitUntil(() => !chatState.loading);

			mockGetDoc.mockResolvedValue(
				docSnap({
					status: 'running',
					currentRunId: 'resume-run',
					queuedAt: { toMillis: () => 456 }
				})
			);

			const fetchMock = vi.fn();
			vi.stubGlobal('fetch', fetchMock);
			vi.useFakeTimers();
			try {
				chatState.handleReturn(60_000);
				await vi.advanceTimersByTimeAsync(350);
				expect(mockGetDoc).toHaveBeenCalledTimes(1);
				expect(mockSubscribe).toHaveBeenCalledTimes(1);
				expect(fetchMock).not.toHaveBeenCalled();
			} finally {
				vi.useRealTimers();
				vi.unstubAllGlobals();
			}
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
