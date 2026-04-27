import { describe, it, mock, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

// ── Mock google-auth-library before importing gear-handoff.js ──

const _getAccessToken = mock.fn(async () => ({ token: 'fake-token' }));
const _getClient = mock.fn(async () => ({ getAccessToken: _getAccessToken }));

mock.module('google-auth-library', {
	namedExports: {
		GoogleAuth: class {
			getClient = _getClient;
		}
	}
});

// firebase-admin/firestore — only `FieldValue` is used by gear-handoff.js.
const FieldValueMock = {
	serverTimestamp: () => '__server_timestamp__'
};
mock.module('firebase-admin/firestore', {
	namedExports: {
		FieldValue: FieldValueMock
	}
});

process.env.GEAR_REASONING_ENGINE_RESOURCE =
	'projects/907466498524/locations/us-central1/reasoningEngines/test-id';

const { gearHandoff, gearHandoffCleanup, _readFirstNdjsonLine, HANDOFF_DEADLINE_MS } =
	await import('./gear-handoff.js');

// ── Helpers ────────────────────────────────────────────────────────────────

/**
 * Build a Response-like object whose body.getReader() yields the supplied
 * NDJSON chunks line-by-line. `aborts` collects calls to reader.cancel()
 * so tests can assert clean disconnect.
 */
function mockSqResponse({
	chunks = ['{"ok":true}\n'],
	status = 200,
	statusText = 'OK',
	signal,
	cancelLog
}) {
	let i = 0;
	const reader = {
		read: mock.fn(async () => {
			if (signal?.aborted) {
				const err = new Error('aborted');
				err.name = 'AbortError';
				throw err;
			}
			if (i >= chunks.length) return { value: undefined, done: true };
			const chunk = chunks[i++];
			return { value: new TextEncoder().encode(chunk), done: false };
		}),
		cancel: mock.fn(async () => {
			cancelLog?.push('cancel');
		})
	};
	return {
		ok: status === 200,
		status,
		statusText,
		text: async () => '',
		body: {
			getReader: () => reader
		},
		_reader: reader
	};
}

/**
 * Build a JSON Response for createSession / appendEvent (no body needed
 * to flow through to a reader).
 */
function mockJsonResponse({ status = 200, body = '{}' } = {}) {
	return {
		ok: status >= 200 && status < 300,
		status,
		text: async () => body
	};
}

let originalFetch;
beforeEach(() => {
	originalFetch = globalThis.fetch;
});
afterEach(() => {
	globalThis.fetch = originalFetch;
});

// ── _readFirstNdjsonLine ───────────────────────────────────────────────────

describe('_readFirstNdjsonLine', () => {
	it('returns the first non-empty line and stops reading', async () => {
		let calls = 0;
		const reader = {
			read: async () => {
				calls++;
				if (calls === 1) return { value: new TextEncoder().encode('{"a":1}\n'), done: false };
				throw new Error('should not read past first newline');
			},
			cancel: async () => {}
		};
		const line = await _readFirstNdjsonLine(reader);
		assert.equal(line, '{"a":1}');
	});

	it('skips empty lines and returns the next non-empty', async () => {
		const reader = {
			read: (() => {
				let i = 0;
				const chunks = ['\n\n', '{"a":2}\n'];
				return async () => {
					if (i >= chunks.length) return { value: undefined, done: true };
					return { value: new TextEncoder().encode(chunks[i++]), done: false };
				};
			})(),
			cancel: async () => {}
		};
		const line = await _readFirstNdjsonLine(reader);
		assert.equal(line, '{"a":2}');
	});

	it('throws if stream closes before a newline appears', async () => {
		const reader = {
			read: (() => {
				let done = false;
				return async () => {
					if (done) return { value: undefined, done: true };
					done = true;
					return { value: new TextEncoder().encode('partial-no-newline'), done: false };
				};
			})(),
			cancel: async () => {}
		};
		await assert.rejects(_readFirstNdjsonLine(reader), /streamQuery ended before/);
	});
});

// ── gearHandoff happy path ─────────────────────────────────────────────────

describe('gearHandoff', () => {
	function setupFetch({ createStatus = 200, appendStatus = 200, sqStatus = 200, sqChunks }) {
		const cancelLog = [];
		const fetchMock = mock.fn(async (url, init) => {
			if (url.includes(':streamQuery')) {
				return mockSqResponse({
					chunks: sqChunks ?? ['{"first":"line"}\n'],
					status: sqStatus,
					signal: init?.signal,
					cancelLog
				});
			}
			if (url.includes(':appendEvent')) {
				return mockJsonResponse({ status: appendStatus });
			}
			if (url.includes('/sessions?sessionId=')) {
				return mockJsonResponse({ status: createStatus });
			}
			throw new Error(`unexpected fetch url: ${url}`);
		});
		globalThis.fetch = fetchMock;
		return { fetchMock, cancelLog };
	}

	it('first turn: createSession + appendEvent + streamQuery + clean disconnect', async () => {
		const { fetchMock, cancelLog } = setupFetch({});
		const out = await gearHandoff({
			sid: 'sid1',
			runId: 'run1',
			turnIdx: 1,
			userId: 'user1',
			message: 'hello',
			isFirstMessage: true
		});
		assert.deepEqual(out, { ok: true });

		// Three fetches in order: createSession, appendEvent, streamQuery
		const urls = fetchMock.mock.calls.map((c) => c.arguments[0]);
		assert.equal(urls.length, 3);
		assert.match(urls[0], /\/sessions\?sessionId=se-sid1$/);
		assert.match(urls[1], /:appendEvent$/);
		assert.match(urls[2], /:streamQuery\?alt=sse$/);

		// Reader was cancelled (clean disconnect after first NDJSON line)
		assert.deepEqual(cancelLog, ['cancel']);

		// All three fetches share the same AbortSignal
		const signals = fetchMock.mock.calls.map((c) => c.arguments[1]?.signal);
		assert.ok(signals[0] === signals[1] && signals[1] === signals[2]);
	});

	it('follow-up turn: skips createSession (only appendEvent + streamQuery)', async () => {
		const { fetchMock, cancelLog } = setupFetch({});
		await gearHandoff({
			sid: 'sid1',
			runId: 'run2',
			turnIdx: 2,
			userId: 'user1',
			message: 'follow-up',
			isFirstMessage: false
		});
		const urls = fetchMock.mock.calls.map((c) => c.arguments[0]);
		assert.equal(urls.length, 2);
		assert.match(urls[0], /:appendEvent$/);
		assert.match(urls[1], /:streamQuery\?alt=sse$/);
		assert.deepEqual(cancelLog, ['cancel']);
	});

	it('createSession ALREADY_EXISTS → continues to appendEvent', async () => {
		const fetchMock = mock.fn(async (url) => {
			if (url.includes('/sessions?sessionId=')) {
				return {
					ok: false,
					status: 409,
					text: async () => '{"error":{"status":"ALREADY_EXISTS"}}'
				};
			}
			if (url.includes(':appendEvent')) return mockJsonResponse({});
			if (url.includes(':streamQuery')) return mockSqResponse({});
			throw new Error('unexpected');
		});
		globalThis.fetch = fetchMock;

		const out = await gearHandoff({
			sid: 'sid1',
			runId: 'run1',
			turnIdx: 1,
			userId: 'user1',
			message: 'hello',
			isFirstMessage: true
		});
		assert.deepEqual(out, { ok: true });
		assert.equal(fetchMock.mock.callCount(), 3);
	});

	it('createSession 4xx (not ALREADY_EXISTS) → throws createSession_failed', async () => {
		const fetchMock = mock.fn(async (url) => {
			if (url.includes('/sessions?sessionId=')) {
				return { ok: false, status: 400, text: async () => 'bad request' };
			}
			throw new Error(`should not reach: ${url}`);
		});
		globalThis.fetch = fetchMock;
		await assert.rejects(
			gearHandoff({
				sid: 'sid1',
				runId: 'run1',
				turnIdx: 1,
				userId: 'user1',
				message: 'hello',
				isFirstMessage: true
			}),
			/createSession_failed:400/
		);
	});

	it('appendEvent 4xx → throws appendEvent_failed', async () => {
		const fetchMock = mock.fn(async (url) => {
			if (url.includes('/sessions?sessionId=')) return mockJsonResponse({});
			if (url.includes(':appendEvent'))
				return { ok: false, status: 400, text: async () => 'invalid' };
			throw new Error(`should not reach: ${url}`);
		});
		globalThis.fetch = fetchMock;
		await assert.rejects(
			gearHandoff({
				sid: 'sid1',
				runId: 'run1',
				turnIdx: 1,
				userId: 'user1',
				message: 'hello',
				isFirstMessage: true
			}),
			/appendEvent_failed:400/
		);
	});

	it('streamQuery 502 → throws streamQuery_not_ok', async () => {
		const fetchMock = mock.fn(async (url) => {
			if (url.includes('/sessions?sessionId=')) return mockJsonResponse({});
			if (url.includes(':appendEvent')) return mockJsonResponse({});
			if (url.includes(':streamQuery'))
				return { ok: false, status: 502, text: async () => 'gateway' };
			throw new Error('unexpected');
		});
		globalThis.fetch = fetchMock;
		await assert.rejects(
			gearHandoff({
				sid: 'sid1',
				runId: 'run1',
				turnIdx: 1,
				userId: 'user1',
				message: 'hello',
				isFirstMessage: true
			}),
			/streamQuery_not_ok:502/
		);
	});

	it('shared AbortController is reused across all three fetches', async () => {
		// plan §"App-level timeout for gearHandoff cleanup, with shared
		// AbortController" — a single controller hoisted to gearHandoff
		// scope means that aborting on deadline cancels every in-flight
		// fetch (createSession, appendEvent, streamQuery) together,
		// rather than only the streamQuery. Verified here by asserting
		// signal identity across all three calls. Stuck-stream + 75 s
		// deadline timeout would also exercise this path but is too
		// slow for unit-test budget.
		const { fetchMock } = setupFetch({});
		await gearHandoff({
			sid: 'sid1',
			runId: 'run1',
			turnIdx: 1,
			userId: 'user1',
			message: 'hi',
			isFirstMessage: true
		});
		const signals = fetchMock.mock.calls.map((c) => c.arguments[1]?.signal);
		assert.equal(signals.length, 3);
		assert.ok(signals[0] && signals[0] === signals[1] && signals[1] === signals[2]);
		assert.equal(typeof HANDOFF_DEADLINE_MS, 'number');
		assert.ok(HANDOFF_DEADLINE_MS > 0);
	});

	it('deadline fires abort across all three fetches and rejects deterministically', async () => {
		// plan §"Cross-cutting" + F2 P1 — the deadline must abort the shared
		// controller AND reject the race promise. Pre-fix, two parallel
		// timers raced: the abort fired first and the in-flight fetch
		// rejected _doHandoff with AbortError on a microtask, settling the
		// race BEFORE the rejection-timer fired. Caller saw AbortError
		// instead of `gearHandoff_deadline_exceeded`. Post-fix, one timer
		// aborts AND rejects synchronously, so the message is deterministic.
		const captured = [];
		const fetchMock = mock.fn(async (url, init) => {
			captured.push(init.signal);
			if (url.includes('/sessions?sessionId=')) return mockJsonResponse({});
			if (url.includes(':appendEvent')) return mockJsonResponse({});
			if (url.includes(':streamQuery')) {
				// Stream that hangs on read until the signal aborts.
				const reader = {
					read: () =>
						new Promise((_resolve, reject) => {
							init.signal.addEventListener('abort', () => {
								const err = new Error('aborted');
								err.name = 'AbortError';
								reject(err);
							});
						}),
					cancel: async () => {}
				};
				return { ok: true, status: 200, body: { getReader: () => reader } };
			}
			throw new Error(`unexpected: ${url}`);
		});
		globalThis.fetch = fetchMock;

		await assert.rejects(
			gearHandoff({
				sid: 'sid1',
				runId: 'run1',
				turnIdx: 1,
				userId: 'user1',
				message: 'stuck',
				isFirstMessage: true,
				deadlineMs: 100
			}),
			/gearHandoff_deadline_exceeded:100ms/
		);

		// All three fetches saw the same signal, and it ended aborted.
		assert.equal(captured.length, 3);
		assert.ok(captured[0] === captured[1] && captured[1] === captured[2]);
		assert.equal(captured[0].aborted, true);
	});

	it('falls back to the hardcoded prod resource when GEAR_REASONING_ENGINE_RESOURCE is unset', async () => {
		// Belt-and-suspenders against a deploy that ships with an empty
		// .env (the 2026-04-27 GHA-strip incident). Without this default,
		// agentStream would 502 every gear request whenever the workflow
		// dropped the env var.
		const saved = process.env.GEAR_REASONING_ENGINE_RESOURCE;
		delete process.env.GEAR_REASONING_ENGINE_RESOURCE;
		const captured = [];
		const fetchMock = mock.fn(async (url) => {
			captured.push(url);
			return new Response('{}', { status: 401 });
		});
		globalThis.fetch = fetchMock;
		try {
			// Resource resolved from default → handoff reaches `:createSession`
			// using the default URL → mock returns 401 → throws createSession_failed.
			// The throw means we got past `getResource()` (no env var thrown);
			// the captured URL proves the default resource was used.
			await assert.rejects(
				gearHandoff({
					sid: 'sid1',
					runId: 'run1',
					turnIdx: 1,
					userId: 'user1',
					message: 'hi',
					isFirstMessage: true
				}),
				/createSession_failed/
			);
			assert.ok(
				captured.length > 0 && String(captured[0]).includes('reasoningEngines/1179666575196684288'),
				`expected fetch URL to include the default resource ID; got ${JSON.stringify(captured)}`
			);
		} finally {
			process.env.GEAR_REASONING_ENGINE_RESOURCE = saved;
		}
	});
});

// ── gearHandoffCleanup ─────────────────────────────────────────────────────

describe('gearHandoffCleanup', () => {
	function makeMockDb({ sessionData, sessionExists = true }) {
		const sessionUpdates = [];
		const turnUpdates = [];
		const sessionRef = {
			_kind: 'session',
			update: () => {},
			collection: () => ({ doc: () => turnRef })
		};
		const turnRef = { _kind: 'turn', update: () => {} };
		const tx = {
			get: async () => ({
				exists: sessionExists,
				data: () => sessionData
			}),
			update: (ref, data) => {
				if (ref._kind === 'session') sessionUpdates.push(data);
				if (ref._kind === 'turn') turnUpdates.push(data);
			}
		};
		const db = {
			collection: () => ({ doc: () => sessionRef }),
			runTransaction: async (cb) => cb(tx)
		};
		return { db, sessionUpdates, turnUpdates };
	}

	it('writes status=error on session+turn when run_id matches and not terminal', async () => {
		const { db, sessionUpdates, turnUpdates } = makeMockDb({
			sessionData: { currentRunId: 'r1', status: 'queued' }
		});
		await gearHandoffCleanup(db, 'sid1', 'r1', 1, 'gear_handoff_failed:test');
		assert.equal(sessionUpdates.length, 1);
		assert.equal(turnUpdates.length, 1);
		assert.equal(sessionUpdates[0].status, 'error');
		assert.equal(sessionUpdates[0].error, 'gear_handoff_failed:test');
		assert.equal(turnUpdates[0].status, 'error');
	});

	it('no-op when currentRunId mismatches (newer turn moved on)', async () => {
		const { db, sessionUpdates, turnUpdates } = makeMockDb({
			sessionData: { currentRunId: 'r2', status: 'queued' }
		});
		await gearHandoffCleanup(db, 'sid1', 'r1', 1, 'reason');
		assert.equal(sessionUpdates.length, 0);
		assert.equal(turnUpdates.length, 0);
	});

	it('no-op when status is already terminal=complete (race: terminal already written)', async () => {
		const { db, sessionUpdates, turnUpdates } = makeMockDb({
			sessionData: { currentRunId: 'r1', status: 'complete' }
		});
		await gearHandoffCleanup(db, 'sid1', 'r1', 1, 'reason');
		assert.equal(sessionUpdates.length, 0);
		assert.equal(turnUpdates.length, 0);
	});

	it('no-op when status is already terminal=error', async () => {
		const { db, sessionUpdates, turnUpdates } = makeMockDb({
			sessionData: { currentRunId: 'r1', status: 'error' }
		});
		await gearHandoffCleanup(db, 'sid1', 'r1', 1, 'reason');
		assert.equal(sessionUpdates.length, 0);
		assert.equal(turnUpdates.length, 0);
	});

	it('no-op when session doc does not exist', async () => {
		const { db, sessionUpdates, turnUpdates } = makeMockDb({
			sessionData: null,
			sessionExists: false
		});
		await gearHandoffCleanup(db, 'sid1', 'r1', 1, 'reason');
		assert.equal(sessionUpdates.length, 0);
		assert.equal(turnUpdates.length, 0);
	});
});
