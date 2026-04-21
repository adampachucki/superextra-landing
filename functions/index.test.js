import { describe, it, mock, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

// ── Mock external modules before importing index.js ──

// Firestore mock supports point-doc set/get/update AND runTransaction(cb).
// The txn object exposes the same get/set/update surface as the real txn,
// but without isolation semantics (tests drive sequences manually).
const mockDb = {
	collection: () => mockDb,
	doc: () => mockDb,
	get: mock.fn(async () => ({ exists: false })),
	set: mock.fn(async () => {}),
	update: mock.fn(async () => {}),
	runTransaction: mock.fn(async (cb) => {
		const txn = {
			get: mockDb.get,
			set: mockDb.set,
			update: mockDb.update
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
			serverTimestamp: () => '__server_timestamp__'
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

// Set WORKER_URL before importing so the Cloud Task target resolves.
process.env.WORKER_URL = 'https://worker-test.run.app';

const { intake, agentStream, agentCheck, sttToken, tts } = await import('./index.js');

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
	mockDb.runTransaction.mock.resetCalls();
	tasksClient.createTask.mock.resetCalls();
	authInstance.verifyIdToken.mock.resetCalls();
	mockDb.get.mock.mockImplementation(async () => ({ exists: false }));
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

	it('returns 202 and enqueues a task on success (new session)', async () => {
		mockDb.get.mock.mockImplementation(async () => ({ exists: false }));
		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 202);
		assert.equal(res._json.ok, true);
		assert.equal(res._json.sessionId, 'sess-1');
		assert.match(res._json.runId, /^[0-9a-f-]{36}$/);

		// Exactly one transaction, one task enqueue.
		assert.equal(mockDb.runTransaction.mock.callCount(), 1);
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

		// Body is base64'd JSON — decode and inspect.
		const body = JSON.parse(Buffer.from(taskArg.task.httpRequest.body, 'base64').toString('utf8'));
		assert.equal(body.sessionId, 'sess-1');
		assert.equal(body.runId, res._json.runId);
		assert.equal(body.userId, 'user-good-token');
		assert.equal(body.isFirstMessage, true);
		assert.equal(body.adkSessionId, null);
		// Date prefix present, Context prefix also present for first message.
		assert.match(body.queryText, /^\[Date: /);
	});

	it('returns 403 when sessionId is owned by a different user', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({ userId: 'user-other-token', status: 'complete' })
		}));

		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 403);
		assert.equal(tasksClient.createTask.mock.callCount(), 0);
	});

	it('returns 403 when existing session doc is missing userId (legacy/malformed)', async () => {
		// Audit Finding 3 — old guard short-circuited when `userId` was
		// missing. Legacy docs without `userId` must be rejected.
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({ status: 'complete' }) // no userId
		}));

		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 403);
		assert.equal(tasksClient.createTask.mock.callCount(), 0);
	});

	it('returns 409 when previous turn is still in flight', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({ userId: 'user-good-token', status: 'running', currentRunId: 'prior-run' })
		}));

		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 409);
		assert.equal(tasksClient.createTask.mock.callCount(), 0);
	});

	it('reuses adkSessionId + isFirstMessage=false on follow-up turns', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				status: 'complete',
				adkSessionId: 'adk-existing',
				placeContext: { name: 'Umami', secondary: 'Berlin', placeId: 'ChIJ...' },
				title: 'Prior chat'
			})
		}));

		const res = mockRes();
		await agentStream(authedReq({ body: { message: 'follow-up', sessionId: 'sess-1' } }), res);

		assert.equal(res._status, 202);
		assert.equal(tasksClient.createTask.mock.callCount(), 1);
		const body = JSON.parse(
			Buffer.from(
				tasksClient.createTask.mock.calls[0].arguments[0].task.httpRequest.body,
				'base64'
			).toString('utf8')
		);
		assert.equal(body.adkSessionId, 'adk-existing');
		assert.equal(body.isFirstMessage, false);
		// Follow-up turn must NOT re-inject [Context: ...] — state handles it.
		assert.ok(!body.queryText.includes('[Context:'));
	});

	it('preserves existing expiresAt when it extends beyond now+30d (never shrinks)', async () => {
		// Existing session with expiresAt 60 days in the future. A follow-up
		// enqueue must NOT reset that to now+30d.
		const farFutureMs = Date.now() + 60 * 24 * 60 * 60 * 1000;
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				status: 'complete',
				adkSessionId: 'adk-existing',
				expiresAt: { toMillis: () => farFutureMs }
			})
		}));

		const res = mockRes();
		await agentStream(authedReq({ body: { message: 'follow-up', sessionId: 'sess-1' } }), res);

		assert.equal(res._status, 202);
		assert.equal(mockDb.update.mock.callCount(), 1);
		// Inside the txn, `t.update(ref, perTurn)` — arguments[0] is the ref,
		// arguments[1] is the perTurn payload with expiresAt.
		const perTurn = mockDb.update.mock.calls[0].arguments[1];
		// `newExpiresAt = new Date(max(existing, now+30d))`. With existing at
		// now+60d, result must be a Date whose ms equals the existing one.
		assert.ok(perTurn.expiresAt instanceof Date, 'expiresAt should be a Date');
		assert.equal(perTurn.expiresAt.getTime(), farFutureMs);
	});

	it('extends expiresAt to now+30d when existing is shorter', async () => {
		// Existing session expires in 5 days — too short. Must extend to ~now+30d.
		const soonMs = Date.now() + 5 * 24 * 60 * 60 * 1000;
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				status: 'complete',
				expiresAt: { toMillis: () => soonMs }
			})
		}));

		const before = Date.now();
		const res = mockRes();
		await agentStream(authedReq({ body: { message: 'follow-up', sessionId: 'sess-1' } }), res);
		const after = Date.now();

		assert.equal(res._status, 202);
		const perTurn = mockDb.update.mock.calls[0].arguments[1];
		const got = perTurn.expiresAt.getTime();
		const THIRTY_D = 30 * 24 * 60 * 60 * 1000;
		// now + 30d — allow a small window for the internal Date.now() inside
		// the handler relative to the test's `before`/`after` measurements.
		assert.ok(
			got >= before + THIRTY_D - 100 && got <= after + THIRTY_D + 100,
			`expected expiresAt near now+30d; got ${got - before}ms from test start`
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
		// Post-enqueue recovery: session should be flipped to status=error.
		assert.equal(mockDb.update.mock.callCount(), 1);
		const updateArg = mockDb.update.mock.calls[0].arguments[0];
		assert.equal(updateArg.status, 'error');
		assert.equal(updateArg.error, 'enqueue_failed');
	});
});

