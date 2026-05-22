import { describe, it, mock, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

const getAccessTokenMock = mock.fn(async () => ({ token: 'test-token' }));
const getClientMock = mock.fn(async () => ({ getAccessToken: getAccessTokenMock }));

mock.module('google-auth-library', {
	namedExports: {
		GoogleAuth: class {
			getClient() {
				return getClientMock();
			}
		}
	}
});

const {
	buildClarificationGatePrompt,
	parseClarificationGateResponse,
	runClarificationGate,
	shouldRunClarificationGate
} = await import('./pre-router.js');

let originalFetch;
let originalProject;

beforeEach(() => {
	originalFetch = globalThis.fetch;
	originalProject = process.env.GOOGLE_CLOUD_PROJECT;
	process.env.GOOGLE_CLOUD_PROJECT = 'superextra-site';
	getAccessTokenMock.mock.resetCalls();
	getClientMock.mock.resetCalls();
});

afterEach(() => {
	globalThis.fetch = originalFetch;
	if (originalProject === undefined) {
		delete process.env.GOOGLE_CLOUD_PROJECT;
	} else {
		process.env.GOOGLE_CLOUD_PROJECT = originalProject;
	}
});

describe('shouldRunClarificationGate', () => {
	it('runs only for the first Engine turn without selected focus', () => {
		assert.equal(
			shouldRunClarificationGate({ isEngineFirstMessage: true, placeContext: null }),
			true
		);
		assert.equal(
			shouldRunClarificationGate({
				isEngineFirstMessage: true,
				placeContext: { name: 'Joe', secondary: 'NYC', placeId: 'p1' }
			}),
			false
		);
		assert.equal(
			shouldRunClarificationGate({ isEngineFirstMessage: false, placeContext: null }),
			false
		);
	});
});

describe('buildClarificationGatePrompt', () => {
	it('marks self-referential local phrases as missing geography', () => {
		const prompt = buildClarificationGatePrompt({
			message: 'What has opened or closed in my area recently?'
		});
		assert.match(prompt, /"my area"/);
		assert.match(prompt, /openings\/closures/);
		assert.match(prompt, /not usable geography/);
	});

	it('includes the original question for clarification follow-ups', () => {
		const prompt = buildClarificationGatePrompt({
			message: 'Williamsburg, Brooklyn',
			originalQuestion: 'What has opened or closed in my area recently?'
		});
		assert.match(prompt, /answering a prior clarification/);
		assert.match(prompt, /Original question/);
		assert.match(prompt, /Latest message/);
	});
});

describe('parseClarificationGateResponse', () => {
	it('normalizes clarify responses', () => {
		assert.deepEqual(
			parseClarificationGateResponse(
				'{"decision":"clarify","question":"What area should I use?","reason":"missing"}'
			),
			{ decision: 'clarify', question: 'What area should I use?', reason: 'missing' }
		);
	});

	it('fails open to research on malformed model output', () => {
		assert.deepEqual(parseClarificationGateResponse('not json'), {
			decision: 'research',
			question: null,
			reason: 'invalid_json'
		});
	});
});

describe('runClarificationGate', () => {
	it('calls Vertex with JSON output and thinking disabled', async () => {
		globalThis.fetch = mock.fn(async () => ({
			ok: true,
			json: async () => ({
				candidates: [
					{
						content: {
							parts: [
								{
									text: '{"decision":"clarify","question":"What area should I use?","reason":"missing"}'
								}
							]
						}
					}
				]
			})
		}));

		const result = await runClarificationGate({
			message: 'What has opened or closed in my area recently?'
		});

		assert.equal(result.decision, 'clarify');
		assert.equal(result.question, 'What area should I use?');
		assert.equal(globalThis.fetch.mock.callCount(), 1);
		const [url, init] = globalThis.fetch.mock.calls[0].arguments;
		assert.match(
			url,
			/locations\/global\/publishers\/google\/models\/gemini-2\.5-flash:generateContent$/
		);
		assert.equal(init.headers.Authorization, 'Bearer test-token');
		const body = JSON.parse(init.body);
		assert.equal(body.generationConfig.responseMimeType, 'application/json');
		assert.equal(body.generationConfig.thinkingConfig.thinkingBudget, 0);
		assert.equal(body.generationConfig.maxOutputTokens, 180);
	});
});
