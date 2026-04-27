import { describe, it, mock, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

// ── Mock external modules before importing index.js ──

// Firestore mock — refs carry a `_path` so assertions can distinguish session
// writes (`sessions/{sid}`) from turn writes (`sessions/{sid}/turns/{turnKey}`).
// The txn object exposes the same get/set/update surface as the real txn,
// but without isolation semantics (tests drive sequences manually).
function makeRef(path) {
	const ref = {
		_path: path,
		collection: (name) => ({
			doc: (id) => makeRef(`${path}/${name}/${id}`)
		}),
		// Direct reads/writes outside a transaction (e.g., agentDelete's session
		// pre-read, enqueue-failure status flip) delegate to the same spies used
		// inside transactions, so assertions see every mutation regardless of
		// execution path.
		get: () => mockDb.get(ref),
		update: (data) => mockDb.update(ref, data),
		set: (data) => mockDb.set(ref, data)
	};
	return ref;
}

// Named after the signature (ref, …) so test assertions can introspect which
// path a mutation hit.
const mockDb = {
	collection: (name) => ({
		doc: (id) => makeRef(`${name}/${id}`)
	}),
	get: mock.fn(async () => ({ exists: false })),
	set: mock.fn(async () => {}),
	update: mock.fn(async () => {}),
	recursiveDelete: mock.fn(async () => {}),
	runTransaction: mock.fn(async (cb) => {
		const txn = {
			get: async (ref) => mockDb.get(ref),
			set: (ref, data) => mockDb.set(ref, data),
			update: (ref, data) => mockDb.update(ref, data)
		};
		return cb(txn);
	})
};

// Cloud Tasks mock — captures the last createTask call for assertions.
const tasksClient = {
	queuePath: (project, location, queue) =>
		`projects/${project}/locations/${location}/queues/${queue}`,
	createTask: mock.fn(async (opts) => [opts.task])
};

// Firebase Auth mock — verifyIdToken returns { uid: 'user-<token>' } so tests
// can pass different tokens to simulate different users.
const authInstance = {
	verifyIdToken: mock.fn(async (token) => {
		if (token === 'bad-token') throw new Error('invalid token');
		return { uid: `user-${token}` };
	})
};

mock.module('firebase-admin/app', {
	namedExports: { initializeApp: mock.fn() }
});
mock.module('firebase-admin/firestore', {
	namedExports: {
		getFirestore: mock.fn(() => mockDb),
		FieldValue: {
			serverTimestamp: () => '__server_timestamp__',
			arrayUnion: (...values) => ({ __arrayUnion: values })
		}
	}
});
mock.module('firebase-admin/auth', {
	namedExports: {
		getAuth: () => authInstance
	}
});
mock.module('firebase-functions/v2/https', {
	namedExports: {
		onRequest: (_opts, handler) => handler
	}
});
mock.module('firebase-functions/params', {
	namedExports: {
		defineSecret: (name) => ({
			value: () =>
				name === 'RELAY_KEY' ? 'test-relay-key' : name === 'ELEVENLABS_API_KEY' ? 'test-el-key' : ''
		})
	}
});
// `@google-cloud/vertexai` and `google-auth-library` are no longer imported
// by functions/index.js (Phase 7 cleanup removed the ADK Cloud Run hop and
// title gen moved to the worker). Mocks deleted — `cd functions && npm test`
// would silently accept a re-introduction otherwise.
mock.module('@google-cloud/tasks', {
	namedExports: {
		CloudTasksClient: class {
			queuePath(...args) {
				return tasksClient.queuePath(...args);
			}
			createTask(...args) {
				return tasksClient.createTask(...args);
			}
		}
	}
});

// Mock ./gear-handoff.js BEFORE the index.js import. Putting this inside a
// describe block would be too late — index.js captures the real exports at
// import time. F2 P1 from the post-review plan.
const gearHandoffMock = mock.fn(async () => ({ ok: true }));
const gearHandoffCleanupMock = mock.fn(async () => {});
mock.module('./gear-handoff.js', {
	namedExports: {
		gearHandoff: gearHandoffMock,
		gearHandoffCleanup: gearHandoffCleanupMock
	}
});

// Set WORKER_URL before importing so the Cloud Task target resolves.
process.env.WORKER_URL = 'https://worker-test.run.app';

const {
	intake,
	agentStream,
	agentDelete,
	sttToken,
	tts,
	chooseInitialTransport,
	GEAR_ALLOWLIST,
	resetGearAllowlist
} = await import('./index.js');

// ── Test helpers ──

function mockReq(overrides = {}) {
	return {
		method: 'POST',
		body: {},
		headers: {},
		ip: '127.0.0.1',
		query: {},
		...overrides
	};
}

function mockRes() {
	const res = {
		_status: 200,
		_json: null,
		_headers: {},
		_written: [],
		_ended: false,
		writableEnded: false,
		status(code) {
			res._status = code;
			return res;
		},
		json(data) {
			res._json = data;
		},
		set(key, val) {
			res._headers[key] = val;
		},
		send(data) {
			res._sent = data;
		},
		writeHead(status, headers) {
			res._status = status;
			Object.assign(res._headers, headers);
		},
		write(data) {
			res._written.push(data);
			return true;
		},
		end() {
			res._ended = true;
			res.writableEnded = true;
		},
		on: mock.fn()
	};
	return res;
}

// Save and restore global fetch
let originalFetch;

beforeEach(() => {
	originalFetch = globalThis.fetch;
	mockDb.get.mock.resetCalls();
	mockDb.set.mock.resetCalls();
	mockDb.update.mock.resetCalls();
	mockDb.recursiveDelete.mock.resetCalls();
	mockDb.runTransaction.mock.resetCalls();
	tasksClient.createTask.mock.resetCalls();
	authInstance.verifyIdToken.mock.resetCalls();
	gearHandoffMock.mock.resetCalls();
	gearHandoffCleanupMock.mock.resetCalls();
	mockDb.get.mock.mockImplementation(async () => ({ exists: false }));
	mockDb.recursiveDelete.mock.mockImplementation(async () => {});
	// F2 P3: reset mock IMPLEMENTATIONS too — a failed/interrupted
	// `mockImplementationOnce` from a prior test could otherwise leak.
	gearHandoffMock.mock.mockImplementation(async () => ({ ok: true }));
	gearHandoffCleanupMock.mock.mockImplementation(async () => {});
	resetGearAllowlist();
});

afterEach(() => {
	globalThis.fetch = originalFetch;
});

// ══════════════════════════════════════════════════════
// intake
// ══════════════════════════════════════════════════════

describe('intake', () => {
	it('rejects non-POST with 405', async () => {
		const res = mockRes();
		await intake(mockReq({ method: 'GET' }), res);
		assert.equal(res._status, 405);
		assert.equal(res._json.ok, false);
	});

	it('sends email and returns ok on success', async () => {
		const calls = [];
		globalThis.fetch = mock.fn(async (url) => {
			calls.push(url);
			return { ok: true, status: 200 };
		});

		const res = mockRes();
		await intake(
			mockReq({
				body: {
					type: 'Restaurant',
					country: 'DE',
					businessName: 'Test Bistro',
					fullName: 'John Doe',
					email: 'john@example.com'
				}
			}),
			res
		);
		assert.equal(res._json.ok, true);
		// Should call Resend twice (notification + confirmation)
		assert.equal(globalThis.fetch.mock.callCount(), 2);
		assert.ok(calls[0].includes('resend.com'));
		assert.ok(calls[1].includes('resend.com'));
	});

	it('returns 502 when Resend fails', async () => {
		globalThis.fetch = mock.fn(async () => ({
			ok: false,
			status: 401,
			text: async () => 'Unauthorized'
		}));

		const res = mockRes();
		await intake(
			mockReq({
				body: {
					type: 'Restaurant',
					businessName: 'Test',
					fullName: 'A',
					email: 'a@b.com'
				}
			}),
			res
		);
		assert.equal(res._status, 502);
		assert.equal(res._json.ok, false);
		assert.match(res._json.error, /key invalid/i);
	});

	it('returns 503 when fetch throws', async () => {
		globalThis.fetch = mock.fn(async () => {
			throw new Error('Network error');
		});

		const res = mockRes();
		await intake(
			mockReq({
				body: {
					type: 'Restaurant',
					businessName: 'Test',
					fullName: 'A',
					email: 'a@b.com'
				}
			}),
			res
		);
		assert.equal(res._status, 503);
		assert.equal(res._json.ok, false);
	});
});

// ══════════════════════════════════════════════════════
// sttToken
// ══════════════════════════════════════════════════════

describe('sttToken', () => {
	it('rejects non-POST with 405', async () => {
		const res = mockRes();
		await sttToken(mockReq({ method: 'GET' }), res);
		assert.equal(res._status, 405);
	});

	it('returns token on success', async () => {
		globalThis.fetch = mock.fn(async () => ({
			ok: true,
			json: async () => ({ token: 'el-token-123' })
		}));

		const res = mockRes();
		await sttToken(mockReq(), res);
		assert.equal(res._json.ok, true);
		assert.equal(res._json.token, 'el-token-123');
	});

	it('returns 502 on upstream failure', async () => {
		globalThis.fetch = mock.fn(async () => ({
			ok: false,
			status: 500,
			text: async () => 'Internal error'
		}));

		const res = mockRes();
		await sttToken(mockReq(), res);
		assert.equal(res._status, 502);
		assert.equal(res._json.ok, false);
	});

	it('returns 503 when fetch throws', async () => {
		globalThis.fetch = mock.fn(async () => {
			throw new Error('Network error');
		});

		const res = mockRes();
		await sttToken(mockReq(), res);
		assert.equal(res._status, 503);
	});
});

// ══════════════════════════════════════════════════════
// tts
// ══════════════════════════════════════════════════════

describe('tts', () => {
	it('rejects non-POST with 405', async () => {
		const res = mockRes();
		await tts(mockReq({ method: 'GET' }), res);
		assert.equal(res._status, 405);
	});

	it('returns 400 when text is missing', async () => {
		const res = mockRes();
		await tts(mockReq({ body: {} }), res);
		assert.equal(res._status, 400);
		assert.match(res._json.error, /text is required/i);
	});

	it('returns 400 when text exceeds 5000 chars', async () => {
		const res = mockRes();
		await tts(mockReq({ body: { text: 'a'.repeat(6000) } }), res);
		assert.equal(res._status, 400);
		assert.match(res._json.error, /too long/i);
	});

	it('returns audio buffer on success', async () => {
		const audioData = new Uint8Array([0xff, 0xfb, 0x90, 0x00]).buffer;
		globalThis.fetch = mock.fn(async () => ({
			ok: true,
			arrayBuffer: async () => audioData
		}));

		const res = mockRes();
		await tts(mockReq({ body: { text: 'Hello world' } }), res);
		assert.equal(res._headers['Content-Type'], 'audio/mpeg');
		assert.ok(Buffer.isBuffer(res._sent));
	});

	it('returns 502 on upstream failure', async () => {
		globalThis.fetch = mock.fn(async () => ({
			ok: false,
			status: 500,
			text: async () => 'error'
		}));

		const res = mockRes();
		await tts(mockReq({ body: { text: 'Hello' } }), res);
		assert.equal(res._status, 502);
	});
});

// ══════════════════════════════════════════════════════
// agentStream
// ══════════════════════════════════════════════════════

describe('agentStream', () => {
	function authedReq(overrides = {}) {
		const headers = { authorization: 'Bearer good-token', ...(overrides.headers || {}) };
		return mockReq({
			body: { message: 'What is the menu like?', sessionId: 'sess-1' },
			...overrides,
			headers
		});
	}

	// Returns `set` / `update` calls partitioned by the ref path the handler
	// hit inside the transaction. Tests want to assert separately on the
	// session doc vs. the turn doc, so this helper isolates the noise.
	function partitionWrites(sessionPath) {
		const sessionSets = mockDb.set.mock.calls
			.filter((c) => c.arguments[0]?._path === sessionPath)
			.map((c) => c.arguments[1]);
		const sessionUpdates = mockDb.update.mock.calls
			.filter((c) => c.arguments[0]?._path === sessionPath)
			.map((c) => c.arguments[1]);
		const turnSets = mockDb.set.mock.calls
			.filter((c) => c.arguments[0]?._path?.startsWith(`${sessionPath}/turns/`))
			.map((c) => ({ path: c.arguments[0]._path, data: c.arguments[1] }));
		return { sessionSets, sessionUpdates, turnSets };
	}

	function decodeTaskBody(taskCall) {
		return JSON.parse(
			Buffer.from(taskCall.arguments[0].task.httpRequest.body, 'base64').toString('utf8')
		);
	}

	it('rejects non-POST with 405', async () => {
		const res = mockRes();
		await agentStream(mockReq({ method: 'GET' }), res);
		assert.equal(res._status, 405);
	});

	it('returns 401 when Authorization header is missing', async () => {
		const res = mockRes();
		await agentStream(mockReq({ body: { message: 'hi', sessionId: 's' } }), res);
		assert.equal(res._status, 401);
	});

	it('returns 401 when token verification fails', async () => {
		const res = mockRes();
		await agentStream(authedReq({ headers: { authorization: 'Bearer bad-token' } }), res);
		assert.equal(res._status, 401);
	});

	it('returns 400 when message or sessionId missing', async () => {
		const res = mockRes();
		await agentStream(authedReq({ body: { sessionId: 'sess-1' } }), res);
		assert.equal(res._status, 400);
	});

	it('first turn creates session + turns/0001 in one transaction', async () => {
		mockDb.get.mock.mockImplementation(async () => ({ exists: false }));
		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 202);
		assert.equal(res._json.ok, true);
		assert.equal(res._json.sessionId, 'sess-1');
		assert.match(res._json.runId, /^[0-9a-f-]{36}$/);

		// Exactly one transaction.
		assert.equal(mockDb.runTransaction.mock.callCount(), 1);

		const { sessionSets, sessionUpdates, turnSets } = partitionWrites('sessions/sess-1');

		// First turn: set session (no update), set turn 0001.
		assert.equal(sessionUpdates.length, 0);
		assert.equal(sessionSets.length, 1);
		const sessionDoc = sessionSets[0];
		assert.equal(sessionDoc.userId, 'user-good-token');
		assert.deepEqual(sessionDoc.participants, ['user-good-token']);
		assert.equal(sessionDoc.lastTurnIndex, 1);
		assert.equal(sessionDoc.status, 'queued');
		assert.equal(sessionDoc.title, null);
		assert.equal(sessionDoc.adkSessionId, null);
		assert.equal(sessionDoc.updatedAt, '__server_timestamp__');
		assert.equal(sessionDoc.queuedAt, '__server_timestamp__');
		assert.equal(sessionDoc.createdAt, '__server_timestamp__');
		// Terminal content fields must NOT be on the session doc anymore.
		assert.ok(!('reply' in sessionDoc));
		assert.ok(!('sources' in sessionDoc));
		assert.ok(!('turnSummary' in sessionDoc));
		// expiresAt removed entirely from the session schema.
		assert.ok(!('expiresAt' in sessionDoc));

		// Turn 0001 doc.
		assert.equal(turnSets.length, 1);
		assert.equal(turnSets[0].path, 'sessions/sess-1/turns/0001');
		const turnDoc = turnSets[0].data;
		assert.equal(turnDoc.turnIndex, 1);
		assert.equal(turnDoc.runId, res._json.runId);
		assert.equal(turnDoc.userMessage, 'What is the menu like?');
		assert.equal(turnDoc.status, 'pending');
		assert.equal(turnDoc.reply, null);
		assert.equal(turnDoc.sources, null);
		assert.equal(turnDoc.turnSummary, null);
		assert.equal(turnDoc.completedAt, null);
		assert.equal(turnDoc.error, null);
		assert.equal(turnDoc.createdAt, '__server_timestamp__');

		// Cloud Task body.
		assert.equal(tasksClient.createTask.mock.callCount(), 1);
		const taskArg = tasksClient.createTask.mock.calls[0].arguments[0];
		assert.equal(
			taskArg.parent,
			'projects/superextra-site/locations/us-central1/queues/agent-dispatch'
		);
		assert.ok(taskArg.task.name.endsWith(`/tasks/${res._json.runId}`));
		assert.equal(taskArg.task.dispatchDeadline.seconds, 1800);
		assert.equal(taskArg.task.httpRequest.url, 'https://worker-test.run.app/run');
		assert.equal(
			taskArg.task.httpRequest.oidcToken.serviceAccountEmail,
			'superextra-worker@superextra-site.iam.gserviceaccount.com'
		);
		assert.equal(taskArg.task.httpRequest.oidcToken.audience, 'https://worker-test.run.app');

		const body = decodeTaskBody(tasksClient.createTask.mock.calls[0]);
		assert.equal(body.sessionId, 'sess-1');
		assert.equal(body.runId, res._json.runId);
		// Creator UID equals submitter UID on the first turn.
		assert.equal(body.userId, 'user-good-token');
		// turnIdx travels as an integer, not a zero-padded string.
		assert.equal(body.turnIdx, 1);
		assert.equal(typeof body.turnIdx, 'number');
		assert.equal(body.isFirstMessage, true);
		assert.equal(body.adkSessionId, null);
		assert.match(body.queryText, /^\[Date: /);
	});

	it('follow-up from the same user arrayUnion-keeps participants and increments lastTurnIndex', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				participants: ['user-good-token'],
				status: 'complete',
				adkSessionId: 'adk-existing',
				lastTurnIndex: 1,
				placeContext: { name: 'Umami', secondary: 'Berlin', placeId: 'ChIJ...' },
				title: 'Prior chat'
			})
		}));

		const res = mockRes();
		await agentStream(authedReq({ body: { message: 'follow-up', sessionId: 'sess-1' } }), res);

		assert.equal(res._status, 202);
		const { sessionSets, sessionUpdates, turnSets } = partitionWrites('sessions/sess-1');

		// Follow-up: update session (no set), set new turn.
		assert.equal(sessionSets.length, 0);
		assert.equal(sessionUpdates.length, 1);
		const sessionUpdate = sessionUpdates[0];
		assert.equal(sessionUpdate.lastTurnIndex, 2);
		assert.equal(sessionUpdate.status, 'queued');
		assert.equal(sessionUpdate.updatedAt, '__server_timestamp__');
		// arrayUnion carries the submitter UID; Firestore dedups duplicates
		// server-side so the resulting array stays [user-good-token].
		assert.deepEqual(sessionUpdate.participants, { __arrayUnion: ['user-good-token'] });
		// userId is not overwritten.
		assert.ok(!('userId' in sessionUpdate));

		assert.equal(turnSets.length, 1);
		assert.equal(turnSets[0].path, 'sessions/sess-1/turns/0002');
		assert.equal(turnSets[0].data.turnIndex, 2);

		// Cloud Task body — creator UID still equals the original creator.
		const body = decodeTaskBody(tasksClient.createTask.mock.calls[0]);
		assert.equal(body.turnIdx, 2);
		assert.equal(body.userId, 'user-good-token');
		assert.equal(body.adkSessionId, 'adk-existing');
		assert.equal(body.isFirstMessage, false);
		// Follow-up must NOT re-inject [Context: ...] — ADK state holds it.
		assert.ok(!body.queryText.includes('[Context:'));
	});

	it('follow-up from a different user (shared URL) preserves creator UID and arrayUnions participants', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-creator-token',
				participants: ['user-creator-token'],
				status: 'complete',
				adkSessionId: 'adk-shared',
				lastTurnIndex: 2
			})
		}));

		const res = mockRes();
		await agentStream(
			authedReq({
				headers: { authorization: 'Bearer visitor-token' },
				body: { message: 'visitor follow-up', sessionId: 'sess-1' }
			}),
			res
		);

		assert.equal(res._status, 202);
		const { sessionUpdates, turnSets } = partitionWrites('sessions/sess-1');

		assert.equal(sessionUpdates.length, 1);
		const sessionUpdate = sessionUpdates[0];
		// session.userId must NOT be overwritten.
		assert.ok(!('userId' in sessionUpdate));
		// arrayUnion adds the visitor UID; Firestore will merge it into the
		// stored [creator, visitor] set server-side.
		assert.deepEqual(sessionUpdate.participants, { __arrayUnion: ['user-visitor-token'] });
		assert.equal(sessionUpdate.lastTurnIndex, 3);

		assert.equal(turnSets.length, 1);
		assert.equal(turnSets[0].path, 'sessions/sess-1/turns/0003');

		// Cloud Task body: userId = original creator, NOT the submitter.
		const body = decodeTaskBody(tasksClient.createTask.mock.calls[0]);
		assert.equal(body.turnIdx, 3);
		assert.equal(body.userId, 'user-creator-token');
		assert.equal(body.adkSessionId, 'adk-shared');
		assert.equal(body.isFirstMessage, false);
	});

	it('returns 409 turn_cap_reached when lastTurnIndex is already 10', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				participants: ['user-good-token'],
				status: 'complete',
				lastTurnIndex: 10
			})
		}));

		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 409);
		assert.equal(res._json.error, 'turn_cap_reached');
		assert.equal(tasksClient.createTask.mock.callCount(), 0);
	});

	it('boundary: lastTurnIndex=9 still admits one more turn and becomes 10', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				participants: ['user-good-token'],
				status: 'complete',
				lastTurnIndex: 9
			})
		}));

		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 202);
		const { sessionUpdates, turnSets } = partitionWrites('sessions/sess-1');
		assert.equal(sessionUpdates[0].lastTurnIndex, 10);
		assert.equal(turnSets[0].path, 'sessions/sess-1/turns/0010');

		const body = decodeTaskBody(tasksClient.createTask.mock.calls[0]);
		assert.equal(body.turnIdx, 10);
	});

	it('bumps updatedAt on enqueue via serverTimestamp (not just on terminal)', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				participants: ['user-good-token'],
				status: 'complete',
				lastTurnIndex: 1
			})
		}));

		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 202);
		const { sessionUpdates } = partitionWrites('sessions/sess-1');
		assert.equal(sessionUpdates[0].updatedAt, '__server_timestamp__');
	});

	it('one-in-flight: returns 409 when existing status=queued', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				status: 'queued',
				currentRunId: 'prior-run',
				lastTurnIndex: 1
			})
		}));

		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 409);
		assert.equal(res._json.error, 'previous_turn_in_flight');
		assert.equal(tasksClient.createTask.mock.callCount(), 0);
	});

	it('one-in-flight: returns 409 when existing status=running', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				status: 'running',
				currentRunId: 'prior-run',
				lastTurnIndex: 1
			})
		}));

		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 409);
		assert.equal(res._json.error, 'previous_turn_in_flight');
		assert.equal(tasksClient.createTask.mock.callCount(), 0);
	});

	it('task dedup name uses runId', async () => {
		mockDb.get.mock.mockImplementation(async () => ({ exists: false }));
		const res = mockRes();
		await agentStream(authedReq(), res);

		const taskArg = tasksClient.createTask.mock.calls[0].arguments[0];
		assert.equal(
			taskArg.task.name,
			`projects/superextra-site/locations/us-central1/queues/agent-dispatch/tasks/${res._json.runId}`
		);
	});

	it('writes status=error if Cloud Tasks enqueue fails', async () => {
		mockDb.get.mock.mockImplementation(async () => ({ exists: false }));
		tasksClient.createTask.mock.mockImplementationOnce(async () => {
			throw new Error('quota exceeded');
		});

		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 502);
		assert.equal(res._json.error, 'enqueue_failed');

		// Post-enqueue recovery: the session doc (and only the session doc)
		// should be flipped to status=error. The txn already ran so its writes
		// are in the set/update history — we want the extra recovery update.
		const recoveryUpdates = mockDb.update.mock.calls
			.filter((c) => c.arguments[0]?._path === 'sessions/sess-1')
			.map((c) => c.arguments[1]);
		const flipped = recoveryUpdates.find((u) => u.status === 'error');
		assert.ok(flipped, 'recovery update with status=error should have run');
		assert.equal(flipped.error, 'enqueue_failed');
	});

	// ── GEAR transport branch (Phase 5+7 + post-review fixes) ──────────────

	it('first turn with submitter in GEAR_ALLOWLIST routes to gearHandoff (no Cloud Task)', async () => {
		mockDb.get.mock.mockImplementation(async () => ({ exists: false }));
		GEAR_ALLOWLIST.add('user-good-token');

		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 202);
		assert.equal(tasksClient.createTask.mock.callCount(), 0);
		assert.equal(gearHandoffMock.mock.callCount(), 1);

		const handoffArgs = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArgs.sid, 'sess-1');
		assert.match(handoffArgs.runId, /^[0-9a-f-]{36}$/);
		assert.equal(handoffArgs.turnIdx, 1);
		assert.equal(handoffArgs.userId, 'user-good-token');
		assert.equal(handoffArgs.isFirstMessage, true);
		assert.match(handoffArgs.message, /^\[Date: /);

		// The session doc set call should record transport='gear' so the
		// session is sticky for follow-ups.
		const { sessionSets } = partitionWrites('sessions/sess-1');
		assert.equal(sessionSets.length, 1);
		assert.equal(sessionSets[0].transport, 'gear');
	});

	it('gearHandoff failure → gearHandoffCleanup called, 502 returned', async () => {
		mockDb.get.mock.mockImplementation(async () => ({ exists: false }));
		GEAR_ALLOWLIST.add('user-good-token');
		gearHandoffMock.mock.mockImplementationOnce(async () => {
			throw new Error('streamQuery_not_ok:502');
		});

		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 502);
		assert.equal(res._json.error, 'handoff_failed');
		assert.equal(gearHandoffCleanupMock.mock.callCount(), 1);
		const cleanupArgs = gearHandoffCleanupMock.mock.calls[0].arguments;
		// (db, sid, runId, turnIdx, errorReason)
		assert.equal(cleanupArgs[1], 'sess-1');
		assert.match(cleanupArgs[2], /^[0-9a-f-]{36}$/);
		assert.equal(cleanupArgs[3], 1);
		assert.match(cleanupArgs[4], /^gear_handoff_failed:streamQuery_not_ok/);
	});

	it('sticky transport: follow-up on existing gear session stays gear (no allowlist needed)', async () => {
		// Submitter is NOT in allowlist; default is 'cloudrun'. The existing
		// session's stored `transport: 'gear'` must override and route to
		// gearHandoff regardless.
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				participants: ['user-good-token'],
				status: 'complete',
				transport: 'gear',
				adkSessionId: 'adk-existing',
				lastTurnIndex: 1,
				placeContext: { name: 'Umami', secondary: 'Berlin', placeId: 'ChIJ...' },
				title: 'Prior chat'
			})
		}));

		const res = mockRes();
		await agentStream(authedReq({ body: { message: 'follow-up', sessionId: 'sess-1' } }), res);

		assert.equal(res._status, 202);
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		assert.equal(tasksClient.createTask.mock.callCount(), 0);

		// Follow-up must NOT include `transport` in the t.update payload —
		// preserves the sticky value.
		const { sessionUpdates } = partitionWrites('sessions/sess-1');
		assert.equal(sessionUpdates.length, 1);
		assert.ok(
			!('transport' in sessionUpdates[0]),
			'follow-up must not write transport (preserves sticky existing value)'
		);
	});

	it('v3.9 P1 regression: legacy session with no transport field stays cloudrun', async () => {
		// Submitter IS in allowlist (would pick 'gear' on a NEW session) but
		// the existing session has no `transport` field at all (legacy data
		// written before the field existed). Branch must read `existing` and
		// default to 'cloudrun', NOT call chooseInitialTransport.
		GEAR_ALLOWLIST.add('user-good-token');
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				participants: ['user-good-token'],
				status: 'complete',
				adkSessionId: 'adk-existing',
				lastTurnIndex: 1
				// no transport field
			})
		}));

		const res = mockRes();
		await agentStream(authedReq({ body: { message: 'follow-up', sessionId: 'sess-1' } }), res);

		assert.equal(res._status, 202);
		assert.equal(
			tasksClient.createTask.mock.callCount(),
			1,
			'legacy session must route to cloudrun'
		);
		assert.equal(gearHandoffMock.mock.callCount(), 0);

		// And the t.update payload still doesn't include `transport` — the
		// field stays nullish on legacy sessions until they naturally drain.
		const { sessionUpdates } = partitionWrites('sessions/sess-1');
		assert.equal(sessionUpdates.length, 1);
		assert.ok(!('transport' in sessionUpdates[0]));
	});

	it('chooseInitialTransport: allowlist hit/miss + default-flipped scenarios', () => {
		// Pure unit test via parameters — no module-state mutation.
		assert.equal(chooseInitialTransport('user-x', new Set(), 'cloudrun'), 'cloudrun');
		assert.equal(chooseInitialTransport('user-x', new Set(['user-x']), 'cloudrun'), 'gear');
		// GEAR_DEFAULT-flipped scenario (Stage B):
		assert.equal(chooseInitialTransport('user-x', new Set(), 'gear'), 'gear');
		// Allowlist for a different user → default applies:
		assert.equal(chooseInitialTransport('user-x', new Set(['user-y']), 'cloudrun'), 'cloudrun');
	});
});

