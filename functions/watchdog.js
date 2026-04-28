// Stuck-session watchdog. Runs every 2 minutes; flips abandoned sessions to
// status='error' with a specific reason. Firestore can't OR across different
// fields from one composite index, so we run three bounded queries and merge
// in code. (Deployed as `watchdog` Cloud Run function + Cloud Scheduler job
// via firebase-functions v2 `onSchedule`.)
//
// Thresholds (gear-only post-Phase-9):
//   - queued > 5 min → handoff_start_timeout. agentStream's gearHandoff
//     normally claims the run within seconds (the plugin's
//     `claim_invocation` flips queued → running). 5 min is generous —
//     anything stuck queued past that means the plugin never claimed
//     (malformed handoff, agentStream crashed mid-dispatch, etc.).
//   - running, heartbeat silent > 10 min → heartbeat_lost. The plugin
//     ticks `lastHeartbeat` every 30 s; 10 min of silence means the
//     Reasoning Engine container crashed or got descheduled.
//   - running, lastEventAt > 5 min → pipeline_wedged. Heartbeat fresh
//     but no ADK events — specialist stuck on a hung tool call, etc.

import { onSchedule } from 'firebase-functions/v2/scheduler';
import { getFirestore, FieldValue } from 'firebase-admin/firestore';

const QUEUED_MAX_AGE_MS = 5 * 60 * 1000;
const HEARTBEAT_MAX_AGE_MS = 10 * 60 * 1000;
const LAST_EVENT_MAX_AGE_MS = 5 * 60 * 1000;
const BATCH_LIMIT = 100;

function toMillis(ts) {
	if (!ts) return null;
	if (typeof ts === 'number') return ts;
	if (typeof ts?.toMillis === 'function') return ts.toMillis();
	return null;
}

/**
 * Pure dispatcher — fetches + merges + returns per-sid classification data
 * without touching Firestore. Split from the handler so tests can drive it
 * with synthetic query results.
 *
 * Each entry carries the metadata the transactional flip needs to re-verify
 * state inside the transaction:
 *   - `expectedStatus` — what status the doc had when classified;
 *   - `expectedRunId` — the runId observed at classification time (catches
 *     the race where a new turn starts between query and flip);
 *   - `thresholdField` — which field was stale;
 *   - `thresholdMillis` — the absolute upper-bound timestamp; if the field
 *     has been freshened past this inside the txn, the worker is alive and
 *     we must back off.
 */
export async function findStuckSessions(db, nowMs = Date.now()) {
	// Firestore auto-converts JS Date to Timestamp for < comparisons, so we
	// don't need to import the explicit Timestamp class.
	const queuedThresholdMs = nowMs - QUEUED_MAX_AGE_MS;
	const heartbeatThresholdMs = nowMs - HEARTBEAT_MAX_AGE_MS;
	const eventThresholdMs = nowMs - LAST_EVENT_MAX_AGE_MS;
	const queuedThreshold = new Date(queuedThresholdMs);
	const heartbeatThreshold = new Date(heartbeatThresholdMs);
	const eventThreshold = new Date(eventThresholdMs);

	const [queuedSnap, heartbeatSnap, eventSnap] = await Promise.all([
		db
			.collection('sessions')
			.where('status', '==', 'queued')
			.where('queuedAt', '<', queuedThreshold)
			.limit(BATCH_LIMIT)
			.get(),
		db
			.collection('sessions')
			.where('status', '==', 'running')
			.where('lastHeartbeat', '<', heartbeatThreshold)
			.limit(BATCH_LIMIT)
			.get(),
		db
			.collection('sessions')
			.where('status', '==', 'running')
			.where('lastEventAt', '<', eventThreshold)
			.limit(BATCH_LIMIT)
			.get()
	]);

	const updates = new Map();

	function classify(sid, entry) {
		if (updates.has(sid)) return; // first classifier wins — deterministic precedence
		updates.set(sid, entry);
	}

	for (const doc of queuedSnap.docs) {
		const d = doc.data();
		const ageMs = nowMs - (toMillis(d.queuedAt) ?? nowMs);
		classify(doc.id, {
			reason: 'handoff_start_timeout',
			errorDetails: { queuedAtAgeMs: ageMs },
			expectedStatus: 'queued',
			expectedRunId: d.currentRunId ?? null,
			thresholdField: 'queuedAt',
			thresholdMillis: queuedThresholdMs
		});
	}
	for (const doc of heartbeatSnap.docs) {
		const d = doc.data();
		const ageMs = nowMs - (toMillis(d.lastHeartbeat) ?? nowMs);
		classify(doc.id, {
			reason: 'heartbeat_lost',
			errorDetails: { lastHeartbeatAgeMs: ageMs },
			expectedStatus: 'running',
			expectedRunId: d.currentRunId ?? null,
			thresholdField: 'lastHeartbeat',
			thresholdMillis: heartbeatThresholdMs
		});
	}
	for (const doc of eventSnap.docs) {
		const d = doc.data();
		const ageMs = nowMs - (toMillis(d.lastEventAt) ?? nowMs);
		classify(doc.id, {
			reason: 'pipeline_wedged',
			errorDetails: { lastEventAgeMs: ageMs },
			expectedStatus: 'running',
			expectedRunId: d.currentRunId ?? null,
			thresholdField: 'lastEventAt',
			thresholdMillis: eventThresholdMs
		});
	}

	return [...updates.entries()].map(([sid, info]) => ({ sid, ...info }));
}

