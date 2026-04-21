import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';

// Mock firebase/firestore before importing firestore-stream so its dynamic
// `import('firebase/firestore')` resolves to our stubbed module.
vi.mock('firebase/firestore', () => {
	return {
		doc: vi.fn((_db, _col, id) => ({ _id: id })),
		onSnapshot: vi.fn(),
		collectionGroup: vi.fn((_db, name) => ({ _kind: 'collectionGroup', _name: name })),
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
 * Capture the session + events observers so tests can synthesise snapshots
 * from the outside. Returns handles for firing snapshots and errors.
 */
function captureObservers() {
	const captured: Array<{
		ref: unknown;
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
		get session() {
			return captured[0];
		},
		get events() {
			return captured[1];
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
	progress: Array<unknown[]>;
	activities: Array<unknown>;
	completes: Array<unknown[]>;
	errors: string[];
	attempts: number[];
	permDenied: number;
	firstSnapshotTimeout: number;
} {
	const spy = {
		progress: [] as Array<unknown[]>,
		activities: [] as Array<unknown>,
		completes: [] as Array<unknown[]>,
		errors: [] as string[],
		attempts: [] as number[],
		permDenied: 0,
		firstSnapshotTimeout: 0
	};
	return Object.assign(spy, {
		onProgress: (...args: unknown[]) => spy.progress.push(args),
		onActivity: (a: unknown) => spy.activities.push(a),
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

	it('wires two observers: session doc + events collection-group', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);
		expect(obs.count).toBe(2);
	});

	it('session doc status=complete + reply fires onComplete once', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);

		obs.session.onNext(
			sessionSnap({
				status: 'complete',
				reply: 'final answer',
				sources: [{ url: 'https://s.example', title: 's' }],
				title: 'My Chat',
				currentAttempt: 1,
				currentRunId: 'run-1'
			})
		);
		expect(cbs.completes).toEqual([
			['final answer', [{ url: 'https://s.example', title: 's' }], 'My Chat']
		]);
	});

	it('ignores cached status=complete snapshot (waits for server-confirmed)', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);

		obs.session.onNext(
			sessionSnap(
				{ status: 'complete', reply: 'stale', currentAttempt: 1, currentRunId: 'run-1' },
				{ fromCache: true }
			)
		);
		expect(cbs.completes).toEqual([]);

		// Server-confirmed follow-up fires onComplete.
		obs.session.onNext(
			sessionSnap(
				{ status: 'complete', reply: 'real', currentAttempt: 1, currentRunId: 'run-1' },
				{ fromCache: false }
			)
		);
		expect(cbs.completes).toHaveLength(1);
		expect(cbs.completes[0][0]).toBe('real');
	});

	it('ignores cached status=error snapshot (waits for server-confirmed)', async () => {
		// Cached error from a prior turn (same sid reused) must not leak into
		// the current subscription. Server-confirmed error of the current run
		// still fires onError.
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-2', cbs);

		obs.session.onNext(
			sessionSnap(
				{ status: 'error', error: 'prior_turn_error', currentRunId: 'run-2' },
				{ fromCache: true }
			)
		);
		expect(cbs.errors).toEqual([]);

		obs.session.onNext(
			sessionSnap(
				{ status: 'error', error: 'pipeline_error', currentRunId: 'run-2' },
				{ fromCache: false }
			)
		);
		expect(cbs.errors).toEqual(['pipeline_error']);
	});

	it('ignores terminal snapshots with stale currentRunId', async () => {
		// Reused `sid`: turn N-1 errored and is still reflected in the doc
		// when turn N subscribes. The observer must not fire onError for the
		// prior run's terminal state.
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-new', cbs);

		obs.session.onNext(
			sessionSnap({ status: 'error', error: 'prior_turn_error', currentRunId: 'run-old' })
		);
		expect(cbs.errors).toEqual([]);

		obs.session.onNext(
			sessionSnap({ status: 'complete', reply: 'prior reply', currentRunId: 'run-old' })
		);
		expect(cbs.completes).toEqual([]);

		// Once the server flushes the new turn's state it comes through.
		obs.session.onNext(
			sessionSnap({
				status: 'running',
				currentAttempt: 1,
				currentRunId: 'run-new'
			})
		);
		obs.session.onNext(
			sessionSnap({
				status: 'complete',
				reply: 'real',
				currentAttempt: 1,
				currentRunId: 'run-new'
			})
		);
		expect(cbs.completes).toHaveLength(1);
		expect(cbs.completes[0][0]).toBe('real');
	});

	it('session doc status=error fires onError with the error string', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);

		obs.session.onNext(
			sessionSnap({
				status: 'error',
				error: 'pipeline_error',
				currentAttempt: 1,
				currentRunId: 'run-1'
			})
		);
		expect(cbs.errors).toEqual(['pipeline_error']);
	});

	it('increments in currentAttempt fire onAttemptChange', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);

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
		await subscribeToSession('sid-1', 'run-1', cbs);

		obs.session.onNext(
			sessionSnap({ status: 'running', currentAttempt: 3, currentRunId: 'run-1' })
		);
		expect(cbs.attempts).toEqual([]);
	});

	it('snapshots with stale currentRunId do not pollute attempt baseline', async () => {
		// A stale-run snapshot arriving before the server version must not
		// seed `observedAttempt`, otherwise a legitimate attempt change in the
		// new run could be silently dropped.
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-new', cbs);

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

	it('events snapshot dispatches progress + activity by type', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);

		obs.events.onNext(
			eventsSnap([
				eventChange('added', {
					attempt: 1,
					seqInAttempt: 1,
					type: 'progress',
					data: { stage: 'context', status: 'complete', label: 'Place data gathered' }
				}),
				eventChange('added', {
					attempt: 1,
					seqInAttempt: 2,
					type: 'activity',
					data: { id: 'data-primary', category: 'data', status: 'running', label: 'Loading' }
				})
			])
		);

		expect(cbs.progress).toEqual([['context', 'complete', 'Place data gathered', undefined]]);
		expect(cbs.activities).toHaveLength(1);
		expect(cbs.activities[0]).toMatchObject({ id: 'data-primary', status: 'running' });
	});

	it('events-stream type=complete does NOT fire onComplete (session doc is sole terminal)', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);

		// Simulate a stale worker leaking a terminal event doc while the
		// session doc is still `running`. Must not trigger onComplete.
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

		// Session doc still drives the real completion.
		obs.session.onNext(
			sessionSnap({
				status: 'complete',
				reply: 'real reply',
				currentAttempt: 1,
				currentRunId: 'run-1'
			})
		);
		expect(cbs.completes).toHaveLength(1);
		expect(cbs.completes[0][0]).toBe('real reply');
	});

	it('events-stream type=error does NOT fire onError (session doc is sole terminal)', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);

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
		await subscribeToSession('sid-1', 'run-1', cbs);

		obs.events.onNext(
			eventsSnap([
				eventChange('added', {
					attempt: 1,
					seqInAttempt: 1,
					type: 'activity',
					data: { id: 'a1', category: 'data', status: 'running', label: 'L' }
				})
			])
		);
		expect(cbs.activities).toHaveLength(1);

		// Second snapshot replays the same doc — skip.
		obs.events.onNext(
			eventsSnap([
				eventChange('added', {
					attempt: 1,
					seqInAttempt: 1,
					type: 'activity',
					data: { id: 'a1', category: 'data', status: 'running', label: 'L' }
				})
			])
		);
		expect(cbs.activities).toHaveLength(1);
	});

	it('PERMISSION_DENIED on either observer fires onPermissionDenied', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);

		obs.session.onError({ code: 'permission-denied', message: 'denied' });
		expect(cbs.permDenied).toBe(1);

		obs.events.onError({ code: 'permission-denied', message: 'denied' });
		expect(cbs.permDenied).toBe(2);
	});

	it('other snapshot errors do NOT call onPermissionDenied', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);

		obs.session.onError({ code: 'unavailable' });
		expect(cbs.permDenied).toBe(0);
	});

	it('fires onFirstSnapshotTimeout after 10 s if no snapshots arrive', async () => {
		vi.useFakeTimers();
		captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);

		vi.advanceTimersByTime(10_001);
		expect(cbs.firstSnapshotTimeout).toBe(1);
		vi.useRealTimers();
	});

	it('cancels first-snapshot timer once any snapshot arrives', async () => {
		vi.useFakeTimers();
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);

		obs.session.onNext(sessionSnap({ status: 'running', currentAttempt: 1 }));
		vi.advanceTimersByTime(15_000);
		expect(cbs.firstSnapshotTimeout).toBe(0);
		vi.useRealTimers();
	});

	it('returns an unsubscribe function that tears down both observers', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		const unsub = await subscribeToSession('sid-1', 'run-1', cbs);
		unsub();
		expect(obs.session.unsubscribe).toHaveBeenCalledTimes(1);
		expect(obs.events.unsubscribe).toHaveBeenCalledTimes(1);
	});

	it('suppresses duplicate terminal emissions', async () => {
		const obs = captureObservers();
		const cbs = buildCallbacks();
		await subscribeToSession('sid-1', 'run-1', cbs);

		obs.session.onNext(
			sessionSnap({ status: 'complete', reply: 'a', currentAttempt: 1, currentRunId: 'run-1' })
		);
		obs.session.onNext(
			sessionSnap({ status: 'complete', reply: 'a', currentAttempt: 1, currentRunId: 'run-1' })
		);
		expect(cbs.completes).toHaveLength(1);
	});
});
