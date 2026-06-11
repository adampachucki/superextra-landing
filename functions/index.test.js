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
			get: (ref) => mockDb.get(ref),
			set: (ref, data) => mockDb.set(ref, data),
			update: (ref, data) => mockDb.update(ref, data)
		};
		return cb(txn);
	})
};

// Opt-in default for tests that don't model the per-account user doc:
// returns a paid user for `users/{uid}` so tests don't need to model the
// agent-side quota gate (which reads users/{uid} from inside the engine,
// not the Cloud Function). Returns `null` for any other path so the caller
// can fall through.
function defaultAccountDoc(ref) {
	const path = ref?._path || '';
	if (path.startsWith('users/')) {
		return {
			exists: true,
			data: () => ({
				plan: 'paid',
				limitOverrides: null
			})
		};
	}
	return null;
}

function readMockWrittenDoc(ref) {
	const path = ref?._path;
	if (!path) return { exists: false };
	const setCall = mockDb.set.mock.calls.findLast((c) => c.arguments[0]?._path === path);
	const updateCalls = mockDb.update.mock.calls.filter((c) => c.arguments[0]?._path === path);
	if (!setCall && updateCalls.length === 0) return { exists: false };
	const data = Object.assign(
		{},
		setCall?.arguments[1] || {},
		...updateCalls.map((c) => c.arguments[1])
	);
	return { exists: true, data: () => data };
}

function readWrittenFirst(ref, fallback) {
	const written = readMockWrittenDoc(ref);
	if (written.exists) return written;
	const accountDefault = defaultAccountDoc(ref);
	if (accountDefault) return accountDefault;
	return typeof fallback === 'function' ? fallback(ref) : fallback;
}

// Firebase Auth mock — verifyIdToken returns { uid, firebase: { sign_in_provider } }
// so tests can drive anonymous-token rejection and provider-aware code paths.
// Tokens starting with 'anon-' simulate anonymous sign-in; everything else
// counts as a real provider (Google / email link).
const authInstance = {
	verifyIdToken: mock.fn(async (token) => {
		if (token === 'bad-token') throw new Error('invalid token');
		const isAnon = typeof token === 'string' && token.startsWith('anon-');
		return {
			uid: `user-${token}`,
			email: isAnon ? null : `${token}@example.com`,
			name: isAnon ? null : `User ${token}`,
			picture: isAnon ? null : `https://example.com/${token}.png`,
			firebase: { sign_in_provider: isAnon ? 'anonymous' : 'google.com' }
		};
	}),
	generateSignInWithEmailLink: mock.fn(
		async (email, settings) => `https://example.test/__link__?email=${email}&url=${settings.url}`
	)
};

