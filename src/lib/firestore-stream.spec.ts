import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';

// Mock firebase/firestore before importing firestore-stream so its dynamic
// `import('firebase/firestore')` resolves to our stubbed module.
vi.mock('firebase/firestore', () => {
	return {
		// `doc(db, col, id)` → `/sessions/{id}`; `doc(db, col, sid, sub, key)`
		// → `/sessions/{sid}/turns/{key}`. The test partitions observers by
		// the ref's `_path`.
		doc: vi.fn((_db, ...parts: string[]) => ({ _path: parts.join('/') })),
		onSnapshot: vi.fn(),
		collection: vi.fn((_db, ...parts: string[]) => ({
			_kind: 'collection',
			_path: parts.join('/')
		})),
		query: vi.fn((ref, ...constraints) => ({ _ref: ref, _constraints: constraints })),
		where: vi.fn((f, op, v) => ({ _kind: 'where', f, op, v })),
		orderBy: vi.fn((f) => ({ _kind: 'orderBy', f }))
	};
});

// Mock firebase singleton. getFirebase returns a stub db; ensureAnonAuth
// returns a deterministic uid.
vi.mock('$lib/firebase', () => ({
	getFirebase: vi.fn(async () => ({ db: {}, auth: {} })),
	ensureAnonAuth: vi.fn(async () => 'uid-test'),
	getIdToken: vi.fn(async () => 'mock-id-token')
}));

import { subscribeToSession, type StreamCallbacks } from './firestore-stream';
import { onSnapshot } from 'firebase/firestore';

const mockOnSnapshot = onSnapshot as unknown as Mock;

type SnapHandler = (snap: unknown) => void;
type ErrHandler = (err: unknown) => void;

/**
 * Capture the session / turn / events observers so tests can synthesise
 * snapshots from the outside. Observers are partitioned by the `_path` tag
 * attached to each ref/query by the mock factory above.
 */
