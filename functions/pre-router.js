import { GoogleAuth } from 'google-auth-library';

const VERTEX_BASE = 'https://aiplatform.googleapis.com';
const MODEL = 'gemini-2.5-flash';
const FALLBACK_QUESTION = 'Which restaurant, street, neighborhood, city, or market should I check?';

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
				'Decide whether the latest message supplies enough restaurant, address, area, market, or geography to research the original question.',
				'If the latest message names a restaurant or venue plus broad geography, treat it as a proposed restaurant or venue focus, not as a pure geography answer.',
				'If the latest message includes an exact address, street name, street-level location, or branch descriptor, treat that as enough branch-level scope.',
				'If the original question had missing self-referential geography and the latest answer names a restaurant or venue without branch-level scope, return clarify even when the answer includes a city.'
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
		'- Research when the message supplies a usable scope for the question: exact address, branch or venue, neighborhood, district, borough, city, region, country, market, or broad industry scope.',
		'- Research broad restaurant-industry questions that do not depend on a specific local market, such as format shifts, consumer behavior, concept trends, channel trends, or category-level strategy. Do not ask for geography only because geography could make the answer more specific.',
		'- For market-level salary, wage, rent, regulation, saturation, delivery, local competition, openings, and closures questions, a named city, region, state, or country is enough geography to research.',
		'- Branch-proximity requests need branch-level scope. These include questions about what is near or around one venue, nearby competitors, nearby openings or closures, local momentum, delivery competition around a venue, or venue-specific pricing.',
		'- Branch-level scope means a selected Google Place ID, exact address, street name, street-level location, neighborhood or district that anchors the venue, or explicit branch descriptor. A chain or brand name plus only a broad city, region, state, or country is not branch-level scope.',
		'- A restaurant or venue name plus an exact address, street name, or street-level location is enough branch-level scope.',
		'- For branch-proximity requests, a restaurant or venue name plus only a city, region, state, or country is not branch-level scope when the name could be a chain or brand. Do not pick or infer one branch.',
		'- When the user is answering a missing-area clarification, a restaurant or venue answer makes local openings, closures, nearby competitors, or nearby momentum a branch-proximity request around that venue. Do not reinterpret that answer as citywide geography.',
		'- Do not clarify just because a named city, neighborhood, venue, or market could have multiple interpretations. Clarify only when the missing distinction is needed to answer the question.',
		'- Clarify by default when the request depends on place, restaurant identity, local market, nearby competitors, wages/labor costs, rent, regulation, openings/closures, pricing for a specific operation, delivery competition, or customer sentiment, and no usable place, area, market, city, neighborhood, venue, address, or country is named.',
		'- Self-referential phrases like "my", "our", "my area", "in my area", "near me", "near us", "nearby", "local", "competitors", "recent openings", and "recent closures" are not usable geography by themselves.',
		'- Salary/wage, rent, regulation, saturation, and local competition questions are not broad enough when no geography is named.',
		'- The question must be one short question asking for the missing restaurant, street, neighborhood, city, area, or market.',
		'- The reason must be a short snake_case reason code.'
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
				responseSchema: {
					type: 'OBJECT',
					properties: {
						decision: { type: 'STRING', enum: ['clarify', 'research'] },
						question: { type: 'STRING' },
						reason: { type: 'STRING' }
					},
					required: ['decision', 'reason'],
					propertyOrdering: ['decision', 'question', 'reason']
				},
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