mock.module('firebase-admin/app', {
	namedExports: { initializeApp: mock.fn() }
});
mock.module('firebase-admin/firestore', {
	namedExports: {
		getFirestore: mock.fn(() => mockDb),
		FieldValue: {
			serverTimestamp: () => '__server_timestamp__',
			arrayUnion: (...values) => ({ __arrayUnion: values }),
			delete: () => ({ __delete: true }),
			increment: (n) => ({ __increment: n })
		},
		Timestamp: {
			fromMillis: (ms) => ({ __timestampMillis: ms })
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
		}),
		defineString: () => ({ value: () => '' })
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
const runIntakeConversationMock = mock.fn(async ({ message, selectedPlaceContext = null }) => ({
	action: 'start_research',
	researchQuestion: message,
	placeContext: selectedPlaceContext,
	acknowledgement: 'Preparing the report. This will take a few minutes.',
	state: null,
	reason: 'test_default'
}));
mock.module('./intake-agent.js', {
	namedExports: {
		runIntakeConversation: runIntakeConversationMock
	}
});
// Mock language detection so agentStream tests don't make a real Gemini call.
const detectLanguageMock = mock.fn(async () => 'en');
mock.module('./detect-language.js', {
	namedExports: {
		detectLanguage: detectLanguageMock,
		SUPPORTED_LOCALES: ['en', 'de', 'pl']
	}
});

const {
	intake,
	agentStream,
	agentCancel,
	agentDelete,
	agentFeedback,
	sttToken,
	tts,
	sendMagicLink,
	_resetRateLimits
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
	authInstance.verifyIdToken.mock.resetCalls();
	gearHandoffMock.mock.resetCalls();
	gearHandoffCleanupMock.mock.resetCalls();
	runIntakeConversationMock.mock.resetCalls();
	authInstance.generateSignInWithEmailLink.mock.resetCalls();
	_resetRateLimits();
	mockDb.get.mock.mockImplementation(async (ref) => {
		const path = ref?._path || '';
		// Default user docs to the paid tier — the Cloud Function only reads
		// users/{uid} for identity provisioning now; quota enforcement is in
		// the agent's research_pipeline before_agent_callback.
		if (path.startsWith('users/')) {
			return {
				exists: true,
				data: () => ({
					plan: 'paid',
					limitOverrides: null
				})
			};
		}
		return readMockWrittenDoc(ref);
	});
	mockDb.recursiveDelete.mock.mockImplementation(async () => {});
	// Reset mock IMPLEMENTATIONS too — a failed/interrupted
	// `mockImplementationOnce` from a prior test could otherwise leak.
	gearHandoffMock.mock.mockImplementation(async () => ({ ok: true }));
	gearHandoffCleanupMock.mock.mockImplementation(async () => {});
	runIntakeConversationMock.mock.mockImplementation(
		async ({ message, selectedPlaceContext = null }) => ({
			action: 'start_research',
			researchQuestion: message,
			placeContext: selectedPlaceContext,
			acknowledgement: 'Preparing the report. This will take a few minutes.',
			state: null,
			reason: 'test_default'
		})
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

	it('sends demo request emails and returns ok on success', async () => {
		const calls = [];
		globalThis.fetch = mock.fn(async (url, init) => {
			calls.push({ url, body: JSON.parse(init.body) });
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
		assert.ok(calls[0].url.includes('resend.com'));
		assert.equal(calls[0].body.subject, 'Demo request - Test Bistro');
		assert.ok(calls[0].body.html.includes('New demo request'));
		assert.ok(calls[1].url.includes('resend.com'));
		assert.equal(calls[1].body.subject, 'Superextra demo request received');
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

		const { sessionSets, sessionUpdates, turnSets, turnUpdates } =
			partitionWrites('sessions/sess-1');

		// First turn: set session, set turn 0001, then mark the Engine session as started.
		assert.equal(sessionSets.length, 1);
		const sessionDoc = sessionSets[0];
		assert.equal(sessionDoc.userId, 'user-good-token');
		assert.deepEqual(sessionDoc.participants, ['user-good-token']);
		assert.equal(sessionDoc.lastTurnIndex, 1);
		assert.equal(sessionDoc.status, 'queued');
		assert.equal(sessionDoc.engineSessionStarted, false);
		assert.equal(sessionDoc.engineSessionId, 'se-sess-1');
		assert.equal(sessionDoc.engineSessionGeneration, 1);
		assert.equal(sessionDoc.intakeState, null);
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
		assert.equal(turnDoc.language, 'en'); // detected per turn (mock returns 'en')
		assert.equal(turnDoc.status, 'pending');
		assert.equal(turnDoc.acknowledgement, null);
		assert.equal(turnDoc.acknowledgedAt, null);
		const ackUpdate = turnUpdates.find((update) => update.data.acknowledgement);
		assert.ok(ackUpdate);
		assert.equal(ackUpdate.path, 'sessions/sess-1/turns/0001');
		assert.match(ackUpdate.data.acknowledgement, /few minutes/);
		assert.equal(ackUpdate.data.acknowledgedAt, '__server_timestamp__');

		// Research-ready turns hand off to the Reasoning Engine.
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.sid, 'sess-1');
		assert.equal(handoffArg.runId, res._json.runId);
		assert.equal(handoffArg.userId, 'user-good-token');
		assert.equal(handoffArg.turnIdx, 1);
		assert.equal(handoffArg.isEngineFirstMessage, true);
		assert.equal(handoffArg.createEngineSession, true);
		assert.equal(handoffArg.engineSessionId, 'se-sess-1');
		assert.equal(handoffArg.seedState, null);
		assert.match(handoffArg.message, /^\[Date: /);
		assert.equal(runIntakeConversationMock.mock.callCount(), 1);
		assert.equal(sessionUpdates.at(-1).engineSessionStarted, true);
		assert.equal(sessionUpdates.at(-1).intakeState, null);
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
		assert.equal(runIntakeConversationMock.mock.callCount(), 1);
		assert.deepEqual(runIntakeConversationMock.mock.calls[0].arguments[0].selectedPlaceContext, {
			name: 'Williamsburg',
			secondary: 'Brooklyn, NY',
			placeId: 'ChIJfocus'
		});
		assert.match(
			handoffArg.message,
			/^\[Context: selected focus: Williamsburg, Brooklyn, NY \(Google Place ID: ChIJfocus\)\] \[Date: /
		);
		assert.ok(!handoffArg.message.includes('asking about'));
	});

	it('first turn can start research with an intake-resolved place', async () => {
		runIntakeConversationMock.mock.mockImplementationOnce(async () => ({
			action: 'start_research',
			researchQuestion: 'What has opened or closed around Monsun Gdynia recently?',
			placeContext: {
				name: 'Monsun Gdynia',
				secondary: 'Świętojańska 69b, Gdynia',
				placeId: 'ChIJmonsun'
			},
			state: {
				originalIntent: 'What has opened or closed around monsun in gdynia recently?'
			},
			reason: 'place_ready'
		}));

		const res = mockRes();
		await agentStream(
			authedReq({
				body: {
					message: 'What has opened or closed around monsun in gdynia recently?',
					sessionId: 'sess-1'
				}
			}),
			res
		);

		assert.equal(res._status, 202);
		assert.equal(runIntakeConversationMock.mock.callCount(), 1);
		const intakeArg = runIntakeConversationMock.mock.calls[0].arguments[0];
		assert.equal(intakeArg.message, 'What has opened or closed around monsun in gdynia recently?');
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const { sessionUpdates } = partitionWrites('sessions/sess-1');
		assert.deepEqual(sessionUpdates.find((update) => update.placeContext)?.placeContext, {
			name: 'Monsun Gdynia',
			secondary: 'Świętojańska 69b, Gdynia',
			placeId: 'ChIJmonsun'
		});
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.match(
			handoffArg.message,
			/^\[Context: selected focus: Monsun Gdynia, Świętojańska 69b, Gdynia \(Google Place ID: ChIJmonsun\)\] \[Date: /
		);
		assert.match(handoffArg.message, /What has opened or closed around Monsun Gdynia/);
	});

	it('directly completes no-context first turn when intake replies', async () => {
		runIntakeConversationMock.mock.mockImplementationOnce(async () => ({
			action: 'reply',
			reply: 'What area should I use?',
			state: {
				originalIntent: 'What has opened or closed in my area recently?',
				pendingQuestion: 'What area should I use?'
			},
			reason: 'missing_scope'
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
		assert.equal(res._json.direct, 'intake');
		assert.equal(gearHandoffMock.mock.callCount(), 0);
		const { sessionSets, sessionUpdates, turnSets, turnUpdates } =
			partitionWrites('sessions/sess-1');
		assert.equal(sessionSets[0].engineSessionStarted, false);
		assert.equal(turnSets[0].data.status, 'pending');
		assert.equal(sessionUpdates.at(-1).status, 'complete');
		assert.equal(sessionUpdates.at(-1).engineSessionStarted, false);
		assert.equal(
			sessionUpdates.at(-1).intakeState.originalIntent,
			'What has opened or closed in my area recently?'
		);
		assert.equal(sessionUpdates.at(-1).title, 'What Has Opened Or Closed');
		assert.equal(turnUpdates.length, 1);
		assert.equal(turnUpdates[0].path, 'sessions/sess-1/turns/0001');
		assert.equal(turnUpdates[0].data.status, 'complete');
		assert.equal(turnUpdates[0].data.reply, 'What area should I use?');
		assert.deepEqual(turnUpdates[0].data.sources, []);
		assert.equal(typeof turnUpdates[0].data.turnSummary.elapsedMs, 'number');
	});

	it('later intake turn creates the first Engine session from model-synthesized intent', async () => {
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
					intakeState: {
						originalIntent: 'What has opened or closed in my area recently?',
						pendingQuestion: 'What area should I use?'
					},
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
						status: 'complete',
						userMessage: 'What has opened or closed in my area recently?'
					})
				};
			}
			return defaultAccountDoc(ref) ?? { exists: false };
		});
		runIntakeConversationMock.mock.mockImplementationOnce(async () => ({
			action: 'start_research',
			researchQuestion: 'What has opened or closed in Williamsburg, Brooklyn recently?',
			placeContext: null,
			acknowledgement:
				'Reviewing recent restaurant openings and closures in Williamsburg, Brooklyn. The report will take a few minutes.',
			state: {
				originalIntent: 'What has opened or closed in my area recently?',
				scopeSummary: 'Williamsburg, Brooklyn'
			},
			reason: 'area_ready'
		}));

		const res = mockRes();
		await agentStream(
			authedReq({ body: { message: 'Williamsburg, Brooklyn', sessionId: 'sess-1' } }),
			res
		);

		assert.equal(res._status, 202);
		assert.equal(runIntakeConversationMock.mock.callCount(), 1);
		const intakeArg = runIntakeConversationMock.mock.calls[0].arguments[0];
		assert.deepEqual(intakeArg.history, [
			{ role: 'user', text: 'What has opened or closed in my area recently?' }
		]);
		assert.equal(
			intakeArg.intakeState.originalIntent,
			'What has opened or closed in my area recently?'
		);
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.turnIdx, 2);
		assert.equal(handoffArg.isEngineFirstMessage, true);
		assert.match(handoffArg.message, /What has opened or closed in Williamsburg, Brooklyn/);
		const { turnUpdates } = partitionWrites('sessions/sess-1');
		assert.equal(
			turnUpdates.find((update) => update.data.acknowledgement)?.data.acknowledgement,
			'Reviewing recent restaurant openings and closures in Williamsburg, Brooklyn. The report will take a few minutes.'
		);
	});

	it('later intake turn can start research with a typed place', async () => {
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
					intakeState: {
						originalIntent: 'What has opened or closed in my area recently?'
					},
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
			return defaultAccountDoc(ref) ?? { exists: false };
		});
		runIntakeConversationMock.mock.mockImplementationOnce(async () => ({
			action: 'start_research',
			researchQuestion: 'What has opened or closed around Monsun Gdynia recently?',
			placeContext: {
				name: 'Monsun Gdynia',
				secondary: 'Świętojańska 69b, Gdynia',
				placeId: 'ChIJmonsun'
			},
			state: {
				originalIntent: 'What has opened or closed in my area recently?',
				scopeSummary: 'Monsun Gdynia'
			},
			reason: 'place_ready'
		}));

		const res = mockRes();
		await agentStream(authedReq({ body: { message: 'monsun gdynia', sessionId: 'sess-1' } }), res);

		assert.equal(res._status, 202);
		assert.equal(runIntakeConversationMock.mock.callCount(), 1);
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const { sessionUpdates } = partitionWrites('sessions/sess-1');
		assert.deepEqual(sessionUpdates.find((update) => update.placeContext)?.placeContext, {
			name: 'Monsun Gdynia',
			secondary: 'Świętojańska 69b, Gdynia',
			placeId: 'ChIJmonsun'
		});
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.match(
			handoffArg.message,
			/selected focus: Monsun Gdynia, Świętojańska 69b, Gdynia \(Google Place ID: ChIJmonsun\)/
		);
		assert.match(handoffArg.message, /What has opened or closed around Monsun Gdynia/);
	});

	it('intake can reply with remembered place candidates', async () => {
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
					intakeState: {
						originalIntent: 'What has opened or closed in my area recently?'
					},
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
			return defaultAccountDoc(ref) ?? { exists: false };
		});
		runIntakeConversationMock.mock.mockImplementationOnce(async () => ({
			action: 'reply',
			reply: 'Which Zeit für Brot location in Berlin do you mean?',
			state: {
				originalIntent: 'What has opened or closed in my area recently?',
				scopeSummary: 'Zeit für Brot in Berlin',
				candidates: [
					{
						optionNumber: 1,
						placeId: 'ChIJzeit-a',
						name: 'Zeit für Brot',
						address: 'Alte Schönhauser Str. 4, Berlin'
					}
				]
			},
			reason: 'multiple_candidates'
		}));

		const res = mockRes();
		await agentStream(
			authedReq({ body: { message: 'near Zeit fur Brot in Berlin', sessionId: 'sess-1' } }),
			res
		);

		assert.equal(res._status, 202);
		assert.equal(res._json.direct, 'intake');
		assert.equal(gearHandoffMock.mock.callCount(), 0);
		const { sessionUpdates, turnUpdates } = partitionWrites('sessions/sess-1');
		assert.equal(sessionUpdates.at(-1).intakeState.candidates[0].placeId, 'ChIJzeit-a');
		assert.equal(turnUpdates.at(-1).path, 'sessions/sess-1/turns/0002');
		assert.equal(turnUpdates.at(-1).data.status, 'complete');
		assert.equal(
			turnUpdates.at(-1).data.reply,
			'Which Zeit für Brot location in Berlin do you mean?'
		);
	});

	it('intake can use remembered candidates on a later pick', async () => {
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
					intakeState: {
						originalIntent: 'What has opened or closed in my area recently?',
						scopeSummary: 'Zeit für Brot in Berlin',
						candidates: [
							{
								optionNumber: 1,
								placeId: 'ChIJzeit',
								name: 'Zeit für Brot',
								address: 'Alte Schönhauser Str. 4, Berlin'
							}
						]
					},
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
						status: 'complete',
						userMessage: 'What has opened or closed in my area recently?',
						reply: 'What area should I use?'
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0002') {
				return {
					exists: true,
					data: () => ({
						status: 'complete',
						userMessage: 'near Zeit fur Brot in Berlin',
						reply: 'Which Zeit für Brot location in Berlin do you mean?'
					})
				};
			}
			return defaultAccountDoc(ref) ?? { exists: false };
		});
		runIntakeConversationMock.mock.mockImplementationOnce(async () => ({
			action: 'start_research',
			researchQuestion:
				'What has opened or closed around Zeit für Brot on Alte Schönhauser Str. 4 recently?',
			placeContext: {
				name: 'Zeit für Brot',
				secondary: 'Alte Schönhauser Str. 4, Berlin',
				placeId: 'ChIJzeit'
			},
			state: {
				originalIntent: 'What has opened or closed in my area recently?',
				scopeSummary: 'Zeit für Brot, Alte Schönhauser Str. 4'
			},
			reason: 'candidate_selected'
		}));

		const res = mockRes();
		await agentStream(
			authedReq({ body: { message: 'the one on Alte Schönhauser', sessionId: 'sess-1' } }),
			res
		);

		assert.equal(res._status, 202);
		const intakeArg = runIntakeConversationMock.mock.calls[0].arguments[0];
		assert.equal(intakeArg.intakeState.candidates[0].placeId, 'ChIJzeit');
		assert.equal(intakeArg.history.length, 4);
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.turnIdx, 3);
		assert.match(
			handoffArg.message,
			/selected focus: Zeit für Brot, Alte Schönhauser Str\. 4, Berlin \(Google Place ID: ChIJzeit\)/
		);
	});

	it('turn after direct clarification uses selected focus when provided', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			const written = readMockWrittenDoc(ref);
			if (written.exists) return written;
			if (ref._path === 'sessions/sess-1') {
				return {
					exists: true,
					data: () => ({
						userId: 'user-good-token',
						participants: ['user-good-token'],
						status: 'complete',
						lastTurnIndex: 1,
						engineSessionStarted: false,
						intakeState: {
							originalIntent: 'What has opened or closed in my area recently?'
						},
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
			return defaultAccountDoc(ref) ?? { exists: false };
		});
		runIntakeConversationMock.mock.mockImplementationOnce(async ({ selectedPlaceContext }) => ({
			action: 'start_research',
			researchQuestion: 'What has opened or closed around this Zeit fur Brot branch recently?',
			placeContext: selectedPlaceContext,
			state: {
				originalIntent: 'What has opened or closed in my area recently?',
				scopeSummary: 'Zeit fur Brot, Alte Schonhauser Str. 4'
			},
			reason: 'selected_place_ready'
		}));

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
		assert.equal(runIntakeConversationMock.mock.callCount(), 1);
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.turnIdx, 2);
		assert.match(
			handoffArg.message,
			/selected focus: Zeit fur Brot, Alte Schonhauser Str\. 4, Berlin \(Google Place ID: ChIJbranch\)/
		);
		assert.match(handoffArg.message, /What has opened or closed around this Zeit fur Brot branch/);
	});

	it('does not reconstruct prior turns with fixed clarification wording', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			const written = readMockWrittenDoc(ref);
			if (written.exists) return written;
			if (ref._path === 'sessions/sess-1') {
				return {
					exists: true,
					data: () => ({
						userId: 'user-good-token',
						participants: ['user-good-token'],
						status: 'complete',
						lastTurnIndex: 1,
						engineSessionStarted: false,
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
			return defaultAccountDoc(ref) ?? { exists: false };
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

	it('falls back to Agent Engine when intake fails', async () => {
		runIntakeConversationMock.mock.mockImplementationOnce(async () => {
			throw new Error('intake unavailable');
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

	it('does not hand off when the run is cancelled during intake', async () => {
		runIntakeConversationMock.mock.mockImplementationOnce(async ({ message }) => {
			await mockDb.update(makeRef('sessions/sess-1'), {
				status: 'error',
				currentRunId: null
			});
			return {
				action: 'start_research',
				researchQuestion: message,
				placeContext: null,
				acknowledgement: 'Preparing the report. This will take a few minutes.',
				state: null,
				reason: 'test_cancelled'
			};
		});

		const res = mockRes();
		await agentStream(authedReq({ ip: '127.0.0.250' }), res);

		assert.equal(res._status, 202);
		assert.equal(res._json.cancelled, true);
		assert.equal(gearHandoffMock.mock.callCount(), 0);
		assert.equal(gearHandoffCleanupMock.mock.callCount(), 0);
	});

	it('does not hand off when the run is cancelled after intake records research start', async () => {
		let researchStartRecorded = false;
		mockDb.update.mock.mockImplementation(async (ref, data) => {
			if (ref?._path === 'sessions/sess-1' && Object.hasOwn(data, 'placeContext')) {
				researchStartRecorded = true;
			}
		});
		mockDb.get.mock.mockImplementation(async (ref) => {
			const written = readMockWrittenDoc(ref);
			if (ref?._path === 'sessions/sess-1' && researchStartRecorded && written.exists) {
				const data = written.data();
				return {
					exists: true,
					data: () => ({
						...data,
						status: 'error',
						currentRunId: null
					})
				};
			}
			return written;
		});

		const res = mockRes();
		await agentStream(
			authedReq({
				ip: '127.0.0.249',
				headers: { authorization: 'Bearer post-record-cancel-token' }
			}),
			res
		);

		assert.equal(res._status, 202);
		assert.equal(res._json.cancelled, true);
		assert.equal(gearHandoffMock.mock.callCount(), 0);
		assert.equal(gearHandoffCleanupMock.mock.callCount(), 0);
	});

	it('does not feed a cancelled pre-engine turn back into intake history', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			const written = readMockWrittenDoc(ref);
			if (written.exists) return written;
			if (ref._path === 'sessions/sess-1') {
				return {
					exists: true,
					data: () => ({
						userId: 'user-good-token',
						participants: ['user-good-token'],
						status: 'error',
						error: 'user_cancelled',
						lastTurnIndex: 1,
						engineSessionStarted: false,
						engineSessionId: 'se-sess-1',
						engineSessionGeneration: 1
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0001') {
				return {
					exists: true,
					data: () => ({
						turnIndex: 1,
						status: 'error',
						error: 'user_cancelled',
						userMessage: 'research lunch pricing'
					})
				};
			}
			return defaultAccountDoc(ref) ?? { exists: false };
		});
		runIntakeConversationMock.mock.mockImplementationOnce(async ({ history, message }) => {
			assert.deepEqual(history, []);
			return {
				action: 'start_research',
				researchQuestion: message,
				placeContext: null,
				acknowledgement: 'Preparing the report. This will take a few minutes.',
				state: null,
				reason: 'test_history'
			};
		});

		const res = mockRes();
		await agentStream(
			authedReq({
				ip: '127.0.0.251',
				body: { message: 'use dinner instead', sessionId: 'sess-1' }
			}),
			res
		);

		assert.equal(res._status, 202);
		assert.equal(gearHandoffMock.mock.callCount(), 1);
	});

	it('follow-up from the same user arrayUnion-keeps participants and increments lastTurnIndex', async () => {
		mockDb.get.mock.mockImplementation(async (ref) =>
			readWrittenFirst(ref, {
				exists: true,
				data: () => ({
					userId: 'user-good-token',
					participants: ['user-good-token'],
					status: 'complete',
					lastTurnIndex: 1,
					placeContext: { name: 'Umami', secondary: 'Berlin', placeId: 'ChIJ...' },
					title: 'Prior chat'
				})
			})
		);

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

	it('turn after user cancellation rotates the ADK working session and seeds visible state', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			const written = readMockWrittenDoc(ref);
			if (written.exists) return written;
			if (ref._path === 'sessions/sess-1') {
				return {
					exists: true,
					data: () => ({
						userId: 'user-good-token',
						participants: ['user-good-token', 'user-rotation-token'],
						status: 'error',
						error: 'user_cancelled',
						lastTurnIndex: 3,
						engineSessionStarted: true,
						engineSessionId: 'se-sess-1',
						engineSessionGeneration: 1,
						placeContext: { name: 'Umami', secondary: 'Seattle, WA', placeId: 'ChIJumami' },
						title: 'Prior chat'
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0001') {
				return {
					exists: true,
					data: () => ({
						turnIndex: 1,
						status: 'complete',
						userMessage: 'What restaurant should open here?',
						reply: 'Which area should I use?',
						turnKind: 'intake_reply'
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0002') {
				return {
					exists: true,
					data: () => ({
						turnIndex: 2,
						status: 'complete',
						userMessage: 'Use Capitol Hill',
						reply: 'Completed market report',
						turnKind: 'research_report',
						sources: [{ title: 'Source', url: 'https://example.com/report' }]
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0003') {
				return {
					exists: true,
					data: () => ({
						turnIndex: 3,
						status: 'error',
						error: 'user_cancelled',
						userMessage: 'Research lunch pricing in detail'
					})
				};
			}
			return defaultAccountDoc(ref) ?? { exists: false };
		});

		const res = mockRes();
		await agentStream(
			authedReq({
				ip: '127.0.0.2',
				headers: { authorization: 'Bearer rotation-token' },
				body: { message: 'Continue with dinner pricing', sessionId: 'sess-1' }
			}),
			res
		);

		assert.equal(res._status, 202);
		assert.equal(runIntakeConversationMock.mock.callCount(), 0);
		const { sessionUpdates, turnSets } = partitionWrites('sessions/sess-1');
		const sessionUpdate = sessionUpdates[0];
		assert.equal(sessionUpdate.lastTurnIndex, 4);
		assert.equal(sessionUpdate.engineSessionId, 'se-sess-1-g2');
		assert.equal(sessionUpdate.engineSessionGeneration, 2);
		assert.deepEqual(sessionUpdate.cancelledAt, { __delete: true });
		assert.equal(turnSets[0].path, 'sessions/sess-1/turns/0004');

		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.turnIdx, 4);
		assert.equal(handoffArg.isEngineFirstMessage, true);
		assert.equal(handoffArg.createEngineSession, true);
		assert.equal(handoffArg.engineSessionId, 'se-sess-1-g2');
		assert.equal(handoffArg.seedState.final_report, 'Completed market report');
		assert.equal(handoffArg.seedState.previous_stopped_request, 'Research lunch pricing in detail');
		assert.match(handoffArg.seedState.continuation_notes, /What restaurant should open here\?/);
		assert.match(handoffArg.message, /^\[Context: selected focus: Umami, Seattle, WA/);
		assert.match(
			handoffArg.message,
			/\[Previous stopped request: Research lunch pricing in detail\]/
		);
	});

	it('does not treat legacy sourced follow-ups as the durable research report', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			const written = readMockWrittenDoc(ref);
			if (written.exists) return written;
			if (ref._path === 'sessions/sess-1') {
				return {
					exists: true,
					data: () => ({
						userId: 'user-good-token',
						participants: ['user-good-token'],
						status: 'error',
						error: 'user_cancelled',
						lastTurnIndex: 3,
						engineSessionStarted: true,
						engineSessionId: 'se-sess-1',
						engineSessionGeneration: 1,
						title: 'Prior chat'
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0001') {
				return {
					exists: true,
					data: () => ({
						turnIndex: 1,
						status: 'complete',
						userMessage: 'Initial report',
						reply: 'Original market report',
						sources: [{ title: 'Report source', url: 'https://example.com/report' }]
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0002') {
				return {
					exists: true,
					data: () => ({
						turnIndex: 2,
						status: 'complete',
						userMessage: 'Continue with competitors',
						reply: 'Legacy continuation answer with a source',
						sources: [{ title: 'Follow-up source', url: 'https://example.com/follow-up' }]
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0003') {
				return {
					exists: true,
					data: () => ({
						turnIndex: 3,
						status: 'error',
						error: 'user_cancelled',
						userMessage: 'Research delivery pricing'
					})
				};
			}
			return defaultAccountDoc(ref) ?? { exists: false };
		});

		const res = mockRes();
		await agentStream(
			authedReq({
				ip: '127.0.0.3',
				headers: { authorization: 'Bearer legacy-seed-token' },
				body: { message: 'Continue with dinner pricing', sessionId: 'sess-1' }
			}),
			res
		);

		assert.equal(res._status, 202);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.seedState.final_report, 'Original market report');
		assert.match(handoffArg.seedState.continuation_notes, /Legacy continuation answer/);
	});

	it('follow-up from a different user (shared URL) preserves creator UID and arrayUnions participants', async () => {
		mockDb.get.mock.mockImplementation(async (ref) =>
			readWrittenFirst(ref, {
				exists: true,
				data: () => ({
					userId: 'user-creator-token',
					participants: ['user-creator-token'],
					status: 'complete',
					lastTurnIndex: 2
				})
			})
		);

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

		// Handoff arg: userId = original creator (engine session ownership),
		// quotaUid = the visitor (so the visitor's daily research counter
		// gets charged, not the creator's).
		assert.equal(gearHandoffMock.mock.callCount(), 1);
		const handoffArg = gearHandoffMock.mock.calls[0].arguments[0];
		assert.equal(handoffArg.turnIdx, 3);
		assert.equal(handoffArg.userId, 'user-creator-token');
		assert.equal(handoffArg.quotaUid, 'user-visitor-token');
		assert.equal(handoffArg.isEngineFirstMessage, false);
	});

	it('boundary: lastTurnIndex=9 still admits one more turn and becomes 10', async () => {
		mockDb.get.mock.mockImplementation(async (ref) =>
			readWrittenFirst(ref, {
				exists: true,
				data: () => ({
					userId: 'user-good-token',
					participants: ['user-good-token'],
					status: 'complete',
					lastTurnIndex: 9
				})
			})
		);

		const res = mockRes();
		await agentStream(
			authedReq({
				ip: '127.0.0.252',
				headers: { authorization: 'Bearer handoff-failure-token' }
			}),
			res
		);

		assert.equal(res._status, 202);
		const { sessionUpdates, turnSets } = partitionWrites('sessions/sess-1');
		assert.equal(sessionUpdates[0].lastTurnIndex, 10);
		assert.equal(turnSets[0].path, 'sessions/sess-1/turns/0010');

		assert.equal(gearHandoffMock.mock.calls[0].arguments[0].turnIdx, 10);
	});

	it('bumps updatedAt on enqueue via serverTimestamp (not just on terminal)', async () => {
		mockDb.get.mock.mockImplementation(async (ref) =>
			readWrittenFirst(ref, {
				exists: true,
				data: () => ({
					userId: 'user-good-token',
					participants: ['user-good-token'],
					status: 'complete',
					lastTurnIndex: 1
				})
			})
		);

		const res = mockRes();
		await agentStream(
			authedReq({
				ip: '127.0.0.254',
				headers: { authorization: 'Bearer cancel-handoff-token' }
			}),
			res
		);

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
		mockDb.get.mock.mockImplementation(async (ref) => readMockWrittenDoc(ref));
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

	it('treats gearHandoff failure after user cancellation as cancelled, not 502', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			if (gearHandoffMock.mock.callCount() > 0 && ref._path === 'sessions/sess-1') {
				return {
					exists: true,
					data: () => ({
						status: 'error',
						error: 'user_cancelled',
						lastTurnIndex: 1
					})
				};
			}
			return readMockWrittenDoc(ref);
		});
		gearHandoffMock.mock.mockImplementationOnce(async () => {
			throw new Error('streamQuery ended before first NDJSON line');
		});

		const res = mockRes();
		await agentStream(authedReq(), res);

		assert.equal(res._status, 202);
		assert.equal(res._json.cancelled, true);
		assert.equal(gearHandoffCleanupMock.mock.callCount(), 0);
	});

	it('rejects anonymous Firebase tokens with 401 AUTH_REQUIRED', async () => {
		const res = mockRes();
		await agentStream(authedReq({ headers: { authorization: 'Bearer anon-leftover-token' } }), res);

		assert.equal(res._status, 401);
		assert.equal(res._json.error, 'AUTH_REQUIRED');
		assert.equal(gearHandoffMock.mock.callCount(), 0);
	});
});

// ══════════════════════════════════════════════════════
// agentCancel
// ══════════════════════════════════════════════════════

describe('agentCancel', () => {
	function authedCancel(sid, overrides = {}) {
		return mockReq({
			method: 'POST',
			body: { sid, runId: 'run-1', turnIndex: 1, ...(overrides.body || {}) },
			headers: { authorization: 'Bearer good-token', ...(overrides.headers || {}) }
		});
	}

	it('rejects non-POST with 405', async () => {
		const res = mockRes();
		await agentCancel(mockReq({ method: 'GET' }), res);
		assert.equal(res._status, 405);
		assert.equal(res._json.ok, false);
	});

	it('returns 403 when caller is not a participant', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				participants: ['user-other-token'],
				status: 'running',
				currentRunId: 'run-1',
				lastTurnIndex: 1
			})
		}));

		const res = mockRes();
		await agentCancel(authedCancel('sess-1'), res);

		assert.equal(res._status, 403);
		assert.equal(res._json.error, 'not_participant');
		assert.equal(mockDb.update.mock.callCount(), 0);
	});

	it('does not cancel queued pre-handoff turns', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				participants: ['user-good-token'],
				status: 'queued',
				currentRunId: 'run-1',
				lastTurnIndex: 1
			})
		}));

		const res = mockRes();
		await agentCancel(authedCancel('sess-1'), res);

		assert.equal(res._status, 409);
		assert.equal(res._json.error, 'cancel_not_started');
		assert.equal(mockDb.update.mock.callCount(), 0);
	});

	it('does not cancel when the requested run/turn is no longer current', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				participants: ['user-good-token'],
				status: 'running',
				currentRunId: 'run-2',
				lastTurnIndex: 3
			})
		}));

		const res = mockRes();
		await agentCancel(authedCancel('sess-1', { body: { runId: 'run-1', turnIndex: 2 } }), res);

		assert.equal(res._status, 409);
		assert.equal(res._json.error, 'cancel_target_mismatch');
		assert.equal(mockDb.update.mock.callCount(), 0);
	});

	it('marks the active turn stopped and clears the current run fence', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => {
			if (ref._path === 'sessions/sess-1') {
				return {
					exists: true,
					data: () => ({
						participants: ['user-good-token'],
						status: 'running',
						currentRunId: 'run-1',
						lastTurnIndex: 2
					})
				};
			}
			if (ref._path === 'sessions/sess-1/turns/0002') {
				return {
					exists: true,
					data: () => ({
						runId: 'run-1',
						status: 'running'
					})
				};
			}
			return defaultAccountDoc(ref) ?? { exists: false };
		});

		const res = mockRes();
		await agentCancel(authedCancel('sess-1', { body: { turnIndex: 2 } }), res);

		assert.equal(res._status, 200);
		assert.equal(res._json.ok, true);
		const sessionUpdate = mockDb.update.mock.calls.find(
			(c) => c.arguments[0]?._path === 'sessions/sess-1'
		).arguments[1];
		assert.equal(sessionUpdate.status, 'error');
		assert.equal(sessionUpdate.error, 'user_cancelled');
		assert.deepEqual(sessionUpdate.currentRunId, { __delete: true });
		assert.deepEqual(sessionUpdate.activeAgent, { __delete: true });
		const turnUpdate = mockDb.update.mock.calls.find(
			(c) => c.arguments[0]?._path === 'sessions/sess-1/turns/0002'
		).arguments[1];
		assert.equal(turnUpdate.status, 'error');
		assert.equal(turnUpdate.error, 'user_cancelled');
		assert.equal(turnUpdate.completedAt, '__server_timestamp__');
	});

	it('is idempotent once the session is already terminal', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				participants: ['user-good-token'],
				status: 'error',
				error: 'user_cancelled'
			})
		}));

		const res = mockRes();
		await agentCancel(authedCancel('sess-1'), res);

		assert.equal(res._status, 200);
		assert.deepEqual(res._json, { ok: true, terminal: true });
		assert.equal(mockDb.update.mock.callCount(), 0);
	});

	it('rejects anonymous Firebase tokens with 401 AUTH_REQUIRED', async () => {
		const res = mockRes();
		await agentCancel(
			authedCancel('sess-1', { headers: { authorization: 'Bearer anon-leftover-token' } }),
			res
		);
		assert.equal(res._status, 401);
		assert.equal(res._json.error, 'AUTH_REQUIRED');
		assert.equal(mockDb.update.mock.callCount(), 0);
	});
});

