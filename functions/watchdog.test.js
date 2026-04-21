import { describe, it, mock, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

// Mock firebase-admin/firestore before importing watchdog.
mock.module('firebase-admin/firestore', {
	namedExports: {
		getFirestore: () => ({})
	}
});

// The v2 scheduler wraps our handler; stub it to just return the handler so
// importing doesn't try to register a scheduled trigger.
mock.module('firebase-functions/v2/scheduler', {
	namedExports: {
		onSchedule: (_opts, handler) => handler
	}
});

const { findStuckSessions, runWatchdog } = await import('./watchdog.js');

function millisTs(ms) {
	return { toMillis: () => ms };
}

function mockSnap(docs) {
	return { docs };
}

function mockDoc(id, data) {
	return {
		id,
		data: () => data,
		ref: { id }
	};
}

/**
 * Build a mock Firestore that routes `.collection('sessions').where(...).get()`
 * calls to predetermined snapshots based on (status, field) fingerprint.
 *
 * `txReads` maps sid → the doc snapshot returned inside runTransaction
 * (so tests can simulate a sid whose state changed between the initial
 * query and the fenced re-read).
 */
function makeDb(plans, { txReads = {} } = {}) {
	const queryChain = (matchKey) => ({
		where(field, _op, _value) {
			if (field === 'status') return queryChain(matchKey + '|status');
			return queryChain(matchKey + '|' + field);
		},
		orderBy(_field) {
			return queryChain(matchKey + '|order');
		},
		limit(_n) {
			return queryChain(matchKey + '|limit');
		},
		get: mock.fn(async () => plans[matchKey] ?? mockSnap([]))
	});

	const batchUpdates = [];
	const docUpdates = [];
	const txUpdates = [];

	return {
		_docUpdates: docUpdates,
		_batchUpdates: batchUpdates,
		_txUpdates: txUpdates,
		collection(name) {
			const base = queryChain(name);
			return {
				...base,
				doc: (id) => ({
					id,
					update: mock.fn(async (data) => {
						docUpdates.push({ id, data });
					})
				})
			};
		},
		batch() {
			const ops = [];
			return {
				update(ref, data) {
					ops.push({ ref, data });
				},
				commit: mock.fn(async () => {
					batchUpdates.push(...ops);
				})
			};
		},
		async runTransaction(fn) {
			const tx = {
				async get(ref) {
					// The ref object has `id` attached by `.doc(id)`.
					const id = ref.id;
					const readState = txReads[id];
					if (readState === undefined) {
						// Default: empty snapshot (doc missing).
						return { exists: false, data: () => ({}) };
					}
					return {
						exists: true,
						data: () => readState
					};
				},
				update(ref, data) {
					txUpdates.push({ id: ref.id, data });
				}
			};
			return await fn(tx);
		}
	};
}

const NOW = 1_000_000_000_000;

describe('findStuckSessions', () => {
	it('classifies queued-too-long as queue_dispatch_timeout', async () => {
		const plans = {
			'sessions|status|queuedAt|limit': mockSnap([
				mockDoc('sid-1', {
					status: 'queued',
					queuedAt: millisTs(NOW - 45 * 60 * 1000)
				})
			])
		};
		const db = makeDb(plans);
		const out = await findStuckSessions(db, NOW);
		assert.equal(out.length, 1);
		assert.equal(out[0].sid, 'sid-1');
		assert.equal(out[0].reason, 'queue_dispatch_timeout');
		assert.equal(out[0].errorDetails.queuedAtAgeMs, 45 * 60 * 1000);
	});

	it('classifies stale-heartbeat running session as worker_lost', async () => {
		const plans = {
			'sessions|status|lastHeartbeat|limit': mockSnap([
				mockDoc('sid-hb', {
					status: 'running',
					lastHeartbeat: millisTs(NOW - 12 * 60 * 1000),
					currentAttempt: 2
				})
			])
		};
		const db = makeDb(plans);
		const out = await findStuckSessions(db, NOW);
		assert.equal(out.length, 1);
		assert.equal(out[0].reason, 'worker_lost');
		assert.equal(out[0].errorDetails.currentAttempt, 2);
	});

	it('classifies wedged pipeline (fresh heartbeat, stale lastEventAt) as pipeline_wedged', async () => {
		const plans = {
			'sessions|status|lastEventAt|limit': mockSnap([
				mockDoc('sid-wedge', {
					status: 'running',
					lastEventAt: millisTs(NOW - 7 * 60 * 1000),
					currentAttempt: 1
				})
			])
		};
		const db = makeDb(plans);
		const out = await findStuckSessions(db, NOW);
		assert.equal(out.length, 1);
		assert.equal(out[0].reason, 'pipeline_wedged');
		assert.equal(out[0].errorDetails.currentAttempt, 1);
	});

	it('dedupes by sid — queued classifier wins over heartbeat for same sid', async () => {
		// Pathological: a doc matches multiple queries.
		const doc = mockDoc('dup', {
			status: 'queued',
			queuedAt: millisTs(NOW - 45 * 60 * 1000),
			lastHeartbeat: millisTs(NOW - 15 * 60 * 1000)
		});
		const plans = {
			'sessions|status|queuedAt|limit': mockSnap([doc]),
			'sessions|status|lastHeartbeat|limit': mockSnap([doc])
		};
		const db = makeDb(plans);
		const out = await findStuckSessions(db, NOW);
		assert.equal(out.length, 1);
		assert.equal(out[0].reason, 'queue_dispatch_timeout');
	});

	it('returns empty list when nothing is stuck', async () => {
		const db = makeDb({});
		const out = await findStuckSessions(db, NOW);
		assert.deepEqual(out, []);
	});
});

describe('runWatchdog', () => {
	it('flips each stuck session to status=error via fenced transaction', async () => {
		const plans = {
			'sessions|status|queuedAt|limit': mockSnap([
				mockDoc('q1', {
					status: 'queued',
					queuedAt: millisTs(NOW - 45 * 60 * 1000),
					currentRunId: 'run-q1'
				})
			]),
			'sessions|status|lastHeartbeat|limit': mockSnap([
				mockDoc('hb1', {
					status: 'running',
					lastHeartbeat: millisTs(NOW - 12 * 60 * 1000),
					currentAttempt: 3,
					currentRunId: 'run-hb1'
				})
			])
		};
		// Inside the txn, the doc state is unchanged — still stuck. Flip lands.
		const txReads = {
			q1: {
				status: 'queued',
				queuedAt: millisTs(NOW - 45 * 60 * 1000),
				currentRunId: 'run-q1'
			},
			hb1: {
				status: 'running',
				lastHeartbeat: millisTs(NOW - 12 * 60 * 1000),
				currentAttempt: 3,
				currentRunId: 'run-hb1'
			}
		};
		const db = makeDb(plans, { txReads });
		const result = await runWatchdog(db, NOW);

		assert.equal(result.stuck, 2);
		assert.equal(result.flipped, 2);
		assert.equal(result.skipped, 0);
		assert.equal(db._txUpdates.length, 2);
		const q1 = db._txUpdates.find((u) => u.id === 'q1');
		const hb1 = db._txUpdates.find((u) => u.id === 'hb1');
		assert.equal(q1.data.status, 'error');
		assert.equal(q1.data.error, 'queue_dispatch_timeout');
		assert.equal(hb1.data.status, 'error');
		assert.equal(hb1.data.error, 'worker_lost');
		assert.equal(hb1.data.errorDetails.currentAttempt, 3);
	});

	it('returns per-reason skip breakdown for ops visibility', async () => {
		// Three stuck docs, each racing against a different abort reason:
		// q1 → worker completed (status_changed)
		// hb1 → worker alive (field_freshened)
		// q2 → new turn started (run_advanced)
		const plans = {
			'sessions|status|queuedAt|limit': mockSnap([
				mockDoc('q1', {
					status: 'queued',
					queuedAt: millisTs(NOW - 45 * 60 * 1000),
					currentRunId: 'run-q1'
				}),
				mockDoc('q2', {
					status: 'queued',
					queuedAt: millisTs(NOW - 45 * 60 * 1000),
					currentRunId: 'run-old'
				})
			]),
			'sessions|status|lastHeartbeat|limit': mockSnap([
				mockDoc('hb1', {
					status: 'running',
					lastHeartbeat: millisTs(NOW - 12 * 60 * 1000),
					currentAttempt: 1,
					currentRunId: 'run-hb1'
				})
			])
		};
		const txReads = {
			q1: { status: 'complete', currentRunId: 'run-q1' }, // status_changed
			hb1: {
				status: 'running',
				lastHeartbeat: millisTs(NOW - 10 * 1000), // fresh → field_freshened
				currentRunId: 'run-hb1'
			},
			q2: {
				status: 'queued',
				queuedAt: millisTs(NOW - 10 * 1000),
				currentRunId: 'run-new' // run_advanced
			}
		};
		const db = makeDb(plans, { txReads });
		const result = await runWatchdog(db, NOW);

		assert.equal(result.stuck, 3);
		assert.equal(result.flipped, 0);
		assert.equal(result.skipped, 3);
		assert.equal(result.skipReasons.status_changed, 1);
		assert.equal(result.skipReasons.field_freshened, 1);
		assert.equal(result.skipReasons.run_advanced, 1);
		assert.equal(result.skipReasons.missing, 0);
	});

	it('aborts silently if status changed between query and txn (worker completed)', async () => {
		const plans = {
			'sessions|status|lastHeartbeat|limit': mockSnap([
				mockDoc('hb1', {
					status: 'running',
					lastHeartbeat: millisTs(NOW - 12 * 60 * 1000),
					currentAttempt: 2,
					currentRunId: 'run-hb1'
				})
			])
		};
		// Race: worker finished between query and txn.
		const txReads = {
			hb1: {
				status: 'complete',
				lastHeartbeat: millisTs(NOW - 12 * 60 * 1000),
				currentRunId: 'run-hb1'
			}
		};
		const db = makeDb(plans, { txReads });
		const result = await runWatchdog(db, NOW);

		assert.equal(result.stuck, 1);
		assert.equal(result.flipped, 0);
		assert.equal(result.skipped, 1);
		assert.equal(db._txUpdates.length, 0);
	});

	it('aborts silently if threshold field was freshened (worker alive)', async () => {
		const plans = {
			'sessions|status|lastHeartbeat|limit': mockSnap([
				mockDoc('hb1', {
					status: 'running',
					lastHeartbeat: millisTs(NOW - 12 * 60 * 1000),
					currentAttempt: 1,
					currentRunId: 'run-hb1'
				})
			])
		};
		// Race: worker wrote a fresh heartbeat between query and txn.
		const txReads = {
			hb1: {
				status: 'running',
				lastHeartbeat: millisTs(NOW - 10 * 1000), // 10 s old — well within threshold
				currentAttempt: 1,
				currentRunId: 'run-hb1'
			}
		};
		const db = makeDb(plans, { txReads });
		const result = await runWatchdog(db, NOW);

		assert.equal(result.stuck, 1);
		assert.equal(result.flipped, 0);
		assert.equal(result.skipped, 1);
		assert.equal(db._txUpdates.length, 0);
	});

	it('aborts silently if a new turn started (currentRunId advanced)', async () => {
		const plans = {
			'sessions|status|queuedAt|limit': mockSnap([
				mockDoc('q1', {
					status: 'queued',
					queuedAt: millisTs(NOW - 45 * 60 * 1000),
					currentRunId: 'run-old'
				})
			])
		};
		// Race: a new turn was enqueued on the same sid with a fresh runId.
		const txReads = {
			q1: {
				status: 'queued',
				queuedAt: millisTs(NOW - 10 * 1000),
				currentRunId: 'run-new'
			}
		};
		const db = makeDb(plans, { txReads });
		const result = await runWatchdog(db, NOW);

		assert.equal(result.stuck, 1);
		assert.equal(result.flipped, 0);
		assert.equal(result.skipped, 1);
		assert.equal(db._txUpdates.length, 0);
	});

	it('continues flipping other sessions if one transaction throws', async () => {
		const plans = {
			'sessions|status|queuedAt|limit': mockSnap([
				mockDoc('q1', {
					status: 'queued',
					queuedAt: millisTs(NOW - 45 * 60 * 1000),
					currentRunId: 'run-q1'
				})
			]),
			'sessions|status|lastHeartbeat|limit': mockSnap([
				mockDoc('hb1', {
					status: 'running',
					lastHeartbeat: millisTs(NOW - 12 * 60 * 1000),
					currentAttempt: 1,
					currentRunId: 'run-hb1'
				})
			])
		};
		const txReads = {
			hb1: {
				status: 'running',
				lastHeartbeat: millisTs(NOW - 12 * 60 * 1000),
				currentAttempt: 1,
				currentRunId: 'run-hb1'
			}
		};
		const db = makeDb(plans, { txReads });
		// Override runTransaction to throw when the tx tries to read q1.
		const origTx = db.runTransaction.bind(db);
		db.runTransaction = async (fn) => {
			return await origTx(async (tx) => {
				const wrappedTx = {
					async get(ref) {
						if (ref.id === 'q1') throw new Error('simulated txn failure');
						return tx.get(ref);
					},
					update: tx.update.bind(tx)
				};
				return await fn(wrappedTx);
			});
		};
		const result = await runWatchdog(db, NOW);

		assert.equal(result.stuck, 2);
		assert.ok(result.flipped >= 1); // hb1 flipped; q1 threw
	});
});
