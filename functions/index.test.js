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
// Mock ./gear-handoff.js BEFORE the index.js import. Putting this inside a
// describe block would be too late — index.js captures the real exports at
// import time.
const gearHandoffMock = mock.fn(async () => ({ ok: true }));
const gearHandoffCleanupMock = mock.fn(async () => {});
mock.module('./gear-handoff.js', {
	namedExports: {
		gearHandoff: gearHandoffMock,
		gearHandoffCleanup: gearHandoffCleanupMock
	}
});
const resolveClarificationFocusMock = mock.fn(async () => null);
mock.module('./place-resolver.js', {
	namedExports: {
		resolveClarificationFocus: resolveClarificationFocusMock
	}
});
const runClarificationGateMock = mock.fn(async () => ({ decision: 'research', question: null }));
const shouldRunClarificationGateMock = mock.fn(
	({ isEngineFirstMessage, placeContext }) =>
		isEngineFirstMessage && !(placeContext && placeContext.name)
);
mock.module('./pre-router.js', {
	namedExports: {
		runClarificationGate: runClarificationGateMock,
		shouldRunClarificationGate: shouldRunClarificationGateMock
	}
});

const { intake, agentStream, agentDelete, sttToken, tts } = await import('./index.js');

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
	authInstance.verifyIdToken.mock.resetCalls();
	gearHandoffMock.mock.resetCalls();
	gearHandoffCleanupMock.mock.resetCalls();
	resolveClarificationFocusMock.mock.resetCalls();
	runClarificationGateMock.mock.resetCalls();
	shouldRunClarificationGateMock.mock.resetCalls();
	mockDb.get.mock.mockImplementation(async (ref) => {
		const path = ref?._path;
		if (!path) return { exists: false };
		const setCall = mockDb.set.mock.calls.findLast((c) => c.arguments[0]?._path === path);
		if (!setCall) return { exists: false };
		const updateCalls = mockDb.update.mock.calls.filter((c) => c.arguments[0]?._path === path);
		const data = Object.assign({}, setCall.arguments[1], ...updateCalls.map((c) => c.arguments[1]));
		return { exists: true, data: () => data };
	});
	mockDb.recursiveDelete.mock.mockImplementation(async () => {});
	// Reset mock IMPLEMENTATIONS too — a failed/interrupted
	// `mockImplementationOnce` from a prior test could otherwise leak.
	gearHandoffMock.mock.mockImplementation(async () => ({ ok: true }));
	gearHandoffCleanupMock.mock.mockImplementation(async () => {});
	resolveClarificationFocusMock.mock.mockImplementation(async () => null);
	runClarificationGateMock.mock.mockImplementation(async () => ({
		decision: 'research',
		question: null
	}));
	shouldRunClarificationGateMock.mock.mockImplementation(
		({ isEngineFirstMessage, placeContext }) =>
			isEngineFirstMessage && !(placeContext && placeContext.name)
	);
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
		const turnUpdates = mockDb.update.mock.calls
			.filter((c) => c.arguments[0]?._path?.startsWith(`${sessionPath}/turns/`))
			.map((c) => ({ path: c.arguments[0]._path, data: c.arguments[1] }));
		return { sessionSets, sessionUpdates, turnSets, turnUpdates };
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

	it('first turn research creates session + turns/0001 and marks Engine started', async () => {
		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 202);
		assert.equal(res._json.ok, true);
		assert.equal(res._json.sessionId, 'sess-1');
		assert.match(res._json.runId, /^[0-9a-f-]{36}$/);

		const { sessionSets, sessionUpdates, turnSets } = partitionWrites('sessions/sess-1');

		// First turn: set session, set turn 0001, then mark the Engine session as started.
		assert.equal(sessionSets.length, 1);
		const sessionDoc = sessionSets[0];
		assert.equal(sessionDoc.userId, 'user-good-token');
		assert.deepEqual(sessionDoc.participants, ['user-good-token']);
		assert.equal(sessionDoc.lastTurnIndex, 1);
		assert.equal(sessionDoc.status, 'queued');
		assert.equal(sessionDoc.engineSessionStarted, false);
		assert.equal(sessionDoc.awaitingClarificationAnswer, false);
		assert.equal(sessionDoc.title, null);
		assert.equal(sessionDoc.updatedAt, '__server_timestamp__');
		assert.equal(sessionDoc.queuedAt, '__server_timestamp__');
		assert.equal(sessionDoc.createdAt, '__server_timestamp__');
		// Phase 9: legacy fence + cloudrun-only fields are gone.
		assert.ok(!('adkSessionId' in sessionDoc));
		assert.ok(!('transport' in sessionDoc));
		assert.ok(!('currentAttempt' in sessionDoc));
		assert.ok(!('currentWorkerId' in sessionDoc));
		// Terminal content fields must NOT be on the session doc.
		assert.ok(!('reply' in sessionDoc));
		assert.ok(!('sources' in sessionDoc));
		assert.ok(!('turnSummary' in sessionDoc));
		assert.ok(!('expiresAt' in sessionDoc));

		// Turn 0001 doc.
		assert.equal(turnSets.length, 1);
		assert.equal(turnSets[0].path, 'sessions/sess-1/turns/0001');
		const turnDoc = turnSets[0].data;
		assert.equal(turnDoc.turnIndex, 1);
		assert.equal(turnDoc.runId, res._json.runId);
		assert.equal(turnDoc.userMessage, 'What is the menu like?');
		assert.equal(turnDoc.status, 'pending');

		// Research-ready turns hand off to the Reasoning Engine.
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.sid, 'sess-1');
		assert.equal(handoffArg.runId, res._json.runId);
		assert.equal(handoffArg.userId, 'user-good-token');
		assert.equal(handoffArg.turnIdx, 1);
		assert.equal(handoffArg.isEngineFirstMessage, true);
		assert.match(handoffArg.message, /^\[Date: /);
		assert.equal(runClarificationGateMock.mock.callCount(), 1);
		assert.equal(sessionUpdates.at(-1).engineSessionStarted, true);
		assert.equal(sessionUpdates.at(-1).awaitingClarificationAnswer, false);
	});

	it('first turn injects selected focus context when provided', async () => {
		const res = mockRes();
		await agentStream(
			authedReq({
				body: {
					message: 'What is changing nearby?',
					sessionId: 'sess-1',
					placeContext: {
						name: 'Williamsburg',
						secondary: 'Brooklyn, NY',
						placeId: 'ChIJfocus'
					}
				}
			}),
			res
		);

		assert.equal(res._status, 202);
		const { sessionSets } = partitionWrites('sessions/sess-1');
		assert.deepEqual(sessionSets[0].placeContext, {
			name: 'Williamsburg',
			secondary: 'Brooklyn, NY',
			placeId: 'ChIJfocus'
		});
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(runClarificationGateMock.mock.callCount(), 0);
		assert.match(
			handoffArg.message,
			/^\[Context: selected focus: Williamsburg, Brooklyn, NY \(Google Place ID: ChIJfocus\)\] \[Date: /
		);
		assert.ok(!handoffArg.message.includes('asking about'));
	});

	it('directly completes no-context first turn when the gate asks for clarification', async () => {
		runClarificationGateMock.mock.mockImplementationOnce(async () => ({
			decision: 'clarify',
			question: 'What area should I use?',
			reason: 'missing_geography'
		}));

		const res = mockRes();
		await agentStream(
			authedReq({
				body: {
					message: 'What has opened or closed in my area recently?',
					sessionId: 'sess-1'
				}
			}),
			res
		);

		assert.equal(res._status, 202);
		assert.equal(res._json.direct, 'clarification');
		assert.equal(gearHandoffMock.mock.callCount(), 0);
		const { sessionSets, sessionUpdates, turnSets, turnUpdates } =
			partitionWrites('sessions/sess-1');
		assert.equal(sessionSets[0].engineSessionStarted, false);
		assert.equal(turnSets[0].data.status, 'pending');
		assert.equal(sessionUpdates.at(-1).status, 'complete');
		assert.equal(sessionUpdates.at(-1).engineSessionStarted, false);
		assert.equal(sessionUpdates.at(-1).awaitingClarificationAnswer, true);
		assert.equal(sessionUpdates.at(-1).title, 'What Has Opened Or Closed');
		assert.equal(turnUpdates.length, 1);
		assert.equal(turnUpdates[0].path, 'sessions/sess-1/turns/0001');
		assert.equal(turnUpdates[0].data.status, 'complete');
		assert.equal(turnUpdates[0].data.reply, 'What area should I use?');
		assert.deepEqual(turnUpdates[0].data.sources, []);
		assert.equal(typeof turnUpdates[0].data.turnSummary.elapsedMs, 'number');
	});

	it('turn after direct clarification creates the first Engine session and preserves intent', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			if (ref._path === 'sessions/sess-1') {
				return {
					exists: true,
					data: () => ({
						userId: 'user-good-token',
						participants: ['user-good-token'],
						status: 'complete',
						lastTurnIndex: 1,
						engineSessionStarted: false,
						awaitingClarificationAnswer: true,
						currentRunId: 'prior-run'
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0001') {
				return {
					exists: true,
					data: () => ({
						userMessage: 'What has opened or closed in my area recently?'
					})
				};
			}
			return { exists: false };
		});

		const res = mockRes();
		await agentStream(
			authedReq({ body: { message: 'Williamsburg, Brooklyn', sessionId: 'sess-1' } }),
			res
		);

		assert.equal(res._status, 202);
		assert.equal(runClarificationGateMock.mock.callCount(), 1);
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.turnIdx, 2);
		assert.equal(handoffArg.isEngineFirstMessage, true);
		assert.match(handoffArg.message, /Original question: "What has opened or closed/);
		assert.match(handoffArg.message, /Clarified focus: "Williamsburg, Brooklyn"/);
		assert.match(handoffArg.message, /Answer the original question/);
	});

	it('turn after direct clarification resolves a typed place before asking again', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			if (ref._path === 'sessions/sess-1') {
				const updateCalls = mockDb.update.mock.calls.filter(
					(c) => c.arguments[0]?._path === ref._path
				);
				const base = {
					userId: 'user-good-token',
					participants: ['user-good-token'],
					status: 'complete',
					lastTurnIndex: 1,
					engineSessionStarted: false,
					awaitingClarificationAnswer: true,
					currentRunId: 'prior-run'
				};
				const data = Object.assign({}, base, ...updateCalls.map((c) => c.arguments[1]));
				return {
					exists: true,
					data: () => data
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0001') {
				return {
					exists: true,
					data: () => ({
						userMessage: 'What has opened or closed in my area recently?'
					})
				};
			}
			return { exists: false };
		});
		resolveClarificationFocusMock.mock.mockImplementationOnce(async () => ({
			name: 'Monsun Gdynia',
			secondary: 'Świętojańska 69b, Gdynia',
			placeId: 'ChIJmonsun'
		}));

		const res = mockRes();
		await agentStream(authedReq({ body: { message: 'monsun gdynia', sessionId: 'sess-1' } }), res);

		assert.equal(res._status, 202);
		assert.equal(resolveClarificationFocusMock.mock.callCount(), 1);
		assert.equal(
			resolveClarificationFocusMock.mock.calls[0].arguments[0].originalQuestion,
			'What has opened or closed in my area recently?'
		);
		assert.equal(runClarificationGateMock.mock.callCount(), 0);
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const { sessionUpdates } = partitionWrites('sessions/sess-1');
		assert.deepEqual(sessionUpdates.find((update) => update.placeContext)?.placeContext, {
			name: 'Monsun Gdynia',
			secondary: 'Świętojańska 69b, Gdynia',
			placeId: 'ChIJmonsun'
		});
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.match(handoffArg.message, /Original question: "What has opened or closed/);
		assert.match(
			handoffArg.message,
			/Selected focus: Monsun Gdynia, Świętojańska 69b, Gdynia \(Google Place ID: ChIJmonsun\)\./
		);
		assert.ok(!handoffArg.message.includes('Clarified focus: "monsun gdynia"'));
	});

	it('turn after direct clarification can ask a place disambiguation question', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			if (ref._path === 'sessions/sess-1') {
				const updateCalls = mockDb.update.mock.calls.filter(
					(c) => c.arguments[0]?._path === ref._path
				);
				const base = {
					userId: 'user-good-token',
					participants: ['user-good-token'],
					status: 'complete',
					lastTurnIndex: 1,
					engineSessionStarted: false,
					awaitingClarificationAnswer: true,
					currentRunId: 'prior-run'
				};
				const data = Object.assign({}, base, ...updateCalls.map((c) => c.arguments[1]));
				return {
					exists: true,
					data: () => data
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0001') {
				return {
					exists: true,
					data: () => ({
						userMessage: 'What has opened or closed in my area recently?'
					})
				};
			}
			return { exists: false };
		});
		resolveClarificationFocusMock.mock.mockImplementationOnce(async () => ({
			question: 'Which Zeit für Brot location in Berlin do you mean?',
			reason: 'multiple_plausible_branches'
		}));

		const res = mockRes();
		await agentStream(
			authedReq({ body: { message: 'near Zeit fur Brot in Berlin', sessionId: 'sess-1' } }),
			res
		);

		assert.equal(res._status, 202);
		assert.equal(res._json.direct, 'clarification');
		assert.equal(runClarificationGateMock.mock.callCount(), 0);
		assert.equal(gearHandoffMock.mock.callCount(), 0);
		const { sessionUpdates, turnUpdates } = partitionWrites('sessions/sess-1');
		assert.equal(sessionUpdates.at(-1).awaitingClarificationAnswer, true);
		assert.equal(turnUpdates.at(-1).path, 'sessions/sess-1/turns/0002');
		assert.equal(turnUpdates.at(-1).data.status, 'complete');
		assert.equal(
			turnUpdates.at(-1).data.reply,
			'Which Zeit für Brot location in Berlin do you mean?'
		);
	});

	it('turn after place disambiguation gives the resolver the latest clarification question', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			if (ref._path === 'sessions/sess-1') {
				const updateCalls = mockDb.update.mock.calls.filter(
					(c) => c.arguments[0]?._path === ref._path
				);
				const base = {
					userId: 'user-good-token',
					participants: ['user-good-token'],
					status: 'complete',
					lastTurnIndex: 2,
					engineSessionStarted: false,
					awaitingClarificationAnswer: true,
					currentRunId: 'prior-run'
				};
				const data = Object.assign({}, base, ...updateCalls.map((c) => c.arguments[1]));
				return {
					exists: true,
					data: () => data
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0001') {
				return {
					exists: true,
					data: () => ({
						userMessage: 'What has opened or closed in my area recently?',
						reply: 'What area should I use?'
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0002') {
				return {
					exists: true,
					data: () => ({
						userMessage: 'near Zeit fur Brot in Berlin',
						reply: 'Which Zeit für Brot location in Berlin do you mean?'
					})
				};
			}
			return { exists: false };
		});
		resolveClarificationFocusMock.mock.mockImplementationOnce(async () => ({
			name: 'Zeit für Brot',
			secondary: 'Alte Schönhauser Str. 4, Berlin',
			placeId: 'ChIJzeit'
		}));

		const res = mockRes();
		await agentStream(
			authedReq({ body: { message: 'the one on Alte Schönhauser', sessionId: 'sess-1' } }),
			res
		);

		assert.equal(res._status, 202);
		const resolverArg = resolveClarificationFocusMock.mock.calls[0].arguments[0];
		assert.equal(resolverArg.originalQuestion, 'What has opened or closed in my area recently?');
		assert.equal(
			resolverArg.clarificationQuestion,
			'Which Zeit für Brot location in Berlin do you mean?'
		);
		assert.equal(runClarificationGateMock.mock.callCount(), 0);
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.turnIdx, 3);
		assert.match(
			handoffArg.message,
			/Latest clarification: "Which Zeit für Brot location in Berlin do you mean\?"/
		);
		assert.match(
			handoffArg.message,
			/Selected focus: Zeit für Brot, Alte Schönhauser Str\. 4, Berlin \(Google Place ID: ChIJzeit\)\./
		);
	});

	it('turn after direct clarification uses selected focus when provided', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			if (ref._path === 'sessions/sess-1') {
				return {
					exists: true,
					data: () => ({
						userId: 'user-good-token',
						participants: ['user-good-token'],
						status: 'complete',
						lastTurnIndex: 1,
						engineSessionStarted: false,
						awaitingClarificationAnswer: true,
						currentRunId: 'prior-run'
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0001') {
				return {
					exists: true,
					data: () => ({
						userMessage: 'What has opened or closed in my area recently?'
					})
				};
			}
			return { exists: false };
		});

		const res = mockRes();
		await agentStream(
			authedReq({
				body: {
					message: 'Use this branch',
					sessionId: 'sess-1',
					placeContext: {
						name: 'Zeit fur Brot',
						secondary: 'Alte Schonhauser Str. 4, Berlin',
						placeId: 'ChIJbranch'
					}
				}
			}),
			res
		);

		assert.equal(res._status, 202);
		assert.equal(runClarificationGateMock.mock.callCount(), 0);
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.turnIdx, 2);
		assert.match(handoffArg.message, /Original question: "What has opened or closed/);
		assert.match(
			handoffArg.message,
			/Selected focus: Zeit fur Brot, Alte Schonhauser Str\. 4, Berlin \(Google Place ID: ChIJbranch\)\./
		);
		assert.match(handoffArg.message, /Answer the original question/);
	});

	it('does not treat engineSessionStarted=false as a clarification answer by itself', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			if (ref._path === 'sessions/sess-1') {
				return {
					exists: true,
					data: () => ({
						userId: 'user-good-token',
						participants: ['user-good-token'],
						status: 'complete',
						lastTurnIndex: 1,
						engineSessionStarted: false,
						awaitingClarificationAnswer: false,
						currentRunId: 'prior-run'
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0001') {
				return {
					exists: true,
					data: () => ({
						userMessage: 'What has opened in Williamsburg?'
					})
				};
			}
			return { exists: false };
		});

		const res = mockRes();
		await agentStream(
			authedReq({ body: { message: 'What about Greenpoint?', sessionId: 'sess-1' } }),
			res
		);

		assert.equal(res._status, 202);
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.isEngineFirstMessage, true);
		assert.ok(!handoffArg.message.includes('Original question:'));
		assert.ok(!handoffArg.message.includes('Answer the original question'));
	});

	it('falls back to Agent Engine when the clarification gate fails', async () => {
		runClarificationGateMock.mock.mockImplementationOnce(async () => {
			throw new Error('gate unavailable');
		});

		const res = mockRes();
		await agentStream(
			authedReq({
				body: {
					message: 'What has opened or closed in Williamsburg recently?',
					sessionId: 'sess-1'
				}
			}),
			res
		);

		assert.equal(res._status, 202);
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		assert.equal(gearHandoffMock.mock.calls[0].arguments[0].isEngineFirstMessage, true);
	});

	it('follow-up from the same user arrayUnion-keeps participants and increments lastTurnIndex', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				participants: ['user-good-token'],
				status: 'complete',
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
		// arrayUnion carries the submitter UID; Firestore dedups duplicates.
		assert.deepEqual(sessionUpdate.participants, { __arrayUnion: ['user-good-token'] });
		assert.ok(!('userId' in sessionUpdate));

		assert.equal(turnSets.length, 1);
		assert.equal(turnSets[0].path, 'sessions/sess-1/turns/0002');
		assert.equal(turnSets[0].data.turnIndex, 2);

		// Handoff arg — creator UID still equals the original creator.
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.turnIdx, 2);
		assert.equal(handoffArg.userId, 'user-good-token');
		assert.equal(handoffArg.isEngineFirstMessage, false);
		// Follow-up must NOT re-inject [Context: ...] — Reasoning Engine state holds it.
		assert.ok(!handoffArg.message.includes('[Context:'));
	});

	it('follow-up from a different user (shared URL) preserves creator UID and arrayUnions participants', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-creator-token',
				participants: ['user-creator-token'],
				status: 'complete',
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
		assert.ok(!('userId' in sessionUpdate));
		assert.deepEqual(sessionUpdate.participants, { __arrayUnion: ['user-visitor-token'] });
		assert.equal(sessionUpdate.lastTurnIndex, 3);

		assert.equal(turnSets.length, 1);
		assert.equal(turnSets[0].path, 'sessions/sess-1/turns/0003');

		// Handoff arg: userId = original creator, NOT the submitter.
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.turnIdx, 3);
		assert.equal(handoffArg.userId, 'user-creator-token');
		assert.equal(handoffArg.isEngineFirstMessage, false);
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
		assert.equal(gearHandoffMock.mock.callCount(), 0);
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

		assert.equal(gearHandoffMock.mock.calls[0].arguments[0].turnIdx, 10);
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
		assert.equal(gearHandoffMock.mock.callCount(), 0);
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
		assert.equal(gearHandoffMock.mock.callCount(), 0);
	});

	it('gearHandoff failure → gearHandoffCleanup called, 502 returned', async () => {
		mockDb.get.mock.mockImplementation(async () => ({ exists: false }));
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
