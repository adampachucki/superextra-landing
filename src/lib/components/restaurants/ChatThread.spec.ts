import { beforeEach, afterEach, describe, expect, it, vi, type Mock } from 'vitest';
import { render } from 'svelte/server';

// Mock firebase/firestore before importing chat-state so its dynamic
// `import('firebase/firestore')` resolves to our stubs.
vi.mock('firebase/firestore', () => ({
	doc: vi.fn((_db, ...parts: string[]) => ({ _kind: 'doc', _path: parts.join('/') })),
	collection: vi.fn((_db, ...parts: string[]) => ({
		_kind: 'collection',
		_path: parts.join('/')
	})),
	query: vi.fn((ref, ...constraints) => ({ _kind: 'query', _ref: ref, _constraints: constraints })),
	where: vi.fn((f, op, v) => ({ _kind: 'where', f, op, v })),
	orderBy: vi.fn((f) => ({ _kind: 'orderBy', f })),
	onSnapshot: vi.fn()
}));

vi.mock('$lib/firebase', () => ({
	ensureAnonAuth: vi.fn(async () => 'uid-test'),
	getFirebase: vi.fn(async () => ({ db: {}, auth: {} })),
	getIdToken: vi.fn(async () => 'mock-id-token')
}));

import { chatState, _testing } from '$lib/chat-state.svelte';
import { onSnapshot } from 'firebase/firestore';
import ChatThread from './ChatThread.svelte';

const mockOnSnapshot = onSnapshot as unknown as Mock;

type SnapHandler = (snap: unknown) => void;
type ErrHandler = (err: unknown) => void;

interface Captured {
	ref: { _path?: string; _ref?: { _path?: string }; _kind?: string };
	onNext: SnapHandler;
	onError: ErrHandler;
	unsubscribe: Mock;
}

function captureObservers() {
	const captured: Captured[] = [];
	mockOnSnapshot.mockImplementation((ref, onNext, onError) => {
		const unsubscribe = vi.fn();
		captured.push({ ref, onNext, onError, unsubscribe });
		return unsubscribe;
	});
	return {
		session(sid: string) {
			return captured.find((c) => c.ref._kind === 'doc' && c.ref._path === `sessions/${sid}`);
		},
		turns(sid: string) {
			return captured.find((c) => c.ref._ref?._path === `sessions/${sid}/turns`);
		}
	};
}

function sessionSnap(data: Record<string, unknown>, { fromCache = false } = {}) {
	return {
		exists: () => true,
		data: () => data,
		metadata: { fromCache }
	};
}

function turnsSnap(entries: Array<{ data: Record<string, unknown> }>, { fromCache = false } = {}) {
	return {
		metadata: { fromCache },
		forEach(cb: (docSnap: { id: string; data: () => Record<string, unknown> }) => void) {
			for (const e of entries) {
				const idx = (e.data.turnIndex as number | undefined) ?? 0;
				cb({ id: String(idx).padStart(4, '0'), data: () => e.data });
			}
		}
	};
}

async function waitUntil(fn: () => boolean, timeout = 2000) {
	const start = Date.now();
	while (!fn()) {
		if (Date.now() - start > timeout) throw new Error('waitUntil timed out');
		await new Promise((r) => setTimeout(r, 5));
	}
}

describe('ChatThread', () => {
	beforeEach(() => {
		mockOnSnapshot.mockReset();
		_testing.reset();
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('skips the completed activity shell when no captured events exist', async () => {
		const obs = captureObservers();
		chatState.selectSession('sid-1');
		await waitUntil(() => !!obs.turns('sid-1'));

		obs.session('sid-1')!.onNext(
			sessionSnap({
				userId: 'uid-test',
				participants: ['uid-test'],
				status: 'complete',
				currentRunId: 'run-1',
				lastTurnIndex: 1
			})
		);
		obs.turns('sid-1')!.onNext(
			turnsSnap([
				{
					data: {
						turnIndex: 1,
						runId: 'run-1',
						userMessage: 'review summary',
						status: 'complete',
						reply: 'Agent reply',
						sources: [{ title: 'Source A', url: 'https://example.com/a' }],
						turnSummary: {
							startedAtMs: 0,
							finishedAtMs: 35_000,
							elapsedMs: 35_000
						},
						createdAt: { toMillis: () => 1000 },
						completedAt: { toMillis: () => 36_000 }
					}
				}
			])
		);

		expect(chatState.messages).toHaveLength(2);
		const { body } = render(ChatThread, { props: {} });
		expect(body).toContain('Agent reply');
		expect(body).not.toContain('Activity unavailable');
		expect(body).not.toContain('Analysis activity');
		expect(body).not.toContain('35s total');
		expect(body).not.toContain('Opened 1 source');
	});
});
