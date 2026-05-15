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
import type { ChatSource } from '$lib/chat-types';

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
		},
		events(sid: string) {
			return captured.find((c) => c.ref._ref?._path === `sessions/${sid}/events`);
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

function eventsSnap(events: Record<string, unknown>[]) {
	return {
		metadata: { fromCache: false },
		docChanges: () =>
			events.map((data, index) => ({
				type: 'added' as const,
				doc: { data: () => ({ attempt: 1, seqInAttempt: index + 1, type: 'timeline', data }) }
			}))
	};
}

async function waitUntil(fn: () => boolean, timeout = 2000) {
	const start = Date.now();
	while (!fn()) {
		if (Date.now() - start > timeout) throw new Error('waitUntil timed out');
		await new Promise((r) => setTimeout(r, 5));
	}
}

function expectInOrder(body: string, values: string[]) {
	let cursor = -1;
	for (const value of values) {
		const next = body.indexOf(value);
		expect(next, value).toBeGreaterThan(cursor);
		cursor = next;
	}
}

async function primeCompleteTurn({
	sid = 'sid-1',
	sourceCount = 0,
	sources,
	turnSummary = null
}: {
	sid?: string;
	sourceCount?: number;
	sources?: ChatSource[];
	turnSummary?: { startedAtMs: number; finishedAtMs: number; elapsedMs: number } | null;
} = {}) {
	const obs = captureObservers();
	chatState.selectSession(sid);
	await waitUntil(() => !!obs.turns(sid));

	const turn: Record<string, unknown> = {
		turnIndex: 1,
		runId: 'run-1',
		userMessage: 'review summary',
		status: 'complete',
		reply: 'Agent reply',
		createdAt: { toMillis: () => 1000 },
		completedAt: { toMillis: () => 36_000 }
	};
	if (sources) {
		turn.sources = sources;
	} else if (sourceCount > 0) {
		turn.sources = Array.from({ length: sourceCount }, (_, i) => ({
			title: `Source ${i + 1}`,
			url: `https://example.com/${i + 1}`
		}));
	}
	if (turnSummary) turn.turnSummary = turnSummary;

	obs.session(sid)!.onNext(
		sessionSnap({
			userId: 'uid-test',
			participants: ['uid-test'],
			status: 'complete',
			currentRunId: 'run-1',
			lastTurnIndex: 1
		})
	);
	obs.turns(sid)!.onNext(turnsSnap([{ data: turn }]));
	return { obs, sid };
}

async function addEvents(
	obs: ReturnType<typeof captureObservers>,
	sid: string,
	events: Record<string, unknown>[]
) {
	await waitUntil(() => !!obs.events(sid));
	obs.events(sid)!.onNext(eventsSnap(events));
}

describe('ChatThread', () => {
	beforeEach(() => {
		mockOnSnapshot.mockReset();
		_testing.reset();
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('hides low-count source and activity metadata', async () => {
		const { obs, sid } = await primeCompleteTurn({
			sourceCount: 1,
			turnSummary: { startedAtMs: 0, finishedAtMs: 35_000, elapsedMs: 35_000 }
		});
		await addEvents(obs, sid, [
			{ kind: 'thought', id: 'n1', author: 'research_lead', text: 'Reading sources' }
		]);

		expect(chatState.messages).toHaveLength(2);
		const { body } = render(ChatThread, { props: {} });
		expect(body).toContain('Agent reply');
		expect(body).not.toContain('Activity unavailable');
		expect(body).not.toContain('Analysis activity');
		expect(body).not.toContain('35s total');
		expect(body).not.toContain('Opened 1 source');
		expect(body).not.toContain('Sources');
		expect(body).not.toContain('Sources (1)');
	});

	it('shows source and activity metadata once thresholds are met', async () => {
		const { obs, sid } = await primeCompleteTurn({
			sourceCount: 5,
			turnSummary: { startedAtMs: 1000, finishedAtMs: 2000, elapsedMs: 1000 }
		});
		await addEvents(obs, sid, [
			{ kind: 'thought', id: 'n1', author: 'research_lead', text: 'Reading sources' },
			{ kind: 'thought', id: 'n2', author: 'report_writer', text: 'Checking evidence' },
			{
				kind: 'detail',
				id: 'd1',
				group: 'source',
				family: 'Public sources',
				text: 'Opened source'
			}
		]);

		const { body } = render(ChatThread, { props: {} });
		expect(body).toContain('Sources (5)');
		expect(body).toContain('Analysis activity');
		expect(body).toContain('1s total');
	});

	it('orders collapsed sources to show portal variety first', async () => {
		const sources: ChatSource[] = [
			{ title: 'Portal first', url: 'https://portal.example/first' },
			{ title: 'Portal second', url: 'https://portal.example/second' },
			...Array.from({ length: 18 }, (_, i) => ({
				title: `Source ${i + 1}`,
				url: `https://domain${i + 1}.example/article`
			}))
		];
		await primeCompleteTurn({ sources });

		const { body } = render(ChatThread, { props: {} });
		expect(body).toContain('Sources (20)');
		expect(body).toContain('https://portal.example/first');
		expect(body).toContain('https://domain18.example/article');
		expect(body).not.toContain('https://portal.example/second');
		expect(body).toContain('+1 more');
	});

	it('stable-shuffles repeated source families after the first variety pass', async () => {
		const sources: ChatSource[] = [
			{ title: 'A1', url: 'https://a.example/1' },
			{ title: 'A2', url: 'https://a.example/2' },
			{ title: 'A3', url: 'https://a.example/3' },
			{ title: 'B1', url: 'https://b.example/1' },
			{ title: 'B2', url: 'https://b.example/2' },
			{ title: 'B3', url: 'https://b.example/3' },
			{ title: 'C1', url: 'https://c.example/1' },
			{ title: 'C2', url: 'https://c.example/2' },
			{ title: 'C3', url: 'https://c.example/3' }
		];
		await primeCompleteTurn({ sources });

		const { body } = render(ChatThread, { props: {} });
		expectInOrder(body, [
			'https://a.example/1',
			'https://b.example/1',
			'https://c.example/1',
			'https://b.example/2',
			'https://c.example/2',
			'https://b.example/3',
			'https://c.example/3',
			'https://a.example/2',
			'https://a.example/3'
		]);
	});

	it('labels fetched page sources by domain', async () => {
		const sources: ChatSource[] = [
			{
				title: 'Fetched article',
				url: 'https://news.example/story',
				domain: 'news.example',
				provider: 'fetched_page'
			},
			{ title: 'A', url: 'https://a.example/story' },
			{ title: 'B', url: 'https://b.example/story' },
			{ title: 'C', url: 'https://c.example/story' },
			{ title: 'D', url: 'https://d.example/story' }
		];
		await primeCompleteTurn({ sources });

		const { body } = render(ChatThread, { props: {} });
		expect(body).toMatch(/>\s*news\.example\s*<\/span>/);
	});

	it('renders user-facing copy for terminal backend error codes', async () => {
		const obs = captureObservers();
		chatState.selectSession('sid-1');
		await waitUntil(() => !!obs.turns('sid-1'));

		obs.turns('sid-1')!.onNext(
			turnsSnap([
				{
					data: {
						turnIndex: 1,
						runId: 'run-1',
						userMessage: 'follow up',
						status: 'error',
						error: 'progress_stalled',
						createdAt: { toMillis: () => 1000 }
					}
				}
			])
		);

		const { body } = render(ChatThread, { props: {} });
		expect(body).toContain('The analysis stalled before a final answer was delivered.');
		expect(body).not.toContain('progress_stalled');
	});
});
