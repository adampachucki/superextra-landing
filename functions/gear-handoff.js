/**
 * gearHandoff — Cloud Function side of the GEAR migration dispatch.
 *
 * agentStream calls `gearHandoff()` after committing the Firestore session
 * txn. The helper:
 *   1. Idempotently creates the Vertex AI Agent Engine session on the
 *      first turn of a chat (camelCase REST `?sessionId=se-{sid}`,
 *      ALREADY_EXISTS treated as success per plan §5.3).
 *   2. Posts an `:appendEvent` with the verified payload from probe
 *      round R3.1 (`author='system'`, RFC3339 timestamp, camelCase
 *      `invocationId`/`actions.stateDelta`) to mutate session.state with
 *      runId/turnIdx — the plugin reads these in `before_run_callback`.
 *   3. Opens the `:streamQuery` NDJSON stream, reads the first line as
 *      proof the runtime accepted the handoff, then explicitly cancels
 *      the reader and aborts the underlying fetch via a shared
 *      `AbortController`. Verified durable for ≥240 s by R3.2: the
 *      runtime keeps running our agent for the full pipeline duration
 *      after this disconnect.
 *
 * One `AbortController` is constructed at gearHandoff scope and passed
 * into every fetch (createSession, appendEvent, streamQuery). When the
 * deadline rejects, calling `controller.abort()` cancels every in-flight
 * HTTP fetch — without this hoist, losing-side fetches would keep
 * running as background work and Firebase's "no progress after
 * termination" warning would bite. (plan §"App-level timeout for
 * gearHandoff cleanup")
 *
 * On any failure after the Firestore session txn already wrote
 * status='queued', `gearHandoffCleanup` flips session+turn to
 * status='error' atomically inside a `currentRunId`-fenced transaction.
 */

import { GoogleAuth } from 'google-auth-library';
import { FieldValue } from 'firebase-admin/firestore';

const VERTEX_BASE = 'https://us-central1-aiplatform.googleapis.com';

// CF timeout is 90s; we reserve ~15s for cleanup-on-failure under the
// remaining budget after the dispatch deadline rejects.
export const HANDOFF_DEADLINE_MS = 75_000;

/**
 * Production Reasoning Engine resource name. Set via `--update-env-vars`
 * in the deploy workflow once Phase 8's staging deploy lands. Format:
 *   projects/907466498524/locations/us-central1/reasoningEngines/{ID}
 *
 * Returning the literal here would couple the code to a not-yet-existing
 * resource; the env var keeps deploy-time configuration explicit.
 */
function getResource() {
	const r = process.env.GEAR_REASONING_ENGINE_RESOURCE;
	if (!r) {
		throw new Error('GEAR_REASONING_ENGINE_RESOURCE env var not set');
	}
	return r;
}

let _auth = null;
async function _getToken() {
	if (_auth === null) {
		_auth = new GoogleAuth({
			scopes: ['https://www.googleapis.com/auth/cloud-platform']
		});
	}
	const client = await _auth.getClient();
	const { token } = await client.getAccessToken();
	if (!token) throw new Error('failed to obtain access token');
	return token;
}

/**
 * Read the first non-empty NDJSON line from the streamQuery body. Vertex
 * AI returns newline-delimited JSON even with `?alt=sse` (verified in
 * R2.7) — standard SSE clients see zero events.
 */
export async function _readFirstNdjsonLine(reader) {
	const decoder = new TextDecoder();
	let buffer = '';
	while (true) {
		const { value, done } = await reader.read();
		if (done) {
			throw new Error('streamQuery ended before first NDJSON line');
		}
		buffer += decoder.decode(value, { stream: true });
		// Drain every newline in the current buffer — a single chunk can
		// hold multiple lines and the leading ones may be blank.
		let newlineIdx = buffer.indexOf('\n');
		while (newlineIdx >= 0) {
			const line = buffer.slice(0, newlineIdx).trim();
			buffer = buffer.slice(newlineIdx + 1);
			if (line) return line;
			newlineIdx = buffer.indexOf('\n');
		}
	}
}

