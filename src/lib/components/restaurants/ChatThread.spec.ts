import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { render } from 'svelte/server';

vi.mock('$lib/firestore-stream', () => ({
	postAgentStream: vi.fn(),
	subscribeToSession: vi.fn()
}));

vi.mock('$lib/firebase', () => ({
	ensureAnonAuth: vi.fn(async () => 'uid-test'),
	getFirebase: vi.fn(async () => ({ db: {}, auth: {} })),
	getIdToken: vi.fn(async () => 'mock-id-token')
}));

import { chatState } from '$lib/chat-state.svelte';
import { postAgentStream, subscribeToSession } from '$lib/firestore-stream';
import ChatThread from './ChatThread.svelte';

const mockPost = postAgentStream as Mock;
const mockSubscribe = subscribeToSession as Mock;

type StreamCallbacks = Parameters<typeof subscribeToSession>[2];

function hangingStream() {
	let capturedCbs!: StreamCallbacks;

	mockPost.mockResolvedValue({ sessionId: 'server-sid', runId: 'run-1' });
	mockSubscribe.mockImplementation(
		async (_sid: string, _runId: string, callbacks: StreamCallbacks) => {
			capturedCbs = callbacks;
			return () => {};
		}
	);

	return {
		get cbs() {
			return capturedCbs;
		}
	};
}

function resetAll() {
	chatState.reset();
	for (const conv of [...chatState.conversations]) {
		chatState.deleteConversation(conv.id);
	}
	chatState.pageHidden = false;
}

async function waitUntil(fn: () => boolean, timeout = 2000) {
	const start = Date.now();
	while (!fn()) {
		if (Date.now() - start > timeout) throw new Error('waitUntil timed out');
		await new Promise((r) => setTimeout(r, 10));
	}
}

describe('ChatThread', () => {
	beforeEach(() => {
		mockPost.mockReset();
		mockSubscribe.mockReset();
		resetAll();
	});

	it('does not render a duplicate final counts row in the completed summary', async () => {
		const stream = hangingStream();
		chatState.start('review summary', null);
		await waitUntil(() => !!stream.cbs);

		stream.cbs.onComplete('Agent reply', [], undefined, {
			startedAtMs: 0,
			finishedAtMs: 10_000,
			elapsedMs: 10_000,
			notes: [
				{
					text: 'I checked the strongest signals.',
					noteSource: 'deterministic',
					counts: { webQueries: 0, sources: 1, venues: 0, platforms: 0 }
				}
			],
			finalCounts: { webQueries: 0, sources: 1, venues: 0, platforms: 0 }
		});
		await waitUntil(() => !chatState.loading);

		const { body } = render(ChatThread, { props: {} });
		expect(body.match(/Opened 1 source/g)).toHaveLength(1);
	});
});
