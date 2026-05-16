import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';

// Mock firebase/firestore before importing chat-state so its dynamic
// `import('firebase/firestore')` resolves here. Each mock fn tags its result
// with `_path` so tests can partition observers by collection/doc path.
vi.mock('firebase/firestore', () => ({
	doc: vi.fn((_db, ...parts: string[]) => ({ _kind: 'doc', _path: parts.join('/') })),
	collection: vi.fn((_db, ...parts: string[]) => ({
		_kind: 'collection',
		_path: parts.join('/')
	})),
	query: vi.fn((ref, ...constraints) => ({ _kind: 'query', _ref: ref, _constraints: constraints })),
	where: vi.fn((f, op, v) => ({ _kind: 'where', f, op, v })),
	orderBy: vi.fn((f) => ({ _kind: 'orderBy', f })),
	onSnapshot: vi.fn(),
	getDoc: vi.fn(async () => ({ exists: () => false }))
}));

vi.mock('$lib/firebase', () => ({
	ensureAnonAuth: vi.fn(async () => 'uid-test'),
	getFirebase: vi.fn(async () => ({ db: {}, auth: {} })),
	getIdToken: vi.fn(async () => 'mock-id-token')
}));

import { chatState, _testing } from './chat-state.svelte';
import { onSnapshot } from 'firebase/firestore';

const mockOnSnapshot = onSnapshot as unknown as Mock;

type SnapHandler = (snap: unknown) => void;
type ErrHandler = (err: unknown) => void;

interface Captured {
	ref: { _path?: string; _ref?: { _path?: string }; _kind?: string };
	onNext: SnapHandler;
	onError: ErrHandler;
	unsubscribe: Mock;
}

/**
 * Capture every onSnapshot call. Tests partition observers by the synthetic
 * `_path` / `_ref._path` tag attached by the mock factory above.
 */
function captureObservers() {
	const captured: Captured[] = [];
	mockOnSnapshot.mockImplementation((ref, onNext, onError) => {
		const unsubscribe = vi.fn();
		captured.push({ ref, onNext, onError, unsubscribe });
		return unsubscribe;
	});
	return {
		all: captured,
		/** `sessions` collection-group listener (sidebar). Ref's `_ref._path`
		 *  is exactly `sessions`. */
		get sidebar() {
			return captured.find((c) => c.ref._ref?._path === 'sessions');
		},
		/** `sessions/{sid}` doc listener for the active session. */
		session(sid?: string) {
			return captured.find((c) => c.ref._kind === 'doc' && c.ref._path === `sessions/${sid ?? ''}`);
		},
		/** `sessions/{sid}/turns` ordered query (active turns listener). */
		turns(sid?: string) {
			return captured.find((c) => c.ref._ref?._path === `sessions/${sid ?? ''}/turns`);
		},
		/** `sessions/{sid}/events` filtered query (active events listener). */
		events(sid?: string) {
			return captured.find((c) => c.ref._ref?._path === `sessions/${sid ?? ''}/events`);
		}
	};
}

function sessionSnap(
	data: Record<string, unknown> | null,
	{ fromCache = false }: { fromCache?: boolean } = {}
) {
	return {
		exists() {
			return data !== null;
		},
		data() {
			return data ?? {};
		},
		metadata: { fromCache }
	};
}

/** Turns-collection snapshot. Each entry becomes a `docSnap` with an `id`
 *  derived from its `turnIndex` (matching the real zero-padded doc key). */
function turnsSnap(
	entries: Array<{ id?: string; data: Record<string, unknown> }>,
	{ fromCache = false }: { fromCache?: boolean } = {}
) {
	return {
		metadata: { fromCache },
		forEach(cb: (docSnap: { id: string; data: () => Record<string, unknown> }) => void) {
			for (const entry of entries) {
				cb({
					id: entry.id ?? String(entry.data.turnIndex ?? 0).padStart(4, '0'),
					data: () => entry.data
				});
			}
		}
	};
}

/** Sidebar-query snapshot; iteration order is the list order. */
function sidebarSnap(
	entries: Array<{ id: string; data: Record<string, unknown> }>,
	{ fromCache = false }: { fromCache?: boolean } = {}
) {
	return {
		metadata: { fromCache },
		forEach(cb: (docSnap: { id: string; data: () => Record<string, unknown> }) => void) {
			for (const entry of entries) {
				cb({ id: entry.id, data: () => entry.data });
			}
		}
	};
}

function eventChange(type: 'added' | 'modified' | 'removed', data: Record<string, unknown>) {
	return { type, doc: { data: () => data } };
}

function eventsSnap(
	changes: Array<ReturnType<typeof eventChange>>,
	{ fromCache = false }: { fromCache?: boolean } = {}
) {
	return {
		metadata: { fromCache },
		docChanges: () => changes
	};
}

