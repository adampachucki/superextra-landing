import { generateGeminiJson } from './gemini-json.js';

const PLACES_TEXT_SEARCH_URL = 'https://places.googleapis.com/v1/places:searchText';
const TEXT_SEARCH_FIELDS = [
	'places.id',
	'places.displayName',
	'places.formattedAddress',
	'places.primaryType',
	'places.types'
].join(',');

const SCOPE_SCHEMA = {
	type: 'OBJECT',
	properties: {
		scopeType: { type: 'STRING', enum: ['place', 'area', 'market', 'none'] },
		placesQuery: { type: 'STRING' },
		needsPlacesLookup: { type: 'BOOLEAN' },
		reason: { type: 'STRING' }
	},
	required: ['scopeType', 'needsPlacesLookup', 'reason'],
	propertyOrdering: ['scopeType', 'placesQuery', 'needsPlacesLookup', 'reason']
};

const CANDIDATE_SCHEMA = {
	type: 'OBJECT',
	properties: {
		action: { type: 'STRING', enum: ['accept_place', 'ask_user', 'no_match'] },
		candidateIndex: { type: 'INTEGER' },
		question: { type: 'STRING' },
		reason: { type: 'STRING' }
	},
	required: ['action', 'reason'],
	propertyOrdering: ['action', 'candidateIndex', 'question', 'reason']
};

export function buildScopePrompt({
	message,
	originalQuestion = null,
	clarificationQuestion = null
}) {
	return [
		'You interpret a Superextra user message or a user answer to a prior location clarification.',
		'Work in the user language. Do not translate names unless the user already did.',
		'Extract the intended research scope; do not answer the research question.',
		'Use the latest answer first. If it is pushback, asks the system to infer or search, repeats earlier place wording, or otherwise does not introduce a new scope, inspect the original question and clarification question to recover the intended scope.',
		'',
		`Original question: ${JSON.stringify(originalQuestion || '')}`,
		`Clarification question: ${JSON.stringify(clarificationQuestion || '')}`,
		`Latest answer: ${JSON.stringify(message)}`,
		'',
		'Return JSON only.',
		'',
		'Rules:',
		'- If the latest answer or original question identifies a restaurant, venue, address, landmark, or branch to use as the anchor, return scopeType="place" and needsPlacesLookup=true.',
		'- For questions about what is around, near, nearby, opened, closed, competing with, delivering around, or changing around a named venue, treat the named venue as the intended place anchor.',
		'- placesQuery should be the clean Google Places lookup query: keep the venue/name/address/city/street/branch hints, remove conversational relationship words in any language such as "around", "near", or "in" unless they are part of the name.',
		'- If the answer is only a city, neighborhood, region, country, or market, return scopeType="area" or "market" and needsPlacesLookup=false.',
		'- Return scopeType="none" only when neither the latest answer nor original question provides a usable place, area, market, or geography.',
		'- reason must be a short snake_case reason code, not a sentence.',
		'- Never invent a Google Place ID.'
	].join('\n');
}

export function buildCandidatePrompt({
	message,
	originalQuestion = null,
	clarificationQuestion = null,
	placesQuery,
	candidates
}) {
	return [
		'You decide whether Google Places candidates identify the user intended anchor place.',
		'Return JSON only. Do not invent candidates or Place IDs.',
		'',
		`Original question: ${JSON.stringify(originalQuestion || '')}`,
		`Clarification question: ${JSON.stringify(clarificationQuestion || '')}`,
		`Latest answer: ${JSON.stringify(message)}`,
		`Places query: ${JSON.stringify(placesQuery)}`,
		`Candidates: ${JSON.stringify(candidates)}`,
		'',
		'Rules:',
		'- action="accept_place" only when one candidate clearly matches the intended restaurant, venue, branch, address, or landmark.',
		'- Accept a single clearly matching branch even when the user used relationship wording like around/near/in.',
		'- If the Places query came from the original question because the latest answer confirms, repeats, questions the need for clarification, or asks the system to infer, accept one clear candidate and ask only when multiple candidates remain plausible.',
		'- action="ask_user" when candidates contain multiple plausible branches or chain locations and the answer does not identify which one.',
		'- action="ask_user" when a specific branch is required but the candidates do not provide enough confidence.',
		'- action="no_match" when none of the candidates fit the user answer.',
		'- reason must be a short snake_case reason code, not a sentence.',
		'- If asking, write one short clarification question in the user language.'
	].join('\n');
}