// ══════════════════════════════════════════════════════
// agentCheck
// ══════════════════════════════════════════════════════

describe('agentCheck', () => {
	function authedCheck(sid, overrides = {}) {
		return mockReq({
			method: 'GET',
			query: { sid, ...(overrides.query || {}) },
			headers: { authorization: 'Bearer good-token', ...(overrides.headers || {}) }
		});
	}

	it('rejects non-GET with 405', async () => {
		const res = mockRes();
		await agentCheck(mockReq({ method: 'POST' }), res);
		assert.equal(res._status, 405);
	});

	it('returns 400 when sid is missing', async () => {
		const res = mockRes();
		await agentCheck(mockReq({ method: 'GET', query: {} }), res);
		assert.equal(res._status, 400);
		assert.match(res._json.error, /sid/);
	});

	it('returns 401 when Authorization header is missing', async () => {
		const res = mockRes();
		await agentCheck(mockReq({ method: 'GET', query: { sid: 'x' } }), res);
		assert.equal(res._status, 401);
	});

	it('returns 401 when token verification fails', async () => {
		const res = mockRes();
		await agentCheck(
			mockReq({
				method: 'GET',
				query: { sid: 'x' },
				headers: { authorization: 'Bearer bad-token' }
			}),
			res
		);
		assert.equal(res._status, 401);
	});

	it('returns session_not_found when session does not exist', async () => {
		mockDb.get.mock.mockImplementation(async () => ({ exists: false }));
		const res = mockRes();
		await agentCheck(authedCheck('unknown'), res);
		assert.equal(res._json.ok, false);
		assert.equal(res._json.reason, 'session_not_found');
	});

	it('returns 403 when session userId does not match caller', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({ userId: 'user-other-token', status: 'complete', reply: 'r' })
		}));
		const res = mockRes();
		await agentCheck(authedCheck('sid-1'), res);
		assert.equal(res._status, 403);
		assert.equal(res._json.reason, 'ownership_mismatch');
	});

	it('returns 403 when session doc is missing userId (legacy/malformed)', async () => {
		// Audit Finding 3 — old `data.userId && data.userId !== uid` let
		// docs without `userId` slip through. New guard rejects.
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({ status: 'complete', reply: 'should not return' })
		}));
		const res = mockRes();
		await agentCheck(authedCheck('sid-1'), res);
		assert.equal(res._status, 403);
		assert.equal(res._json.reason, 'ownership_mismatch');
	});

	it('returns complete reply + sources + title when status=complete', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				status: 'complete',
				reply: 'The final report.',
				sources: [{ title: 'S1', url: 'https://s1.example' }],
				title: 'Chat title'
			})
		}));

		const res = mockRes();
		await agentCheck(authedCheck('known'), res);
		assert.equal(res._json.ok, true);
		assert.equal(res._json.status, 'complete');
		assert.equal(res._json.reply, 'The final report.');
		assert.deepEqual(res._json.sources, [{ title: 'S1', url: 'https://s1.example' }]);
		assert.equal(res._json.title, 'Chat title');
	});

	it('returns pipeline_error when status=error', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				status: 'error',
				error: 'synthesizer_failed'
			})
		}));

		const res = mockRes();
		await agentCheck(authedCheck('errored'), res);
		assert.equal(res._json.ok, false);
		assert.equal(res._json.reason, 'pipeline_error');
		assert.equal(res._json.error, 'synthesizer_failed');
	});

	it('returns status=running with null reply while pipeline is in flight', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				status: 'running',
				currentRunId: 'run-1',
				reply: null
			})
		}));

		const res = mockRes();
		await agentCheck(authedCheck('pending'), res);
		assert.equal(res._json.ok, true);
		assert.equal(res._json.status, 'running');
		assert.equal(res._json.reply, null);
	});

	it('accepts (and ignores) a stale runId query param — returns current state', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				userId: 'user-good-token',
				status: 'complete',
				reply: 'Latest reply.',
				currentRunId: 'run-latest'
			})
		}));

		const res = mockRes();
		await agentCheck(authedCheck('sid-1', { query: { runId: 'run-stale' } }), res);
		assert.equal(res._json.ok, true);
		assert.equal(res._json.reply, 'Latest reply.');
	});
});