async function flushAsync(times = 3) {
	for (let i = 0; i < times; i++) {
		await Promise.resolve();
	}
}

async function waitUntil(fn: () => boolean, timeout = 2000) {
	const start = Date.now();
	while (!fn()) {
		if (Date.now() - start > timeout) throw new Error('waitUntil timed out');
		await new Promise((r) => setTimeout(r, 5));
	}
}

describe('chatState (Firestore-driven)', () => {
	beforeEach(() => {
		mockOnSnapshot.mockReset();
		_testing.reset();
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	describe('sidebar listener', () => {
		it('subscribes to sessions where participants contains currentUid, ordered by updatedAt desc', async () => {
			const obs = captureObservers();
			// Touch sessionsList getter to trigger lazy attach.
			void chatState.sessionsList;
			await waitUntil(() => !!obs.sidebar);

			const sidebar = obs.sidebar!;
			// Ref is a `query(collection(db,'sessions'), where, orderBy)`.
			const constraints =
				(sidebar.ref._ref && undefined) ??
				(sidebar.ref as { _constraints?: Array<Record<string, unknown>> })._constraints;
			expect(Array.isArray(constraints)).toBe(true);
			const whereClauses = (constraints ?? []).filter(
				(c) => (c as { _kind?: string })._kind === 'where'
			);
			const orderBys = (constraints ?? []).filter(
				(c) => (c as { _kind?: string })._kind === 'orderBy'
			);
			expect(whereClauses).toHaveLength(1);
			expect(whereClauses[0]).toMatchObject({
				f: 'participants',
				op: 'array-contains',
				v: 'uid-test'
			});
			expect(orderBys).toHaveLength(1);
			expect(orderBys[0]).toMatchObject({ f: 'updatedAt' });
		});

		it('reflects snapshots into sessionsList in order', async () => {
			const obs = captureObservers();
			void chatState.sessionsList;
			await waitUntil(() => !!obs.sidebar);

			obs.sidebar!.onNext(
				sidebarSnap([
					{
						id: 'sid-a',
						data: {
							title: 'Alpha',
							userId: 'uid-test',
							lastTurnIndex: 1,
							status: 'complete',
							updatedAt: { toMillis: () => 2000 }
						}
					},
					{
						id: 'sid-b',
						data: {
							title: 'Beta',
							userId: 'uid-other',
							lastTurnIndex: 2,
							status: 'running',
							updatedAt: { toMillis: () => 1000 }
						}
					}
				])
			);

			expect(chatState.sessionsList.map((s) => s.sid)).toEqual(['sid-a', 'sid-b']);
			expect(chatState.sessionsList[0].title).toBe('Alpha');
			expect(chatState.sessionsList[0].updatedAtMs).toBe(2000);
		});

		it('updates on subsequent snapshot (new session added, one removed)', async () => {
			const obs = captureObservers();
			void chatState.sessionsList;
			await waitUntil(() => !!obs.sidebar);

			obs.sidebar!.onNext(
				sidebarSnap([
					{ id: 'sid-a', data: { title: 'A', userId: 'uid-test', lastTurnIndex: 1 } },
					{ id: 'sid-b', data: { title: 'B', userId: 'uid-test', lastTurnIndex: 1 } }
				])
			);
			expect(chatState.sessionsList.map((s) => s.sid)).toEqual(['sid-a', 'sid-b']);

			obs.sidebar!.onNext(
				sidebarSnap([
					{ id: 'sid-c', data: { title: 'C', userId: 'uid-test', lastTurnIndex: 1 } },
					{ id: 'sid-a', data: { title: 'A', userId: 'uid-test', lastTurnIndex: 1 } }
				])
			);
			expect(chatState.sessionsList.map((s) => s.sid)).toEqual(['sid-c', 'sid-a']);
		});
	});

	describe('active session listener', () => {
		it('subscribes to sessions/{sid} doc on selectSession()', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.session('sid-1'));
			expect(obs.session('sid-1')!.ref._path).toBe('sessions/sid-1');
		});

		it('activeSession reflects the doc snapshot', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.session('sid-1'));

			obs.session('sid-1')!.onNext(
				sessionSnap({
					userId: 'uid-test',
					participants: ['uid-test'],
					title: 'My Chat',
					placeContext: null,
					status: 'complete',
					currentRunId: 'run-1',
					activeAgent: 'report_writer',
					activeStage: 'writing_final_report',
					lastTurnIndex: 2,
					createdAt: { toMillis: () => 1000 },
					updatedAt: { toMillis: () => 2000 }
				})
			);
			expect(chatState.activeSession).toMatchObject({
				sid: 'sid-1',
				title: 'My Chat',
				userId: 'uid-test',
				lastTurnIndex: 2,
				activeAgent: 'report_writer',
				activeStage: 'writing_final_report',
				updatedAtMs: 2000
			});
		});

		it('derives the live status label from active session stage fields', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.session('sid-1'));

			obs.session('sid-1')!.onNext(
				sessionSnap({
					userId: 'uid-test',
					participants: ['uid-test'],
					status: 'running',
					currentRunId: 'run-1',
					activeAgent: 'context_enricher',
					activeStage: 'building_context',
					lastTurnIndex: 1
				})
			);

			expect(chatState.liveStatusLabel).toBe('Building context');
		});

		it('labels the evidence checking stage', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.session('sid-1'));

			obs.session('sid-1')!.onNext(
				sessionSnap({
					userId: 'uid-test',
					participants: ['uid-test'],
					status: 'running',
					currentRunId: 'run-1',
					activeAgent: 'evidence_adjudicator',
					activeStage: 'checking_evidence',
					lastTurnIndex: 1
				})
			);

			expect(chatState.liveStatusLabel).toBe('Checking evidence');
		});

		it('reselecting tears down the prior listener and starts a new one', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.session('sid-1'));
			const first = obs.session('sid-1')!;

			chatState.selectSession('sid-2');
			await waitUntil(() => !!obs.session('sid-2'));
			expect(first.unsubscribe).toHaveBeenCalled();
			expect(obs.session('sid-2')!.ref._path).toBe('sessions/sid-2');
		});

		it('canDelete is true when session.userId === currentUid, false otherwise', async () => {
			const obs = captureObservers();
			// Attach sidebar so currentUid populates.
			void chatState.sessionsList;
			await waitUntil(() => !!obs.sidebar);
			// Prime the sidebar so the listener actually resolves anon auth.
			obs.sidebar!.onNext(sidebarSnap([]));

			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.session('sid-1'));

			obs
				.session('sid-1')!
				.onNext(sessionSnap({ userId: 'uid-test', participants: ['uid-test'], lastTurnIndex: 1 }));
			expect(chatState.canDelete).toBe(true);

			chatState.selectSession('sid-2');
			await waitUntil(() => !!obs.session('sid-2'));
			obs.session('sid-2')!.onNext(
				sessionSnap({
					userId: 'uid-other',
					participants: ['uid-other', 'uid-test'],
					lastTurnIndex: 1
				})
			);
			expect(chatState.canDelete).toBe(false);
		});

		describe('loadState transitions', () => {
			it('starts as "loading" immediately after selectSession', () => {
				captureObservers();
				chatState.selectSession('sid-1');
				expect(chatState.loadState).toBe('loading');
			});

			it('cache-only first snap with exists=false does NOT flip to missing', async () => {
				const obs = captureObservers();
				chatState.selectSession('sid-1');
				await waitUntil(() => !!obs.session('sid-1'));

				obs.session('sid-1')!.onNext(sessionSnap(null, { fromCache: true }));
				expect(chatState.loadState).toBe('loading');
			});

			it('server-confirmed exists=true flips to "loaded"', async () => {
				const obs = captureObservers();
				chatState.selectSession('sid-1');
				await waitUntil(() => !!obs.session('sid-1'));

				obs
					.session('sid-1')!
					.onNext(
						sessionSnap(
							{ userId: 'uid-test', participants: ['uid-test'], lastTurnIndex: 0 },
							{ fromCache: false }
						)
					);
				expect(chatState.loadState).toBe('loaded');
			});

			it('server-confirmed exists=false flips to "missing"', async () => {
				const obs = captureObservers();
				chatState.selectSession('sid-1');
				await waitUntil(() => !!obs.session('sid-1'));

				obs.session('sid-1')!.onNext(sessionSnap(null, { fromCache: false }));
				expect(chatState.loadState).toBe('missing');
			});
		});
	});

	describe('active turns listener → messages', () => {
		it('subscribes to sessions/{sid}/turns ordered by turnIndex', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.turns('sid-1'));

			const turnsQ = obs.turns('sid-1')!;
			const constraints =
				(turnsQ.ref as { _constraints?: Array<Record<string, unknown>> })._constraints ?? [];
			const orderBys = constraints.filter((c) => (c as { _kind?: string })._kind === 'orderBy');
			expect(orderBys).toHaveLength(1);
			expect(orderBys[0]).toMatchObject({ f: 'turnIndex' });
		});

		it('flattens complete turns into user + agent messages', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.turns('sid-1'));

			obs.turns('sid-1')!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'hello',
							status: 'complete',
							reply: 'hi there',
							sources: [{ url: 'https://e.com', title: 'e' }],
							turnSummary: null,
							createdAt: { toMillis: () => 1000 },
							completedAt: { toMillis: () => 2000 }
						}
					}
				])
			);

			const msgs = chatState.messages;
			expect(msgs).toHaveLength(2);
			expect(msgs[0]).toMatchObject({
				role: 'user',
				text: 'hello',
				timestamp: 1000
			});
			expect(msgs[1]).toMatchObject({
				role: 'agent',
				text: 'hi there',
				timestamp: 2000
			});
			expect(msgs[1].sources).toEqual([{ url: 'https://e.com', title: 'e' }]);
		});

		it('does not animate turns that arrive already complete', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.turns('sid-1'));

			obs.turns('sid-1')!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'historical',
							status: 'complete',
							reply: 'already done',
							createdAt: { toMillis: () => 1000 },
							completedAt: { toMillis: () => 2000 }
						}
					}
				])
			);

			expect(chatState.messages[1]).toMatchObject({
				role: 'agent',
				text: 'already done',
				animateReveal: false
			});
		});

		it('animates replies when a live turn moves from running to complete', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.turns('sid-1'));

			obs.turns('sid-1')!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'live',
							status: 'running',
							reply: null,
							createdAt: { toMillis: () => 1000 }
						}
					}
				])
			);
			expect(chatState.messages).toHaveLength(1);

			obs.turns('sid-1')!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'live',
							status: 'complete',
							reply: 'fresh reply',
							createdAt: { toMillis: () => 1000 },
							completedAt: { toMillis: () => 2000 }
						}
					}
				])
			);

			const agent = chatState.messages[1];
			expect(agent).toMatchObject({
				role: 'agent',
				text: 'fresh reply',
				animateReveal: true
			});

			chatState.markReplyRevealed(agent.turnIndex);
			expect(chatState.messages[1].animateReveal).toBe(false);
		});

		it('does not animate when only a cache snapshot saw the turn running', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.turns('sid-1'));

			obs.turns('sid-1')!.onNext(
				turnsSnap(
					[
						{
							data: {
								turnIndex: 1,
								runId: 'run-1',
								userMessage: 'cached live',
								status: 'running',
								reply: null,
								createdAt: { toMillis: () => 1000 }
							}
						}
					],
					{ fromCache: true }
				)
			);

			obs.turns('sid-1')!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'cached live',
							status: 'complete',
							reply: 'already complete on server',
							createdAt: { toMillis: () => 1000 },
							completedAt: { toMillis: () => 2000 }
						}
					}
				])
			);

			expect(chatState.messages[1]).toMatchObject({
				role: 'agent',
				text: 'already complete on server',
				animateReveal: false
			});
		});

		it('skips incomplete agent messages — renders only the user message until the turn completes', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.turns('sid-1'));

			obs.turns('sid-1')!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'working?',
							status: 'running',
							reply: null,
							createdAt: { toMillis: () => 1000 }
						}
					}
				])
			);

			const msgs = chatState.messages;
			expect(msgs).toHaveLength(1);
			expect(msgs[0]).toMatchObject({ role: 'user', text: 'working?' });
		});

		it('error turns render only the user message (no agent row)', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.turns('sid-1'));

			obs.turns('sid-1')!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'oops',
							status: 'error',
							reply: null,
							error: 'pipeline_error',
							createdAt: { toMillis: () => 1000 }
						}
					}
				])
			);

			expect(chatState.messages).toHaveLength(1);
			expect(chatState.error).toBe('pipeline_error');
		});
	});

	describe('active events listener', () => {
		function primeRunningTurn(sid: string, obs: ReturnType<typeof captureObservers>) {
			obs.session(sid)!.onNext(
				sessionSnap({
					userId: 'uid-test',
					participants: ['uid-test'],
					status: 'running',
					currentRunId: 'run-1',
					lastTurnIndex: 1
				})
			);
			obs.turns(sid)!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'q',
							status: 'running',
							reply: null,
							createdAt: { toMillis: () => 1000 }
						}
					}
				])
			);
		}

		it('attaches only when the latest turn is queued/running/pending', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.turns('sid-1'));

			primeRunningTurn('sid-1', obs);
			await waitUntil(() => !!obs.events('sid-1'));
			expect(obs.events('sid-1')).toBeTruthy();
		});

		it('events query path is sessions/{sid}/events with a runId filter and (attempt, seqInAttempt) ordering', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.turns('sid-1'));

			primeRunningTurn('sid-1', obs);
			await waitUntil(() => !!obs.events('sid-1'));

			const ev = obs.events('sid-1')!;
			expect(ev.ref._ref?._path).toBe('sessions/sid-1/events');
			const constraints =
				(ev.ref as { _constraints?: Array<Record<string, unknown>> })._constraints ?? [];
			const wheres = constraints.filter((c) => (c as { _kind?: string })._kind === 'where');
			const orderBys = constraints.filter((c) => (c as { _kind?: string })._kind === 'orderBy');
			expect(wheres).toHaveLength(1);
			expect(wheres[0]).toMatchObject({ f: 'runId', v: 'run-1' });
			expect(orderBys.map((o) => (o as { f?: string }).f)).toEqual(['attempt', 'seqInAttempt']);
		});

		it('only processes "added" doc changes', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.turns('sid-1'));
			primeRunningTurn('sid-1', obs);
			await waitUntil(() => !!obs.events('sid-1'));

			obs.events('sid-1')!.onNext(
				eventsSnap([
					eventChange('added', {
						attempt: 1,
						seqInAttempt: 1,
						type: 'timeline',
						data: { kind: 'thought', id: 'n1', author: 'research_lead', text: 'Looking it up' }
					}),
					eventChange('modified', {
						attempt: 1,
						seqInAttempt: 2,
						type: 'timeline',
						data: { kind: 'thought', id: 'n2', author: 'research_lead', text: 'Should be skipped' }
					}),
					eventChange('removed', {
						attempt: 1,
						seqInAttempt: 3,
						type: 'timeline',
						data: { kind: 'thought', id: 'n3', author: 'research_lead', text: 'Also skipped' }
					})
				])
			);
			expect(chatState.liveTimeline).toHaveLength(1);
			expect(chatState.liveTimeline[0]).toMatchObject({ kind: 'thought', id: 'n1' });
		});

		it('keeps the live timeline on the completed agent message', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.turns('sid-1'));
			primeRunningTurn('sid-1', obs);
			await waitUntil(() => !!obs.events('sid-1'));

			obs.events('sid-1')!.onNext(
				eventsSnap([
					eventChange('added', {
						attempt: 1,
						seqInAttempt: 1,
						type: 'timeline',
						data: { kind: 'thought', id: 'n1', author: 'research_lead', text: 'Reading sources' }
					})
				])
			);

			obs.turns('sid-1')!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'q',
							status: 'complete',
							reply: 'a',
							turnSummary: { startedAtMs: 1000, finishedAtMs: 2000, elapsedMs: 1000 },
							createdAt: { toMillis: () => 1000 },
							completedAt: { toMillis: () => 2000 }
						}
					}
				])
			);

			expect(chatState.messages[1].activityEvents).toEqual([
				{ kind: 'thought', id: 'n1', author: 'research_lead', text: 'Reading sources' }
			]);
			expect(chatState.liveTimeline).toEqual([]);
		});

		it('hydrates completed activity events for a completed turn opened from history', async () => {
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
							userMessage: 'q',
							status: 'complete',
							reply: 'a',
							turnSummary: { startedAtMs: 1000, finishedAtMs: 2000, elapsedMs: 1000 },
							createdAt: { toMillis: () => 1000 },
							completedAt: { toMillis: () => 2000 }
						}
					}
				])
			);

			await waitUntil(() => !!obs.events('sid-1'));
			obs.events('sid-1')!.onNext(
				eventsSnap([
					eventChange('added', {
						attempt: 1,
						seqInAttempt: 1,
						type: 'timeline',
						data: { kind: 'thought', id: 'n1', author: 'research_lead', text: 'Reading sources' }
					})
				])
			);

			expect(chatState.messages[1].activityEvents).toEqual([
				{ kind: 'thought', id: 'n1', author: 'research_lead', text: 'Reading sources' }
			]);
			expect(chatState.liveTimeline).toEqual([]);
		});

		it('detaches when the TURN doc status flips to terminal (not the session)', async () => {
			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.turns('sid-1'));

			primeRunningTurn('sid-1', obs);
			await waitUntil(() => !!obs.events('sid-1'));
			const eventsUnsubBefore = obs.events('sid-1')!.unsubscribe;

			// Session doc flips terminal, but the turn doc is still running:
			// events listener MUST stay attached (pin #6).
			obs.session('sid-1')!.onNext(
				sessionSnap({
					userId: 'uid-test',
					participants: ['uid-test'],
					status: 'complete',
					currentRunId: 'run-1',
					lastTurnIndex: 1
				})
			);
			expect(eventsUnsubBefore).not.toHaveBeenCalled();

			// Now the turn doc flips terminal → detach.
			obs.turns('sid-1')!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'q',
							status: 'complete',
							reply: 'a',
							createdAt: { toMillis: () => 1000 },
							completedAt: { toMillis: () => 2000 }
						}
					}
				])
			);
			expect(eventsUnsubBefore).toHaveBeenCalledTimes(1);
		});
	});

	describe('startNewChat()', () => {
		it('generates a fresh sid, POSTs to /api/agent/stream, and starts listeners for it', async () => {
			const fetchMock: Mock = vi.fn(
				async () =>
					({
						ok: true,
						status: 200,
						json: async () => ({})
					}) as unknown as Response
			);
			vi.stubGlobal('fetch', fetchMock);

			const obs = captureObservers();
			const sid = await chatState.startNewChat('hello', {
				name: 'Bistro',
				secondary: '',
				placeId: 'p1'
			});
			expect(chatState.messages).toHaveLength(1);
			expect(chatState.messages[0]).toMatchObject({
				role: 'user',
				text: 'hello',
				turnIndex: 1
			});
			expect(chatState.currentTurnStartedAtMs).toEqual(expect.any(Number));
			// Wait for the fire-and-forget listener attach inside selectSession()
			// to finish awaiting anon-auth / getFirebase / dynamic import.
			await waitUntil(() => !!obs.session(sid));

			expect(sid).toMatch(/^[0-9a-f-]{20,}$/);
			expect(fetchMock).toHaveBeenCalledTimes(1);
			const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
			expect(url).toBe('/api/agent/stream');
			const body = JSON.parse(init.body as string);
			expect(body.sessionId).toBe(sid);
			expect(body.message).toBe('hello');
			expect(body.placeContext).toMatchObject({ placeId: 'p1' });
			expect(body.history).toBeUndefined();
			expect(init.headers).toMatchObject({
				Authorization: 'Bearer mock-id-token'
			});

			// Listeners for the new sid should be attached.
			expect(obs.session(sid)).toBeTruthy();
			expect(obs.turns(sid)).toBeTruthy();
			expect(chatState.activeSid).toBe(sid);
		});

		it('keeps the optimistic user message through an empty pre-turn snapshot', async () => {
			const fetchMock = vi.fn(
				async () =>
					({
						ok: true,
						status: 200,
						json: async () => ({})
					}) as unknown as Response
			);
			vi.stubGlobal('fetch', fetchMock);

			const obs = captureObservers();
			const sid = chatState.startNewChat('hello', null);
			await waitUntil(() => !!obs.turns(sid));

			obs.turns(sid)!.onNext(turnsSnap([]));
			expect(chatState.messages).toHaveLength(1);
			expect(chatState.messages[0]).toMatchObject({ role: 'user', text: 'hello' });
			const localStartedAt = chatState.currentTurnStartedAtMs;
			expect(localStartedAt).toEqual(expect.any(Number));
			const serverStartedAt = localStartedAt! + 1500;

			obs.turns(sid)!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'hello',
							status: 'running',
							reply: null,
							createdAt: { toMillis: () => serverStartedAt }
						}
					}
				])
			);
			expect(chatState.messages[0]).toMatchObject({
				role: 'user',
				text: 'hello',
				timestamp: serverStartedAt
			});
			expect(chatState.currentTurnStartedAtMs).toBe(localStartedAt);
		});

		it('does not stay loading once a terminal turn snapshot arrives before POST cleanup', async () => {
			const fetchMock = vi.fn(async () => new Promise<Response>(() => {}));
			vi.stubGlobal('fetch', fetchMock);

			const obs = captureObservers();
			const sid = chatState.startNewChat('hello', null);
			await waitUntil(() => !!obs.turns(sid));
			expect(chatState.loading).toBe(true);

			obs.turns(sid)!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'hello',
							status: 'complete',
							reply: 'done',
							createdAt: { toMillis: () => 1000 },
							completedAt: { toMillis: () => 2000 }
						}
					}
				])
			);

			expect(chatState.messages).toHaveLength(2);
			expect(chatState.loading).toBe(false);
		});

		it('throws synchronously on an empty message and does not POST', () => {
			const fetchMock = vi.fn();
			vi.stubGlobal('fetch', fetchMock);
			captureObservers();

			expect(() => chatState.startNewChat('   ', null)).toThrow(/empty/);
			expect(fetchMock).not.toHaveBeenCalled();
		});

		it('pre-Firestore failure (non-2xx) → flips loadState to missing and clears active state', async () => {
			// startNewChat is sync and owns its POST catch. Non-2xx no longer
			// bubbles a rejection to the caller; instead the catch runs a
			// single getDoc check. With the test mock's empty `db: {}`, the
			// dynamic firebase/firestore import throws inside getDoc → treated
			// as pre-Firestore failure → local rollback to loadState='missing'
			// so the chat page renders "Couldn't start this chat".
			const fetchMock = vi.fn(
				async () =>
					({
						ok: false,
						status: 500,
						json: async () => ({ error: 'upstream_down' })
					}) as unknown as Response
			);
			vi.stubGlobal('fetch', fetchMock);
			captureObservers();

			const sid = chatState.startNewChat('hello', null);
			expect(sid).toMatch(/^[0-9a-f-]{20,}$/);
			// Wait for the fire-and-forget catch to complete its rollback.
			await waitUntil(() => chatState.activeSid === null);
			expect(chatState.loadState).toBe('missing');
		});

		// NB: paired tests for the post-Firestore-failure branch (POST 502 +
		// getDoc returns exists=true → no rollback) and the v3.9 P2
		// regression (getFirebase throws inside the catch → rollback) were
		// attempted but vitest's `vi.mock('firebase/firestore', ...)` does
		// NOT propagate to chat-state's dynamic
		// `await import('firebase/firestore')` — the catch block's `doc()`
		// call resolves to the real Firebase fn and throws on the empty
		// `db: {}` mock. F1's fallback: cover both branches via the manual
		// Chrome DevTools MCP smoke (force-offline mid-POST recipe in the
		// Phase 6 smoke section of the execution log) rather than silently
		// skipping. The pre-Firestore rollback above already proves the
		// rollback machinery via the same dynamic-import-throws path.

		it('listener race: optimisticPendingSid suppresses missing flip during POST window', async () => {
			// When startNewChat fires the POST, the active-session listener is
			// already attached. If a server-confirmed `exists=false` snapshot
			// arrives BEFORE agentStream's Firestore txn lands (the gap is
			// ~0.5–1.5 s), `loadState` would briefly flip to 'missing' without
			// the optimisticPendingSid guard. This test simulates that race.
			let resolveFetch: (value: Response) => void;
			const fetchPromise = new Promise<Response>((resolve) => {
				resolveFetch = resolve;
			});
			const fetchMock = vi.fn(async () => fetchPromise);
			vi.stubGlobal('fetch', fetchMock);

			const obs = captureObservers();
			chatState.startNewChat('hello', null);

			// Wait for the optimistic selectSession() to attach listeners.
			await waitUntil(() => !!obs.all.find((c) => c.ref._kind === 'doc'));

			// Fire a server-confirmed exists=false snapshot — simulates the
			// listener seeing the pre-txn gap.
			const sessionObs = obs.all.find((c) => c.ref._kind === 'doc')!;
			sessionObs.onNext({
				metadata: { fromCache: false },
				exists: () => false
			});

			// loadState should NOT have flipped to 'missing' — the
			// optimisticPendingSid guard kept it 'loading'.
			expect(chatState.loadState).toBe('loading');

			// Resolve the POST so the fire-and-forget chain completes cleanly.
			resolveFetch!({ ok: true, status: 200, json: async () => ({}) } as unknown as Response);
			await waitUntil(() => true);
		});
	});

	describe('sendFollowUp()', () => {
		it('installs an optimistic pending turn and POSTs to /api/agent/stream', async () => {
			const fetchMock: Mock = vi.fn(
				async () =>
					({
						ok: true,
						status: 200,
						json: async () => ({})
					}) as unknown as Response
			);
			vi.stubGlobal('fetch', fetchMock);

			captureObservers();
			chatState.selectSession('sid-1');
			await flushAsync();

			await chatState.sendFollowUp('another question');

			expect(chatState.loading).toBe(true);
			expect(chatState.messages.at(-1)).toMatchObject({
				role: 'user',
				text: 'another question',
				turnIndex: 1
			});
			expect(fetchMock).toHaveBeenCalledTimes(1);
			const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
			const body = JSON.parse(init.body as string);
			expect(body.sessionId).toBe('sid-1');
			expect(body.message).toBe('another question');
		});

		it('preserves an optimistic follow-up when the turns snapshot has only older turns', async () => {
			const fetchMock: Mock = vi.fn(
				async () =>
					({
						ok: true,
						status: 200,
						json: async () => ({})
					}) as unknown as Response
			);
			vi.stubGlobal('fetch', fetchMock);

			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.session('sid-1') && !!obs.turns('sid-1'));
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
							userMessage: 'original',
							status: 'complete',
							reply: 'answer',
							createdAt: { toMillis: () => 1000 },
							completedAt: { toMillis: () => 2000 }
						}
					}
				])
			);

			await chatState.sendFollowUp('deeper question');
			expect(chatState.messages.map((m) => m.text)).toContain('deeper question');

			obs.turns('sid-1')!.onNext(
				turnsSnap([
					{
						data: {
							turnIndex: 1,
							runId: 'run-1',
							userMessage: 'original',
							status: 'complete',
							reply: 'answer',
							createdAt: { toMillis: () => 1000 },
							completedAt: { toMillis: () => 2000 }
						}
					}
				])
			);

			expect(chatState.loading).toBe(true);
			expect(chatState.messages.at(-1)).toMatchObject({
				role: 'user',
				text: 'deeper question',
				turnIndex: 2
			});
		});

		it('attaches follow-up events as soon as the session exposes the new run id', async () => {
			const fetchMock: Mock = vi.fn(
				async () =>
					({
						ok: true,
						status: 200,
						json: async () => ({ ok: true, runId: 'run-2' })
					}) as unknown as Response
			);
			vi.stubGlobal('fetch', fetchMock);

			const obs = captureObservers();
			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.session('sid-1') && !!obs.turns('sid-1'));
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
							userMessage: 'original',
							status: 'complete',
							reply: 'answer',
							createdAt: { toMillis: () => 1000 },
							completedAt: { toMillis: () => 2000 }
						}
					}
				])
			);

			await chatState.sendFollowUp('deeper question');
			obs.session('sid-1')!.onNext(
				sessionSnap({
					userId: 'uid-test',
					participants: ['uid-test'],
					status: 'running',
					currentRunId: 'run-2',
					lastTurnIndex: 2
				})
			);

			await waitUntil(() => !!obs.events('sid-1'));
			const ev = obs.events('sid-1')!;
			const constraints =
				(ev.ref as { _constraints?: Array<Record<string, unknown>> })._constraints ?? [];
			const wheres = constraints.filter((c) => (c as { _kind?: string })._kind === 'where');
			expect(wheres[0]).toMatchObject({ f: 'runId', v: 'run-2' });

			ev.onNext(
				eventsSnap([
					eventChange('added', {
						attempt: 1,
						seqInAttempt: 1,
						type: 'timeline',
						data: {
							kind: 'detail',
							id: 'run-start:run-2',
							group: 'platform',
							family: 'Analysis',
							text: 'Continuing research'
						}
					})
				])
			);

			expect(chatState.liveTimeline).toEqual([
				{
					kind: 'detail',
					id: 'run-start:run-2',
					group: 'platform',
					family: 'Analysis',
					text: 'Continuing research'
				}
			]);
		});

		it('throws if no active session', async () => {
			vi.stubGlobal(
				'fetch',
				vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }))
			);
			captureObservers();
			await expect(chatState.sendFollowUp('q')).rejects.toThrow(/no_active_session/);
		});

		it('no-ops on an empty message (does not throw, does not POST)', async () => {
			const fetchMock = vi.fn(
				async () =>
					({
						ok: true,
						status: 200,
						json: async () => ({})
					}) as unknown as Response
			);
			vi.stubGlobal('fetch', fetchMock);
			captureObservers();
			chatState.selectSession('sid-1');
			await flushAsync();

			await chatState.sendFollowUp('   ');
			expect(fetchMock).not.toHaveBeenCalled();
		});
	});

	describe('deleteSession()', () => {
		it('POSTs /api/agent/delete with sid and bearer token', async () => {
			const fetchMock: Mock = vi.fn(
				async () =>
					({
						ok: true,
						status: 200,
						json: async () => ({ ok: true })
					}) as unknown as Response
			);
			vi.stubGlobal('fetch', fetchMock);
			captureObservers();

			await chatState.deleteSession('sid-1');

			expect(fetchMock).toHaveBeenCalledTimes(1);
			const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
			expect(url).toBe('/api/agent/delete');
			expect(init.headers).toMatchObject({
				Authorization: 'Bearer mock-id-token'
			});
			expect(JSON.parse(init.body as string)).toEqual({ sid: 'sid-1' });
		});

		it('on success, clears active listeners when sid matches the active session', async () => {
			const fetchMock = vi.fn(
				async () =>
					({ ok: true, status: 200, json: async () => ({ ok: true }) }) as unknown as Response
			);
			vi.stubGlobal('fetch', fetchMock);
			const obs = captureObservers();

			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.session('sid-1'));
			const sessionUnsub = obs.session('sid-1')!.unsubscribe;

			await chatState.deleteSession('sid-1');

			expect(sessionUnsub).toHaveBeenCalled();
			expect(chatState.activeSid).toBeNull();
		});

		it('leaves the active session alone when deleting a different sid', async () => {
			const fetchMock = vi.fn(
				async () =>
					({ ok: true, status: 200, json: async () => ({ ok: true }) }) as unknown as Response
			);
			vi.stubGlobal('fetch', fetchMock);
			const obs = captureObservers();

			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.session('sid-1'));
			const sessionUnsub = obs.session('sid-1')!.unsubscribe;

			await chatState.deleteSession('sid-2');

			expect(sessionUnsub).not.toHaveBeenCalled();
			expect(chatState.activeSid).toBe('sid-1');
		});

		it('propagates non-2xx as an error with the JSON reason', async () => {
			const fetchMock = vi.fn(
				async () =>
					({
						ok: false,
						status: 403,
						json: async () => ({ error: 'not_creator' })
					}) as unknown as Response
			);
			vi.stubGlobal('fetch', fetchMock);
			captureObservers();

			await expect(chatState.deleteSession('sid-1')).rejects.toThrow('not_creator');
		});
	});

	describe('reset()', () => {
		it('clears active listeners without touching sidebar listener', async () => {
			const obs = captureObservers();
			void chatState.sessionsList;
			await waitUntil(() => !!obs.sidebar);
			const sidebarUnsub = obs.sidebar!.unsubscribe;

			chatState.selectSession('sid-1');
			await waitUntil(() => !!obs.session('sid-1'));
			const sessionUnsub = obs.session('sid-1')!.unsubscribe;

			chatState.reset();

			expect(sessionUnsub).toHaveBeenCalled();
			expect(sidebarUnsub).not.toHaveBeenCalled();
			expect(chatState.activeSid).toBeNull();
		});
	});
});