function captureObservers() {
	const captured: Array<{
		ref: { _path?: string; _ref?: { _path?: string } };
		onNext: SnapHandler;
		onError: ErrHandler;
		unsubscribe: Mock;
	}> = [];
	mockOnSnapshot.mockImplementation((ref, onNext, onError) => {
		const unsubscribe = vi.fn();
		captured.push({ ref, onNext, onError, unsubscribe });
		return unsubscribe;
	});
	return {
		/** `sessions/{sid}` observer — path has 2 segments. */
		get session() {
			return captured.find((c) => c.ref._path?.split('/').length === 2)!;
		},
		/** `sessions/{sid}/turns/{turnKey}` observer — 4-segment path. */
		get turn() {
			return captured.find(
				(c) => c.ref._path?.split('/').length === 4 && c.ref._path?.includes('/turns/')
			)!;
		},
		/** Events query — ref is a `query(...)` wrapper whose `_ref._path`
		 *  matches `sessions/{sid}/events`. */
		get events() {
			return captured.find((c) => c.ref._ref?._path?.endsWith('/events'))!;
		},
		get count() {
			return captured.length;
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

function turnSnap(
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

function eventChange(type: 'added' | 'modified' | 'removed', data: Record<string, unknown>) {
	return { type, doc: { data: () => data } };
}

function eventsSnap(
	changes: Array<ReturnType<typeof eventChange>>,
	{ fromCache = false }: { fromCache?: boolean } = {}
) {
	return {
		docChanges: () => changes,
		metadata: { fromCache }
	};
}

function buildCallbacks(): StreamCallbacks & {
	timeline: Array<unknown>;
	completes: Array<unknown[]>;
	errors: string[];
	attempts: number[];
	permDenied: number;
	firstSnapshotTimeout: number;
} {
	const spy = {
		timeline: [] as Array<unknown>,
		completes: [] as Array<unknown[]>,
		errors: [] as string[],
		attempts: [] as number[],
		permDenied: 0,
		firstSnapshotTimeout: 0
	};
	return Object.assign(spy, {
		onTimelineEvent: (event: unknown) => spy.timeline.push(event),
		onComplete: (...args: unknown[]) => spy.completes.push(args),
		onError: (e: string) => spy.errors.push(e),
		onAttemptChange: (n: number) => spy.attempts.push(n),
		onPermissionDenied: () => {
			spy.permDenied++;
		},
		onFirstSnapshotTimeout: () => {
			spy.firstSnapshotTimeout++;
		}
	});
}

describe('subscribeToSession', () => {
	beforeEach(() => {
		mockOnSnapshot.mockReset();
		vi.useRealTimers();
	});

	it('wires three observers: session doc + turn doc + events per-session collection', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);
		expect(obs.count).toBe(3);
		expect(obs.session.ref._path).toBe('sessions/sid-1');
		expect(obs.turn.ref._path).toBe('sessions/sid-1/turns/0000');
		// Events query is scoped to the per-session path, not a
		// collection-group.
		expect(obs.events.ref._ref?._path).toBe('sessions/sid-1/events');
	});

	it('turn doc with 4-digit zero-padded key for large turn indices', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 9, cbs);
		expect(obs.turn.ref._path).toBe('sessions/sid-1/turns/0009');
	});

	it('turn doc status=complete + reply fires onComplete with title from session doc', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		// Session delivers title first.
		obs.session.onNext(
			sessionSnap({
				status: 'running',
				title: 'My Chat',
				currentAttempt: 1,
				currentRunId: 'run-1'
			})
		);

		// Turn doc settles with the terminal content.
		obs.turn.onNext(
			turnSnap({
				status: 'complete',
				runId: 'run-1',
				reply: 'final answer',
				sources: [{ url: 'https://s.example', title: 's' }],
				turnSummary: undefined
			})
		);

		expect(cbs.completes).toEqual([
			['final answer', [{ url: 'https://s.example', title: 's' }], 'My Chat', undefined]
		]);
	});

	it("turn doc terminal fires even when session hasn't delivered title yet (undefined title)", async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		obs.turn.onNext(
			turnSnap({
				status: 'complete',
				runId: 'run-1',
				reply: 'final answer',
				sources: []
			})
		);

		expect(cbs.completes).toEqual([['final answer', [], undefined, undefined]]);
	});

	it('ignores cached turn status=complete snapshot (waits for server-confirmed)', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		obs.turn.onNext(
			turnSnap({ status: 'complete', runId: 'run-1', reply: 'stale' }, { fromCache: true })
		);
		expect(cbs.completes).toEqual([]);

		obs.turn.onNext(
			turnSnap({ status: 'complete', runId: 'run-1', reply: 'real' }, { fromCache: false })
		);
		expect(cbs.completes).toHaveLength(1);
		expect(cbs.completes[0][0]).toBe('real');
	});

	it('ignores cached turn status=error snapshot (waits for server-confirmed)', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-2', 1, cbs);

		obs.turn.onNext(
			turnSnap({ status: 'error', runId: 'run-2', error: 'prior_turn_error' }, { fromCache: true })
		);
		expect(cbs.errors).toEqual([]);

		obs.turn.onNext(
			turnSnap({ status: 'error', runId: 'run-2', error: 'pipeline_error' }, { fromCache: false })
		);
		expect(cbs.errors).toEqual(['pipeline_error']);
	});

	it('turn doc with mismatched runId is ignored (defensive)', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-new', 0, cbs);

		obs.turn.onNext(turnSnap({ status: 'complete', runId: 'run-old', reply: 'prior reply' }));
		expect(cbs.completes).toEqual([]);

		obs.turn.onNext(turnSnap({ status: 'complete', runId: 'run-new', reply: 'real' }));
		expect(cbs.completes).toHaveLength(1);
		expect(cbs.completes[0][0]).toBe('real');
	});

	it('session doc with stale currentRunId does not pollute attempt baseline', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-new', 0, cbs);

		// Stale: currentAttempt=5 from prior run. Must be ignored entirely.
		obs.session.onNext(
			sessionSnap({ status: 'running', currentAttempt: 5, currentRunId: 'run-old' })
		);
		// First new-run snapshot: attempt=1. Baseline, no onAttemptChange.
		obs.session.onNext(
			sessionSnap({ status: 'running', currentAttempt: 1, currentRunId: 'run-new' })
		);
		// Retry: attempt=2. Should fire onAttemptChange.
		obs.session.onNext(
			sessionSnap({ status: 'running', currentAttempt: 2, currentRunId: 'run-new' })
		);
		expect(cbs.attempts).toEqual([2]);
	});

	it('turn doc status=error fires onError with the error string', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		obs.turn.onNext(turnSnap({ status: 'error', runId: 'run-1', error: 'pipeline_error' }));
		expect(cbs.errors).toEqual(['pipeline_error']);
	});

	it('increments in currentAttempt fire onAttemptChange', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		obs.session.onNext(
			sessionSnap({ status: 'running', currentAttempt: 1, currentRunId: 'run-1' })
		);
		obs.session.onNext(
			sessionSnap({ status: 'running', currentAttempt: 2, currentRunId: 'run-1' })
		);
		expect(cbs.attempts).toEqual([2]);
	});

	it('first observed attempt sets the baseline, no onAttemptChange fired', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		obs.session.onNext(
			sessionSnap({ status: 'running', currentAttempt: 3, currentRunId: 'run-1' })
		);
		expect(cbs.attempts).toEqual([]);
	});

	it('events snapshot dispatches timeline rows by type', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		obs.events.onNext(
			eventsSnap([
				eventChange('added', {
					attempt: 1,
					seqInAttempt: 1,
					type: 'timeline',
					data: {
						kind: 'note',
						id: 'n1',
						text: 'Checking the venue',
						noteSource: 'deterministic',
						counts: { webQueries: 0, sources: 0, venues: 1, platforms: 1 }
					}
				}),
				eventChange('added', {
					attempt: 1,
					seqInAttempt: 2,
					type: 'timeline',
					data: {
						kind: 'detail',
						id: 'd1',
						group: 'platform',
						family: 'Google Maps',
						text: 'Profile for Umami'
					}
				})
			])
		);

		expect(cbs.timeline).toHaveLength(2);
		expect(cbs.timeline[0]).toMatchObject({ kind: 'note', id: 'n1' });
		expect(cbs.timeline[1]).toMatchObject({ kind: 'detail', id: 'd1', family: 'Google Maps' });
	});

	it('events-stream type=complete does NOT fire onComplete (turn doc is sole terminal)', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		// Simulate a stale worker leaking a terminal event doc while the
		// turn doc is still `running`. Must not trigger onComplete.
		obs.events.onNext(
			eventsSnap([
				eventChange('added', {
					attempt: 1,
					seqInAttempt: 1,
					type: 'complete',
					data: { reply: 'stale reply from a fenced-out worker', sources: [] }
				})
			])
		);
		expect(cbs.completes).toEqual([]);

		// Turn doc drives the real completion.
		obs.turn.onNext(
			turnSnap({
				status: 'complete',
				runId: 'run-1',
				reply: 'real reply',
				sources: []
			})
		);
		expect(cbs.completes).toHaveLength(1);
		expect(cbs.completes[0][0]).toBe('real reply');
	});

	it('events-stream type=error does NOT fire onError (turn doc is sole terminal)', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		obs.events.onNext(
			eventsSnap([
				eventChange('added', {
					attempt: 1,
					seqInAttempt: 1,
					type: 'error',
					data: { error: 'stale_error_from_unfenced_event' }
				})
			])
		);
		expect(cbs.errors).toEqual([]);
	});

	it('skips events already rendered (reconnect replay)', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		obs.events.onNext(
			eventsSnap([
				eventChange('added', {
					attempt: 1,
					seqInAttempt: 1,
					type: 'timeline',
					data: { kind: 'detail', id: 'a1', group: 'platform', family: 'Google Maps', text: 'L' }
				})
			])
		);
		expect(cbs.timeline).toHaveLength(1);

		// Second snapshot replays the same doc — skip.
		obs.events.onNext(
			eventsSnap([
				eventChange('added', {
					attempt: 1,
					seqInAttempt: 1,
					type: 'timeline',
					data: { kind: 'detail', id: 'a1', group: 'platform', family: 'Google Maps', text: 'L' }
				})
			])
		);
		expect(cbs.timeline).toHaveLength(1);
	});

	it('PERMISSION_DENIED on any observer fires onPermissionDenied exactly once', async () => {
		// All three observers share a single handleErr; without the
		// one-shot guard, errors from multiple observers would double-fire
		// the callback. Per the `StreamCallbacks.onPermissionDenied` JSDoc
		// contract.
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		obs.session.onError({ code: 'permission-denied', message: 'denied' });
		expect(cbs.permDenied).toBe(1);

		obs.turn.onError({ code: 'permission-denied', message: 'denied' });
		expect(cbs.permDenied).toBe(1);

		obs.events.onError({ code: 'permission-denied', message: 'denied' });
		expect(cbs.permDenied).toBe(1);
	});

	it('other snapshot errors do NOT call onPermissionDenied', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		obs.session.onError({ code: 'unavailable' });
		expect(cbs.permDenied).toBe(0);
	});

	it('fires onFirstSnapshotTimeout after 10 s if no snapshots arrive', async () => {
		vi.useFakeTimers();
		captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		vi.advanceTimersByTime(10_001);
		expect(cbs.firstSnapshotTimeout).toBe(1);
		vi.useRealTimers();
	});

	it('cancels first-snapshot timer once any snapshot arrives', async () => {
		vi.useFakeTimers();
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		obs.turn.onNext(turnSnap({ status: 'running', runId: 'run-1' }));
		vi.advanceTimersByTime(15_000);
		expect(cbs.firstSnapshotTimeout).toBe(0);
		vi.useRealTimers();
	});

	it('returns an unsubscribe function that tears down all three observers', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		const unsub = await subscribeToSession('sid-1', 'run-1', 0, cbs);
		unsub();
		expect(obs.session.unsubscribe).toHaveBeenCalledTimes(1);
		expect(obs.turn.unsubscribe).toHaveBeenCalledTimes(1);
		expect(obs.events.unsubscribe).toHaveBeenCalledTimes(1);
	});

	it('suppresses duplicate terminal emissions', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', 0, cbs);

		obs.turn.onNext(turnSnap({ status: 'complete', runId: 'run-1', reply: 'a', sources: [] }));
		obs.turn.onNext(turnSnap({ status: 'complete', runId: 'run-1', reply: 'a', sources: [] }));
		expect(cbs.completes).toHaveLength(1);
	});

	it('events query is filtered by runId (not by userId)', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-42', 0, cbs);

		const constraints = (
			obs.events.ref as { _constraints?: Array<{ _kind?: string; f?: string; v?: unknown }> }
		)._constraints;
		const whereClauses = (constraints ?? []).filter((c) => c._kind === 'where');
		// Exactly one `where` — on runId. The old code had a second where on
		// userId which must be gone.
		expect(whereClauses).toHaveLength(1);
		expect(whereClauses[0]).toMatchObject({ f: 'runId', v: 'run-42' });
	});
});
