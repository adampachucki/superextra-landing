import { describe, it, mock, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

// ── Mock external modules before importing index.js ──

const mockDb = {
	collection: () => mockDb,
	doc: () => mockDb,
	get: mock.fn(async () => ({ exists: false })),
	set: mock.fn(async () => {})
};

mock.module('firebase-admin/app', {
	namedExports: { initializeApp: mock.fn() }
});
mock.module('firebase-admin/firestore', {
	namedExports: { getFirestore: mock.fn(() => mockDb) }
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
mock.module('@google-cloud/vertexai', {
	namedExports: {
		VertexAI: class {
			getGenerativeModel() {
				return {
					generateContent: async () => ({
						response: {
							candidates: [{ content: { parts: [{ text: 'Test Title' }] } }]
						}
					})
				};
			}
		}
	}
});
mock.module('google-auth-library', {
	namedExports: {
		GoogleAuth: class {
			async getIdTokenClient() {
				return { getRequestHeaders: async () => ({ Authorization: 'Bearer mock-token' }) };
			}
		}
	}
});

const { intake, agent, agentStream, agentCheck, sttToken, tts } = await import('./index.js');

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
// agent
// ══════════════════════════════════════════════════════

describe('agent', () => {
	it('rejects non-POST with 405', async () => {
		const res = mockRes();
		await agent(mockReq({ method: 'GET' }), res);
		assert.equal(res._status, 405);
	});

	it('returns 400 when message or sessionId missing', async () => {
		const res = mockRes();
		await agent(mockReq({ body: { message: 'hi' } }), res);
		assert.equal(res._status, 400);

		const res2 = mockRes();
		await agent(mockReq({ body: { sessionId: 'abc' } }), res2);
		assert.equal(res2._status, 400);
	});

	it('returns 400 when message exceeds 2000 chars', async () => {
		const res = mockRes();
		await agent(mockReq({ body: { message: 'a'.repeat(2001), sessionId: 'test' } }), res);
		assert.equal(res._status, 400);
		assert.match(res._json.error, /too long/i);
	});

	it('returns reply on success (new session)', async () => {
		let fetchCallCount = 0;
		globalThis.fetch = mock.fn(async (url) => {
			fetchCallCount++;
			// 1st call: create session
			if (url.includes('/sessions') && !url.includes('/run_sse')) {
				return {
					ok: true,
					json: async () => ({ id: 'adk-session-1' })
				};
			}
			// 2nd call: run_sse
			if (url.includes('/run_sse')) {
				const sseBody = [
					'data: {"actions":{"state_delta":{"final_report":"Here is the report."}}}',
					''
				].join('\n');
				return { ok: true, text: async () => sseBody };
			}
			return { ok: true, json: async () => ({}) };
		});

		const res = mockRes();
		await agent(
			mockReq({ body: { message: 'Tell me about this place', sessionId: 'sess-1' } }),
			res
		);
		assert.equal(res._json.ok, true);
		assert.equal(res._json.reply, 'Here is the report.');
	});

	it('returns 502 when session creation fails', async () => {
		globalThis.fetch = mock.fn(async (url) => {
			if (url.includes('/sessions')) {
				return { ok: false, status: 500 };
			}
			return { ok: true };
		});

		const res = mockRes();
		await agent(mockReq({ body: { message: 'hi', sessionId: 'new-sess' } }), res);
		assert.equal(res._status, 502);
	});
});

// ══════════════════════════════════════════════════════
// agentStream
// ══════════════════════════════════════════════════════

describe('agentStream', () => {
	it('rejects non-POST with 405', async () => {
		const res = mockRes();
		await agentStream(mockReq({ method: 'GET' }), res);
		assert.equal(res._status, 405);
	});

	it('returns 400 when message or sessionId missing', async () => {
		const res = mockRes();
		await agentStream(mockReq({ body: { message: 'hi' } }), res);
		assert.equal(res._status, 400);
	});

	it('writes SSE headers and streams events on success', async () => {
		// Simulate a readable stream from ADK
		function makeReadableStream(chunks) {
			let index = 0;
			return {
				getReader() {
					return {
						async read() {
							if (index >= chunks.length) return { done: true, value: undefined };
							return { done: false, value: new TextEncoder().encode(chunks[index++]) };
						}
					};
				}
			};
		}

		globalThis.fetch = mock.fn(async (url) => {
			if (url.includes('/sessions') && !url.includes('/run_sse')) {
				return { ok: true, json: async () => ({ id: 'adk-stream-1' }) };
			}
			if (url.includes('/run_sse')) {
				const chunk =
					'data: {"content":{"parts":[{"text":"Hello"}]},"actions":{"state_delta":{"final_report":"Full report here."}}}\n\n';
				return {
					ok: true,
					body: makeReadableStream([chunk])
				};
			}
			// Session state fetch for sources fallback
			return { ok: true, json: async () => ({ state: {} }) };
		});

		const res = mockRes();
		await agentStream(mockReq({ body: { message: 'test', sessionId: 'stream-sess' } }), res);

		// Should have written SSE headers
		assert.equal(res._status, 200);
		assert.equal(res._headers['Content-Type'], 'text/event-stream');
		// Should have written `: ok\n\n` first
		assert.ok(res._written.some((w) => w.includes(': ok')));
		// Should have ended with a complete event
		assert.ok(res._written.some((w) => w.includes('event: complete')));
		assert.ok(res._ended);
	});
});

// ══════════════════════════════════════════════════════
// agentCheck
// ══════════════════════════════════════════════════════

describe('agentCheck', () => {
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

	it('returns session_not_found when session does not exist', async () => {
		mockDb.get.mock.mockImplementation(async () => ({ exists: false }));

		const res = mockRes();
		await agentCheck(mockReq({ method: 'GET', query: { sid: 'unknown' } }), res);
		assert.equal(res._json.ok, false);
		assert.equal(res._json.reason, 'session_not_found');
	});

	it('returns complete reply when session has final_report', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				adkSessionId: 'adk-1',
				userId: 'user-1',
				createdAt: Date.now()
			})
		}));

		globalThis.fetch = mock.fn(async () => ({
			ok: true,
			json: async () => ({
				state: { final_report: 'The final report.' }
			})
		}));

		const res = mockRes();
		await agentCheck(mockReq({ method: 'GET', query: { sid: 'known' } }), res);
		assert.equal(res._json.ok, true);
		assert.equal(res._json.reply, 'The final report.');
		assert.equal(res._json.status, 'complete');
	});

	it('returns processing when reply not ready yet', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				adkSessionId: 'adk-1',
				userId: 'user-1',
				createdAt: Date.now()
			})
		}));

		globalThis.fetch = mock.fn(async () => ({
			ok: true,
			json: async () => ({ state: {} })
		}));

		const res = mockRes();
		await agentCheck(mockReq({ method: 'GET', query: { sid: 'pending' } }), res);
		assert.equal(res._json.ok, true);
		assert.equal(res._json.status, 'processing');
		assert.equal(res._json.reply, null);
	});

	it('returns timed_out for old sessions without reply', async () => {
		mockDb.get.mock.mockImplementation(async () => ({
			exists: true,
			data: () => ({
				adkSessionId: 'adk-1',
				userId: 'user-1',
				createdAt: Date.now() - 10 * 60 * 1000 // 10 minutes ago
			})
		}));

		globalThis.fetch = mock.fn(async () => ({
			ok: true,
			json: async () => ({ state: {} })
		}));

		const res = mockRes();
		await agentCheck(mockReq({ method: 'GET', query: { sid: 'old' } }), res);
		assert.equal(res._json.ok, false);
		assert.equal(res._json.reason, 'timed_out');
	});
});