async function _doHandoff({
	controller,
	resource,
	sid,
	runId,
	turnIdx,
	userId,
	message,
	isFirstMessage
}) {
	const token = await _getToken();
	const adkSid = `se-${sid}`;
	const headers = {
		Authorization: `Bearer ${token}`,
		'Content-Type': 'application/json'
	};

	// 1. Idempotent createSession on the first turn. Network retries can
	// double-dispatch this — ALREADY_EXISTS treated as success per plan §5.3.
	if (isFirstMessage) {
		const r = await fetch(`${VERTEX_BASE}/v1beta1/${resource}/sessions?sessionId=${adkSid}`, {
			method: 'POST',
			signal: controller.signal,
			headers,
			body: JSON.stringify({
				userId,
				sessionState: { runId, turnIdx, attempt: 1 }
			})
		});
		if (!r.ok) {
			const body = await r.text().catch(() => '');
			// Narrow to status === 409 + body match — pre-fix any 4xx whose
			// body happened to contain the substring "ALREADY_EXISTS" was
			// silently treated as success (theoretical: a 429 quota error
			// mentioning the phrase). Now only the actual conflict response
			// is the success path.
			if (r.status !== 409 || !body.includes('ALREADY_EXISTS')) {
				throw new Error(`createSession_failed:${r.status}:${body.slice(0, 200)}`);
			}
		}
	}

	// 2. appendEvent — verified payload shape from R3.1.
	const ar = await fetch(`${VERTEX_BASE}/v1beta1/${resource}/sessions/${adkSid}:appendEvent`, {
		method: 'POST',
		signal: controller.signal,
		headers,
		body: JSON.stringify({
			author: 'system',
			invocationId: `agentstream-${runId}`,
			timestamp: new Date().toISOString(),
			actions: { stateDelta: { runId, turnIdx, attempt: 1 } }
		})
	});
	if (!ar.ok) {
		const body = await ar.text().catch(() => '');
		throw new Error(`appendEvent_failed:${ar.status}:${body.slice(0, 200)}`);
	}

	// 3. streamQuery + first-NDJSON-line read + clean abort. Mirrors the
	// R3.2 gate variant pattern verified durable for ≥240 s post-disconnect.
	const sqRes = await fetch(`${VERTEX_BASE}/v1/${resource}:streamQuery?alt=sse`, {
		method: 'POST',
		signal: controller.signal,
		headers,
		body: JSON.stringify({
			class_method: 'async_stream_query',
			input: { user_id: userId, session_id: adkSid, message }
		})
	});
	if (!sqRes.ok) {
		const body = await sqRes.text().catch(() => '');
		throw new Error(`streamQuery_not_ok:${sqRes.status}:${body.slice(0, 200)}`);
	}

	const reader = sqRes.body.getReader();
	try {
		await _readFirstNdjsonLine(reader);
	} finally {
		// reader.cancel() releases the body; controller.abort() in the
		// outer finally also tears down the underlying fetch as a clean
		// double-disconnect (verified pattern from R3.2).
		await reader.cancel().catch(() => {});
	}
	return { ok: true };
}

/**
 * Run the handoff sequence under a strict deadline with one shared
 * AbortController. Returns `{ ok: true }` on success. Throws on any
 * failure shape — caller must call `gearHandoffCleanup` to flip the
 * session+turn to status='error'.
 *
 * `deadlineMs` defaults to `HANDOFF_DEADLINE_MS` (75 s) for production
 * use. Tests override to a small value to exercise the deadline-fires-
 * abort path without real wall-clock waits.
 */
export async function gearHandoff({
	sid,
	runId,
	turnIdx,
	userId,
	message,
	isFirstMessage,
	deadlineMs = HANDOFF_DEADLINE_MS
}) {
	const resource = getResource();
	const controller = new AbortController();
	// Single deadline timer that both aborts the in-flight fetches AND
	// rejects the race promise. Two parallel timers (one for abort, one
	// for the reject) would race against each other: in-flight fetches
	// notice the abort and reject _doHandoff with AbortError on a
	// microtask, which can settle the Promise.race BEFORE the rejection
	// timer fires. Caller would see AbortError instead of the intended
	// `gearHandoff_deadline_exceeded` message. Collapsing to one timer
	// makes the synchronous reject() settle the race deterministically.
	let deadlineTimer;
	const deadlinePromise = new Promise((_resolve, reject) => {
		deadlineTimer = setTimeout(() => {
			controller.abort();
			reject(new Error(`gearHandoff_deadline_exceeded:${deadlineMs}ms`));
		}, deadlineMs);
	});
	try {
		return await Promise.race([
			_doHandoff({
				controller,
				resource,
				sid,
				runId,
				turnIdx,
				userId,
				message,
				isFirstMessage
			}),
			deadlinePromise
		]);
	} finally {
		clearTimeout(deadlineTimer);
		// Suppress "unhandled rejection" warning when _doHandoff wins the
		// race — we don't await the deadline branch so its rejection has
		// no listener.
		deadlinePromise.catch(() => {});
		// Idempotent — ensures any straggler fetch that survived the race
		// also gets cancelled.
		controller.abort();
	}
}

/**
 * Flip session+turn to status='error' atomically inside a transaction
 * that fences on `currentRunId`. No-ops if the run has moved on or the
 * terminal state has already been written (race-safe). Mirrors
 * `watchdog.js:172-186` and `worker_main.py:1349`.
 */
export async function gearHandoffCleanup(db, sid, runId, turnIdx, errorReason) {
	const sessionRef = db.collection('sessions').doc(sid);
	const turnKey = String(turnIdx).padStart(4, '0');
	const turnRef = sessionRef.collection('turns').doc(turnKey);
	await db.runTransaction(async (tx) => {
		const snap = await tx.get(sessionRef);
		if (!snap.exists) return;
		const data = snap.data();
		if (data.currentRunId !== runId) return; // newer turn moved on
		if (data.status === 'complete' || data.status === 'error') return; // race: terminal already written
		tx.update(sessionRef, {
			status: 'error',
			error: errorReason,
			updatedAt: FieldValue.serverTimestamp()
		});
		tx.update(turnRef, { status: 'error', error: errorReason });
	});
}