function placeName(place) {
	return place?.displayName?.text || '';
}

function placeAddress(place) {
	return place?.formattedAddress || '';
}

function toPlaceContext(place) {
	const name = placeName(place).trim();
	const placeId = typeof place?.id === 'string' ? place.id.trim() : '';
	if (!name || !placeId) return null;
	return {
		name,
		secondary: placeAddress(place).trim(),
		placeId
	};
}

function toCandidate(place, index) {
	return {
		index,
		name: placeName(place),
		address: placeAddress(place),
		primaryType: typeof place?.primaryType === 'string' ? place.primaryType : '',
		types: Array.isArray(place?.types) ? place.types.filter((type) => typeof type === 'string') : []
	};
}

async function searchText({ query, apiKey, fetchImpl }) {
	const response = await fetchImpl(PLACES_TEXT_SEARCH_URL, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'X-Goog-Api-Key': apiKey,
			'X-Goog-FieldMask': TEXT_SEARCH_FIELDS
		},
		body: JSON.stringify({
			textQuery: query,
			pageSize: 5
		})
	});
	if (!response.ok) {
		const body = await response.text().catch(() => '');
		throw new Error(`places_text_search_failed:${response.status}:${body.slice(0, 160)}`);
	}
	const payload = await response.json();
	return Array.isArray(payload?.places) ? payload.places : [];
}

export async function resolveClarificationFocus({
	message,
	originalQuestion = null,
	clarificationQuestion = null,
	apiKey,
	fetchImpl = fetch,
	getToken
}) {
	const latestAnswer = String(message || '').trim();
	if (!latestAnswer || !apiKey) return null;

	const scope = await generateGeminiJson({
		prompt: buildScopePrompt({ message: latestAnswer, originalQuestion, clarificationQuestion }),
		responseSchema: SCOPE_SCHEMA,
		maxOutputTokens: 220,
		errorName: 'clarification_scope_model',
		fetchImpl,
		getToken
	});

	if (scope?.scopeType !== 'place' || scope.needsPlacesLookup !== true) return null;
	const placesQuery = typeof scope.placesQuery === 'string' ? scope.placesQuery.trim() : '';
	if (!placesQuery) return null;

	const places = await searchText({ query: placesQuery, apiKey, fetchImpl });
	const candidates = places
		.map((place, index) => ({
			place,
			context: toPlaceContext(place),
			candidate: toCandidate(place, index)
		}))
		.filter(({ context }) => context);
	if (!candidates.length) return null;

	const selection = await generateGeminiJson({
		prompt: buildCandidatePrompt({
			message: latestAnswer,
			originalQuestion,
			clarificationQuestion,
			placesQuery,
			candidates: candidates.map(({ candidate }) => candidate)
		}),
		responseSchema: CANDIDATE_SCHEMA,
		maxOutputTokens: 220,
		errorName: 'clarification_candidate_model',
		fetchImpl,
		getToken
	});

	if (selection?.action === 'accept_place' && Number.isInteger(selection.candidateIndex)) {
		const match = candidates.find(({ candidate }) => candidate.index === selection.candidateIndex);
		return match?.context || null;
	}

	if (selection?.action === 'ask_user') {
		const question = typeof selection.question === 'string' ? selection.question.trim() : '';
		if (question) {
			return {
				question,
				reason: typeof selection.reason === 'string' ? selection.reason : 'ambiguous_place'
			};
		}
	}

	return null;
}