export async function runWatchdog(db, nowMs = Date.now()) {
	const stuck = await findStuckSessions(db, nowMs);

	// Flip stuck sessions to error inside a transaction so a worker that
	// completes between the initial query and the flip cannot be clobbered
	// with status=error over a real `status=complete`. The txn re-reads the
	// doc and aborts silently if any of the four preconditions no longer
	// hold. Per-reason skip counters aid post-incident debugging — without
	// them a `skipped=12` summary hides whether the watchdog was racing
	// worker completions, stale runIds, or freshened heartbeats. See plan
	// Tier 1.4.
	let flipped = 0;
	const skipReasons = { missing: 0, status_changed: 0, run_advanced: 0, field_freshened: 0 };
	for (const entry of stuck) {
		const {
			sid,
			reason,
			errorDetails,
			expectedStatus,
			expectedRunId,
			thresholdField,
			thresholdMillis
		} = entry;
		try {
			const ref = db.collection('sessions').doc(sid);
			const result = await db.runTransaction(async (tx) => {
				const snap = await tx.get(ref);
				if (!snap.exists) return 'missing';
				const data = snap.data();
				if (data.status !== expectedStatus) return 'status_changed';
				if (expectedRunId !== null && data.currentRunId !== expectedRunId) {
					return 'run_advanced';
				}
				const fieldMillis = toMillis(data[thresholdField]);
				if (fieldMillis !== null && fieldMillis > thresholdMillis) {
					return 'field_freshened';
				}
				// Server-stored sessions (plan §8): propagate the error to the
				// in-flight turn doc in the same transaction. agentStream
				// enforces that `turns/{lastTurnIndex}` is the doc for
				// `currentRunId`, so the predicates already validated above
				// keep that invariant intact. If `lastTurnIndex` is missing
				// (e.g., a partial-enqueue legacy doc), skip the turn write
				// rather than fail the flip — the session update is still the
				// meaningful signal.
				tx.update(ref, {
					status: 'error',
					error: reason,
					errorDetails,
					updatedAt: FieldValue.serverTimestamp()
				});
				const lastTurnIndex = data.lastTurnIndex;
				if (typeof lastTurnIndex === 'number' && lastTurnIndex > 0) {
					const turnKey = String(lastTurnIndex).padStart(4, '0');
					const turnRef = ref.collection('turns').doc(turnKey);
					tx.update(turnRef, {
						status: 'error',
						error: reason
					});
				}
				return 'flipped';
			});
			if (result === 'flipped') {
				flipped++;
			} else if (result in skipReasons) {
				skipReasons[result]++;
			}
		} catch (err) {
			console.warn(`[watchdog] failed to flip ${sid}:`, err?.message || err);
		}
	}

	const skipped =
		skipReasons.missing +
		skipReasons.status_changed +
		skipReasons.run_advanced +
		skipReasons.field_freshened;
	console.log(
		`[watchdog] stuck=${stuck.length} flipped=${flipped} skipped=${skipped}` +
			` (missing=${skipReasons.missing} status_changed=${skipReasons.status_changed}` +
			` run_advanced=${skipReasons.run_advanced} field_freshened=${skipReasons.field_freshened})`
	);
	return { stuck: stuck.length, flipped, skipped, skipReasons };
}

export const watchdog = onSchedule(
	{
		schedule: 'every 2 minutes',
		timeoutSeconds: 120,
		memory: '256MiB',
		region: 'us-central1'
	},
	async () => {
		const db = getFirestore();
		await runWatchdog(db);
	}
);