// ══════════════════════════════════════════════════════
// agentFeedback
// ══════════════════════════════════════════════════════

describe('agentFeedback', () => {
	function sessionGet(participants = ['user-good-token'], turnExists = true) {
		mockDb.get.mock.mockImplementation(async (ref) => {
			if (ref._path === 'sessions/sess-1') {
				return { exists: true, data: () => ({ participants }) };
			}
			if (ref._path.startsWith('sessions/sess-1/turns/')) {
				return { exists: turnExists, data: () => ({ status: 'complete' }) };
			}
			return defaultAccountDoc(ref) ?? { exists: false };
		});
	}

	function feedbackRow() {
		return mockDb.set.mock.calls.find((c) => c.arguments[0]?._path.startsWith('feedback/'))
			?.arguments[1];
	}

	function authed(body, overrides = {}) {
		return mockReq({
			method: 'POST',
			body: { sid: 'sess-1', turnIndex: 1, ...body },
			headers: { authorization: 'Bearer good-token', ...(overrides.headers || {}) }
		});
	}

	function writtenAt(path) {
		return mockDb.set.mock.calls.find((c) => c.arguments[0]?._path === path)?.arguments[1];
	}

	it('rejects non-POST with 405', async () => {
		const res = mockRes();
		await agentFeedback(mockReq({ method: 'GET' }), res);
		assert.equal(res._status, 405);
	});

	it('requires an Authorization header', async () => {
		const res = mockRes();
		await agentFeedback(mockReq({ method: 'POST', body: { sid: 'sess-1' } }), res);
		assert.equal(res._status, 401);
	});

	it('rejects anonymous Firebase tokens with 401 AUTH_REQUIRED', async () => {
		const res = mockRes();
		await agentFeedback(
			authed({ kind: 'rating', rating: 'up' }, { headers: { authorization: 'Bearer anon-x' } }),
			res
		);
		assert.equal(res._status, 401);
		assert.equal(res._json.error, 'AUTH_REQUIRED');
	});

	it('400s on an unknown kind', async () => {
		const res = mockRes();
		await agentFeedback(authed({ kind: 'nope' }), res);
		assert.equal(res._status, 400);
		assert.equal(res._json.error, 'unknown_kind');
	});

	it('404s when the session does not exist', async () => {
		mockDb.get.mock.mockImplementation(async (ref) => defaultAccountDoc(ref) ?? { exists: false });
		const res = mockRes();
		await agentFeedback(authed({ kind: 'rating', rating: 'up' }), res);
		assert.equal(res._status, 404);
	});

	it('403s when the caller is not a participant', async () => {
		sessionGet(['user-other-token']);
		const res = mockRes();
		await agentFeedback(authed({ kind: 'rating', rating: 'up' }), res);
		assert.equal(res._status, 403);
		assert.equal(res._json.error, 'not_participant');
		assert.equal(mockDb.set.mock.callCount(), 0);
	});

	it('writes only the rating to the turn doc (no reasons/note leak there)', async () => {
		sessionGet();
		const res = mockRes();
		await agentFeedback(authed({ kind: 'rating', rating: 'up' }), res);
		assert.equal(res._status, 200);
		assert.equal(res._json.ok, true);
		const entry = writtenAt('sessions/sess-1/turns/0001').feedback['user-good-token'];
		assert.deepEqual(Object.keys(entry).sort(), ['at', 'rating']);
		assert.equal(entry.rating, 'up');
		assert.equal(entry.at, '__server_timestamp__');
		// A bare 👍 records no private row.
		assert.equal(feedbackRow(), undefined);
	});

	it('404s when the turn does not exist (no phantom turn doc)', async () => {
		sessionGet(['user-good-token'], false);
		const res = mockRes();
		await agentFeedback(authed({ kind: 'rating', rating: 'up' }), res);
		assert.equal(res._status, 404);
		assert.equal(res._json.error, 'turn_not_found');
		assert.equal(mockDb.set.mock.callCount(), 0);
	});

	it('keeps 👎 reasons + note in the private feedback collection, not the turn', async () => {
		sessionGet();
		const res = mockRes();
		await agentFeedback(
			authed({
				turnIndex: 2,
				kind: 'rating',
				rating: 'down',
				reasons: ['Inaccurate', 'Wrong sources'],
				note: '  too vague  '
			}),
			res
		);
		assert.equal(res._status, 200);
		const entry = writtenAt('sessions/sess-1/turns/0002').feedback['user-good-token'];
		assert.equal(entry.rating, 'down');
		assert.equal(entry.reasons, undefined);
		assert.equal(entry.note, undefined);
		const row = feedbackRow();
		assert.equal(row.kind, 'rating');
		assert.equal(row.rating, 'down');
		assert.deepEqual(row.reasons, ['Inaccurate', 'Wrong sources']);
		assert.equal(row.note, 'too vague');
		assert.equal(row.turnIndex, 2);
	});

	it('400s on an invalid rating', async () => {
		sessionGet();
		const res = mockRes();
		await agentFeedback(authed({ kind: 'rating', rating: 'meh' }), res);
		assert.equal(res._status, 400);
	});

	it('appends a "yes" survey response to the feedback collection', async () => {
		sessionGet();
		const res = mockRes();
		await agentFeedback(authed({ kind: 'survey', useful: 'yes' }), res);
		assert.equal(res._status, 200);
		const row = feedbackRow();
		assert.ok(row, 'expected a write to the feedback collection');
		assert.equal(row.kind, 'survey');
		assert.equal(row.uid, 'user-good-token');
		assert.equal(row.sid, 'sess-1');
		assert.equal(row.useful, 'yes');
		assert.deepEqual(row.reasons, []);
		assert.equal(row.createdAt, '__server_timestamp__');
	});

	it('keeps "no" survey reasons + note in the feedback collection', async () => {
		sessionGet();
		const res = mockRes();
		await agentFeedback(
			authed({ kind: 'survey', useful: 'no', reasons: ['Incomplete'], note: '  too thin  ' }),
			res
		);
		assert.equal(res._status, 200);
		const row = feedbackRow();
		assert.equal(row.useful, 'no');
		assert.deepEqual(row.reasons, ['Incomplete']);
		assert.equal(row.note, 'too thin');
	});

	it('400s on an invalid survey answer', async () => {
		sessionGet();
		const res = mockRes();
		await agentFeedback(authed({ kind: 'survey', useful: 'maybe' }), res);
		assert.equal(res._status, 400);
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

	it('rejects anonymous Firebase tokens with 401 AUTH_REQUIRED', async () => {
		const res = mockRes();
		await agentDelete(
			authedDelete('sess-1', { headers: { authorization: 'Bearer anon-leftover-token' } }),
			res
		);
		assert.equal(res._status, 401);
		assert.equal(res._json.error, 'AUTH_REQUIRED');
		assert.equal(mockDb.recursiveDelete.mock.callCount(), 0);
	});
});

// ══════════════════════════════════════════════════════
// sendMagicLink
// ══════════════════════════════════════════════════════

describe('sendMagicLink', () => {
	it('generates an action link and sends it via Resend', async () => {
		const fetches = [];
		globalThis.fetch = mock.fn(async (url, init) => {
			fetches.push({ url, init });
			return { ok: true, status: 200, text: async () => '', json: async () => ({}) };
		});

		const res = mockRes();
		await sendMagicLink(
			mockReq({
				method: 'POST',
				body: { email: 'me@example.com', returnTo: '/chat?sid=abc' },
				ip: '127.9.9.1'
			}),
			res
		);

		assert.equal(res._status, 200);
		assert.equal(res._json.ok, true);
		assert.equal(authInstance.generateSignInWithEmailLink.mock.callCount(), 1);
		const generateArgs = authInstance.generateSignInWithEmailLink.mock.calls[0].arguments;
		assert.equal(generateArgs[0], 'me@example.com');
		assert.equal(generateArgs[1].handleCodeInApp, true);
		// returnTo flows into the actionCodeSettings url
		assert.ok(generateArgs[1].url.includes('returnTo='));
		assert.equal(fetches.length, 1);
		assert.match(fetches[0].url, /api\.resend\.com\/emails/);
	});

	it('rejects malformed email addresses', async () => {
		const res = mockRes();
		await sendMagicLink(
			mockReq({ method: 'POST', body: { email: 'not-an-email' }, ip: '127.9.9.2' }),
			res
		);
		assert.equal(res._status, 400);
		assert.equal(res._json.error, 'Valid email is required');
	});

	it('rejects protocol-relative returnTo to prevent open-redirect', async () => {
		globalThis.fetch = mock.fn(async () => ({
			ok: true,
			status: 200,
			text: async () => '',
			json: async () => ({})
		}));

		const res = mockRes();
		await sendMagicLink(
			mockReq({
				method: 'POST',
				body: { email: 'me@example.com', returnTo: '//evil.example.com/' },
				ip: '127.9.9.3'
			}),
			res
		);
		assert.equal(res._status, 200);
		// Bad returnTo gets stripped — generated url should NOT carry returnTo.
		const generateArgs = authInstance.generateSignInWithEmailLink.mock.calls[0].arguments;
		assert.ok(
			!generateArgs[1].url.includes('returnTo='),
			'expected returnTo to be omitted for unsafe values'
		);
	});
});
