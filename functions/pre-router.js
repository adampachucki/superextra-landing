import { GoogleAuth } from 'google-auth-library';

const VERTEX_BASE = 'https://aiplatform.googleapis.com';
const MODEL = 'gemini-2.5-flash';
const FALLBACK_QUESTION = 'What restaurant, address, area, or market should I use?';

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

function _projectId() {
	return process.env.GOOGLE_CLOUD_PROJECT || process.env.GCLOUD_PROJECT || 'superextra-site';
}

export function shouldRunClarificationGate({ isEngineFirstMessage, placeContext }) {
	return isEngineFirstMessage && !(placeContext && placeContext.name);
}

export function buildClarificationGatePrompt({ message, originalQuestion = null }) {
	const mode = originalQuestion
		? [
				'The user is answering a prior clarification.',
				`Original question: ${JSON.stringify(originalQuestion)}`,
				`Latest message: ${JSON.stringify(message)}`,
				'Decide whether the latest message supplies enough restaurant, address, area, market, or geography to research the original question.'
			].join('\n')
		: [
				'Input is the first user message in a new chat.',
				`User message: ${JSON.stringify(message)}`
			].join('\n');

	return [
		'You are a clarification gate for Superextra, a restaurant market-intelligence agent.',
		'There is no selected focus, no saved account venue, and no saved market unless explicitly stated in the input.',
		'',
		mode,
		'',
		'Return JSON only: {"decision":"clarify"|"research","question":"...","reason":"..."}.',
		'',
		'Decision rules:',
		'- Research when the message names any ordinary city, neighborhood, borough, district, country, address, restaurant, venue, or market. Do not ask which one just because a place name could be ambiguous.',
		'- Research broad restaurant-industry questions that do not depend on a specific local market, such as format shifts, consumer behavior, concept trends, channel trends, or category-level strategy. Do not ask for geography only because geography could make the answer more specific.',
		'- For salary, wage, rent, regulation, saturation, delivery, and local competition questions, a named city, region, state, or country is enough geography to research. Do not ask for a narrower area inside the named geography.',
		'- Clarify by default when the request depends on place, restaurant identity, local market, nearby competitors, wages/labor costs, rent, regulation, openings/closures, pricing for a specific operation, delivery competition, or customer sentiment, and no usable place, area, market, city, neighborhood, venue, address, or country is named.',
		'- Self-referential phrases like "my", "our", "my area", "in my area", "near me", "near us", "nearby", "local", "competitors", "recent openings", and "recent closures" are not usable geography by themselves.',
		'- Salary/wage, rent, regulation, saturation, and local competition questions are not broad enough when no geography is named.',
		'- The question must be one short question asking for the missing restaurant, address, area, or market.'
	].join('\n');
}

export function parseClarificationGateResponse(text) {
	let parsed;
	try {
		parsed = JSON.parse(text);
	} catch {
		return { decision: 'research', question: null, reason: 'invalid_json' };
	}

	if (parsed?.decision !== 'clarify') {
		return {
			decision: 'research',
			question: null,
			reason: typeof parsed?.reason === 'string' ? parsed.reason : null
		};
	}

	const question =
		typeof parsed.question === 'string' && parsed.question.trim()
			? parsed.question.trim()
			: FALLBACK_QUESTION;

	return {
		decision: 'clarify',
		question,
		reason: typeof parsed.reason === 'string' ? parsed.reason : null
	};
}

export async function runClarificationGate({ message, originalQuestion = null }) {
	const token = await _getToken();
	const url = `${VERTEX_BASE}/v1/projects/${_projectId()}/locations/global/publishers/google/models/${MODEL}:generateContent`;
	const response = await fetch(url, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${token}`,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			contents: [
				{
					role: 'user',
					parts: [{ text: buildClarificationGatePrompt({ message, originalQuestion }) }]
				}
			],
			generationConfig: {
				temperature: 0,
				maxOutputTokens: 180,
				responseMimeType: 'application/json',
				thinkingConfig: { thinkingBudget: 0 }
			}
		})
	});

	if (!response.ok) {
		const body = await response.text().catch(() => '');
		throw new Error(`clarification_gate_failed:${response.status}:${body.slice(0, 200)}`);
	}

	const payload = await response.json();
	const text =
		payload?.candidates?.[0]?.content?.parts
			?.map((part) => (typeof part.text === 'string' ? part.text : ''))
			.join('')
			.trim() || '';

	return parseClarificationGateResponse(text);
}