// ══════════════════════════════════════════════════════
// agentDelete
// ══════════════════════════════════════════════════════

describe('agentDelete', () => {
	function authedDelete(sid, overrides = {}) {
		return mockReq({
			method: 'POST',
			body: { sid, ...(overrides.body || {}) },
			headers: { authorization: 'Bearer good-token', ...(overrides.headers || {}) }
		});
	}

	it('rejects non-POST with 405', async () => {
		const res = mockRes();
		await agentDelete(mockReq({ method: 'GET' }), res);
		assert.equal(res._status, 405);
		assert.equal(res._json.ok, false);
	});

	it('returns 401 when Authorization header is missing', async () => {
		const res = mockRes();
		await agentDelete(mockReq({ method: 'POST', body: { sid: 'sess-1' } }), res);
		assert.equal(res._status, 401);
		assert.equal(mockDb.recursiveDelete.mock.callCount(), 0);
	});

	it('returns 401 when token verification fails', async () => {
		const res = mockRes();
		await agentDelete(
			authedDelete('sess-1', { headers: { authorization: 'Bearer bad-token' } }),
			res
		);
		assert.equal(res._status, 401);
		assert.equal(mockDb.recursiveDelete.mock.callCount(), 0);
	});

	it('returns 400 when sid is missing or not a string', async () => {
		const res = mockRes();
		await agentDelete(
			mockReq({
				method: 'POST',
				body: {},
				headers: { authorization: 'Bearer good-token' }
			}),
			res
		);
		assert.equal(res._status, 400);

		const res2 = mockRes();
		await agentDelete(
			mockReq({
				method: 'POST',
				body: { sid: 42 },
				headers: { authorization: 'Bearer good-token' }
			}),
			res2
		);
		assert.equal(res2._status, 400);
		assert.equal(mockDb.recursiveDelete.mock.callCount(), 0);
	});

	it('returns 404 session_not_found when session doc does not exist', async () => {
		mockDb.get.mock.mockImplementation(async () => ({ exists: false }));

		const res = mockRes();
		await agentDelete(authedDelete('missing'), res);

		assert.equal(res._status, 404);
		assert.equal(res._json.ok, false);
		assert.equal(res._json.error, 'session_not_found');
		assert.equal(mockDb.recursiveDelete.mock.callCount(), 0);
	});

	it('returns 403 not_creator when caller is a contributor, not the creator', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-creator-token',
				participants: ['user-creator-token', 'user-good-token']
			})
		}));

		const res = mockRes();
		await agentDelete(authedDelete('sess-1'), res);

		assert.equal(res._status, 403);
		assert.equal(res._json.ok, false);
		assert.equal(res._json.error, 'not_creator');
		assert.equal(mockDb.recursiveDelete.mock.callCount(), 0);
	});

	it('returns 200 and recursively deletes when caller is the creator', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				participants: ['user-good-token']
			})
		}));

		const res = mockRes();
		await agentDelete(authedDelete('sess-1'), res);

		assert.equal(res._status, 200);
		assert.equal(res._json.ok, true);
		assert.equal(mockDb.recursiveDelete.mock.callCount(), 1);
		const deletedRef = mockDb.recursiveDelete.mock.calls[0].arguments[0];
		assert.equal(deletedRef._path, 'sessions/sess-1');
	});

	it('returns 500 delete_failed and logs when recursiveDelete rejects', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				participants: ['user-good-token']
			})
		}));
		mockDb.recursiveDelete.mock.mockImplementationOnce(async () => {
			throw new Error('firestore outage');
		});

		const errs = [];
		const origError = console.error;
		console.error = (...args) => errs.push(args);
		try {
			const res = mockRes();
			await agentDelete(authedDelete('sess-1'), res);

			assert.equal(res._status, 500);
			assert.equal(res._json.ok, false);
			assert.equal(res._json.error, 'delete_failed');
			assert.equal(mockDb.recursiveDelete.mock.callCount(), 1);
			// Logged the error along with the sid so operators can trace.
			assert.ok(
				errs.some((line) => line.some((v) => typeof v === 'string' && v.includes('sess-1'))),
				'expected console.error to include the sid'
			);
		} finally {
			console.error = origError;
		}
	});
});
