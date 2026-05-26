import { generateGeminiJson } from './gemini-json.js';

const PLACES_TEXT_SEARCH_URL = 'https://places.googleapis.com/v1/places:searchText';
const TEXT_SEARCH_FIELDS = [
	'places.id',
	'places.displayName',
	'places.formattedAddress',
	'places.primaryType',
	'places.types'
].join(',');

const MAX_TEXT = 900;
const MAX_CANDIDATES = 5;
const ACKNOWLEDGEMENT_TEXT_LIMIT = 320;
const FALLBACK_REPLY = 'Which restaurant, street, neighborhood, city, or market should I check?';

const INTAKE_STATE_SCHEMA = {
	type: 'OBJECT',
	properties: {
		summary: { type: 'STRING' },
		originalIntent: { type: 'STRING' },
		scopeSummary: { type: 'STRING' },
		pendingQuestion: { type: 'STRING' },
		candidateSet: { type: 'STRING', enum: ['keep', 'clear'] }
	},
	required: ['summary', 'originalIntent', 'scopeSummary', 'pendingQuestion', 'candidateSet'],
	propertyOrdering: ['summary', 'originalIntent', 'scopeSummary', 'pendingQuestion', 'candidateSet']
};

const SCOPE_KINDS = ['research_scope', 'anchor_place', 'candidate_selection', 'insufficient_scope'];

const INTAKE_SCHEMA = {
	type: 'OBJECT',
	properties: {
		action: { type: 'STRING', enum: ['reply', 'lookup_place', 'start_research'] },
		scopeKind: { type: 'STRING', enum: SCOPE_KINDS },
		reply: { type: 'STRING' },
		placesQuery: { type: 'STRING' },
		researchQuestion: { type: 'STRING' },
		placeId: { type: 'STRING' },
		acknowledgement: { type: 'STRING' },
		reason: { type: 'STRING' },
		state: INTAKE_STATE_SCHEMA
	},
	required: [
		'action',
		'scopeKind',
		'reply',
		'placesQuery',
		'researchQuestion',
		'placeId',
		'acknowledgement',
		'reason',
		'state'
	],
	propertyOrdering: [
		'action',
		'scopeKind',
		'reply',
		'placesQuery',
		'researchQuestion',
		'placeId',
		'acknowledgement',
		'reason',
		'state'
	]
};

function compact(text, max = MAX_TEXT) {
	return String(text || '')
		.trim()
		.replace(/\s+/g, ' ')
		.slice(0, max);
}

function compactReply(text, max = MAX_TEXT) {
	return String(text || '')
		.trim()
		.replace(/\r\n/g, '\n')
		.replace(/[ \t\f\v]+/g, ' ')
		.replace(/[ \t]*\n[ \t]*/g, '\n')
		.replace(/\n{3,}/g, '\n\n')
		.slice(0, max);
}

function compactUnique(values, max) {
	const seen = new Set();
	const out = [];
	for (const value of values) {
		const text = compact(value, max);
		const key = text.toLocaleLowerCase();
		if (!text || seen.has(key)) continue;
		seen.add(key);
		out.push(text);
	}
	return out;
}

function isUsableAcknowledgement(text) {
	const normalized = compact(text, ACKNOWLEDGEMENT_TEXT_LIMIT).toLocaleLowerCase();
	if (!normalized || normalized.includes('?')) return false;
	if (/\b(scopekind|tool result|placesquery|the models)\b/i.test(normalized)) return false;
	return true;
}

function acknowledgementFocus({ state, researchQuestion, placeContext, message }) {
	const placeFocus = compact(
		[placeContext?.name, placeContext?.secondary].filter(Boolean).join(', ')
	);
	const focus = compact(
		state?.scopeSummary || placeFocus || researchQuestion || state?.originalIntent || message,
		180
	).replace(/[.?!:;]+$/, '');
	return (focus || 'the restaurant market request').replace(
		/^(Area|Market|Question|Request|Analysis)\b/,
		(word) => word.toLocaleLowerCase()
	);
}

function fallbackAcknowledgement(context) {
	const focus = acknowledgementFocus(context);
	return `Reviewing ${focus}. The report will take a few minutes.`;
}

function normalizeAcknowledgement(acknowledgement, context) {
	const modelAcknowledgement = compact(acknowledgement, ACKNOWLEDGEMENT_TEXT_LIMIT);
	return isUsableAcknowledgement(modelAcknowledgement)
		? modelAcknowledgement
		: fallbackAcknowledgement(context);
}

function placeName(place) {
	return compact(place?.displayName?.text || place?.name || '', 180);
}

function placeAddress(place) {
	return compact(place?.formattedAddress || place?.address || place?.secondary || '', 260);
}

function normalizeCandidate(candidate, index) {
	const placeId = compact(candidate?.placeId || candidate?.id || '', 160);
	const name = placeName(candidate);
	if (!placeId || !name) return null;
	const optionNumber = Number.isInteger(candidate?.optionNumber)
		? candidate.optionNumber
		: index + 1;
	return {
		optionNumber,
		placeId,
		name,
		address: placeAddress(candidate),
		primaryType: compact(candidate?.primaryType || '', 80),
		types: Array.isArray(candidate?.types)
			? candidate.types.filter((type) => typeof type === 'string').slice(0, 8)
			: []
	};
}

function placesToCandidates(places) {
	return places
		.map((place, index) => normalizeCandidate(place, index))
		.filter(Boolean)
		.slice(0, MAX_CANDIDATES)
		.map((candidate, index) => ({ ...candidate, optionNumber: index + 1 }));
}

export function normalizeIntakeState(input) {
	if (!input || typeof input !== 'object') return null;
	const candidates = Array.isArray(input.candidates)
		? input.candidates
				.map((candidate, index) => normalizeCandidate(candidate, index))
				.filter(Boolean)
				.slice(0, MAX_CANDIDATES)
				.map((candidate, index) => ({ ...candidate, optionNumber: index + 1 }))
		: [];
	const state = {
		summary: compact(input.summary),
		originalIntent: compact(input.originalIntent),
		scopeSummary: compact(input.scopeSummary),
		pendingQuestion: compact(input.pendingQuestion),
		candidates
	};
	if (
		!state.summary &&
		!state.originalIntent &&
		!state.scopeSummary &&
		!state.pendingQuestion &&
		!state.candidates.length
	) {
		return null;
	}
	return state;
}

function mergeState({ modelState, previousState, candidates = null }) {
	const previous = normalizeIntakeState(previousState) || {
		summary: '',
		originalIntent: '',
		scopeSummary: '',
		pendingQuestion: '',
		candidates: []
	};
	const clearCandidates = modelState?.candidateSet === 'clear';
	const next = {
		summary: compact(modelState?.summary || previous.summary),
		originalIntent: compact(modelState?.originalIntent || previous.originalIntent),
		scopeSummary: compact(modelState?.scopeSummary || previous.scopeSummary),
		pendingQuestion: compact(modelState?.pendingQuestion || ''),
		candidates: candidates ?? (clearCandidates ? [] : previous.candidates)
	};
	return normalizeIntakeState(next);
}

function candidateToPlaceContext(candidate) {
	if (!candidate) return null;
	return {
		name: candidate.name,
		secondary: candidate.address,
		placeId: candidate.placeId
	};
}

function comparable(text) {
	return compact(text, 500)
		.toLocaleLowerCase()
		.normalize('NFKD')
		.replace(/[\u0300-\u036f]/g, '')
		.replace(/[^\p{L}\p{N}]+/gu, ' ')
		.trim();
}

function resolvePlaceContext({ placeId, selectedPlaceContext, state }) {
	const requested = compact(placeId, 160);
	if (!requested) return null;
	if (selectedPlaceContext?.placeId === requested) return selectedPlaceContext;
	const candidates = state?.candidates || [];
	const candidate =
		candidates.find((item) => item.placeId === requested) ||
		candidates.find((item) => String(item.optionNumber) === requested) ||
		candidates.find((item) => {
			const needle = comparable(requested);
			if (needle.length < 3) return false;
			return comparable(`${item.name} ${item.address}`).includes(needle);
		});
	return candidateToPlaceContext(candidate);
}

function stateForCandidateResolution(state, previousState) {
	const previous = normalizeIntakeState(previousState);
	if (state?.candidates?.length || !previous?.candidates?.length) return state;
	return {
		...(state || previous),
		candidates: previous.candidates
	};
}

function compactHistory(history) {
	return (Array.isArray(history) ? history : [])
		.map((item) => ({
			role: item?.role === 'assistant' ? 'assistant' : 'user',
			text: compact(item?.text)
		}))
		.filter((item) => item.text)
		.slice(-12);
}

export function buildIntakePrompt({
	history,
	message,
	intakeState = null,
	selectedPlaceContext = null,
	toolResult = null
}) {
	return [
		'You are Superextra intake, the fast conversation layer before restaurant market research.',
		'Help the user reach a research-ready request. Do not research, browse, or answer the business question.',
		'Use the conversation naturally. Do not assume fixed rounds or that the latest message only answers the previous question.',
		'If your previous reply proposed a specific entity, area, or correction, and the user latest message agrees with it or repeats it, treat it as confirmed and start research.',
		'Users sometimes mistype or mispronounce names. When the user wording is unclear, contains an unfamiliar token, or could plausibly be either a venue or an area, ask one short clarifying question (such as "Did you mean X?") instead of guessing a correction.',
		'If the user prompt contains a possibly mistyped, garbled, or unfamiliar venue or area name — or any named token that could be a restaurant, brand, district, or chain — search for it with Places (use lookup_place) before classifying scope. Do not silently drop the token because it looks like noise or seems peripheral to the question.',
		'Ask only when the missing detail is needed. If the user gives enough restaurant, address, area, market, or broad industry scope, start research.',
		'First set scopeKind to the model-owned semantic role of the latest usable scope:',
		'- research_scope: enough named geography, market, catchment, non-food-service landmark-as-geographic-shorthand, or broad industry scope to research directly in search queries without resolving a Place ID.',
		'- anchor_place: a specific restaurant, cafe, bar, bakery, food hall vendor, food/drink brand, chain branch, venue, or exact address where the exact entity is the research target or branch identity matters.',
		'- candidate_selection: the user is choosing from remembered candidates.',
		'- insufficient_scope: the request still lacks enough usable scope.',
		'For openings, closures, saturation, local momentum, nearby competition, or market movement, near/around/in + a named public place, station, district, mall, hotel, tourist attraction, or landmark is usually research_scope when it names the surrounding market rather than a food-service business or exact branch.',
		'A bare generic area descriptor without a named place, city, neighborhood, market, address, or other anchor is insufficient_scope.',
		'A named restaurant, cafe, bakery, bar, food/drink brand, or chain is anchor_place when the request is about what is near or around it, because branch identity matters.',
		'Action must follow scopeKind: research_scope -> start_research with no placeId; anchor_place -> lookup_place unless selected or known context already resolves it; candidate_selection -> start_research with a candidate placeId; insufficient_scope -> reply.',
		'When Tool result contains Google Places candidates for an anchor_place: use one clear matching candidate to start research with its Place ID; ask the user to choose only when multiple plausible branches remain.',
		'A clear matching candidate must match the requested establishment or brand name and the important location cues. Do not select a candidate just because the street, neighborhood, or city matches if its name is a different establishment.',
		'If there is no clear matching candidate for the requested establishment, ask a short clarification instead of guessing.',
		'If known candidates exist and the user asks to see them, asks whether there are multiple, or picks by number, street, branch, name, or Place ID, use those candidates.',
		'If selected place context is relevant, set placeId to its Place ID.',
		'Never invent a Place ID. start_research.placeId must be the selected Place ID or one of the known candidate Place IDs.',
		'Write user-visible replies in the user language. For missing-detail replies, output only the clarification question or candidate list. Keep wording plain and direct. When listing candidates, put each option on its own line with an option number, name, and address.',
		'When starting research, researchQuestion must be a complete standalone request preserving the business intent and resolved scope.',
		'For start_research only, write an acknowledgement in the user language. Start with the work or focus, not a conversational opener. Say the report will take a few minutes. Use an empty acknowledgement for reply and lookup_place.',
		'',
		'Return JSON only with one action:',
		'- reply: write reply and updated state.',
		'- lookup_place: write placesQuery and updated state.',
		'- start_research: write researchQuestion, optional placeId, acknowledgement, and updated state.',
		'Always include scopeKind and every string field. Use an empty string when a field or acknowledgement is not relevant to the selected action.',
		'',
		`Conversation before latest message: ${JSON.stringify(compactHistory(history))}`,
		`Latest user message: ${JSON.stringify(compact(message))}`,
		`Current intake state: ${JSON.stringify(normalizeIntakeState(intakeState) || {})}`,
		`Selected place context: ${JSON.stringify(selectedPlaceContext || null)}`,
		`Tool result: ${JSON.stringify(toolResult || null)}`
	].join('\n');
}

async function callIntakeModel({
	history,
	message,
	intakeState,
	selectedPlaceContext,
	toolResult,
	fetchImpl,
	getToken
}) {
	return generateGeminiJson({
		prompt: buildIntakePrompt({
			history,
			message,
			intakeState,
			selectedPlaceContext,
			toolResult
		}),
		responseSchema: INTAKE_SCHEMA,
		maxOutputTokens: 900,
		errorName: 'intake_model',
		fetchImpl,
		getToken
	});
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
			pageSize: MAX_CANDIDATES
		})
	});
	if (!response.ok) {
		const body = await response.text().catch(() => '');
		throw new Error(`places_text_search_failed:${response.status}:${body.slice(0, 160)}`);
	}
	const payload = await response.json();
	return Array.isArray(payload?.places) ? payload.places : [];
}

function normalizeDecision({
	raw,
	previousState,
	selectedPlaceContext,
	candidates = null,
	message
}) {
	const state = mergeState({ modelState: raw?.state, previousState, candidates });
	const action = raw?.action;
	const scopeKind = SCOPE_KINDS.includes(raw?.scopeKind) ? raw.scopeKind : '';
	if (!['reply', 'lookup_place', 'start_research'].includes(action)) {
		throw new Error('intake_model_invalid_action');
	}

	if (action === 'reply') {
		return {
			action,
			scopeKind,
			reply: compactReply(raw.reply, 1400) || FALLBACK_REPLY,
			state,
			reason: compact(raw.reason, 120)
		};
	}

	if (action === 'lookup_place') {
		const placesQuery = compact(raw.placesQuery, 240);
		if (!placesQuery) throw new Error('intake_model_missing_places_query');
		return {
			action,
			scopeKind,
			placesQuery,
			state,
			reason: compact(raw.reason, 120)
		};
	}

	const resolutionState = stateForCandidateResolution(state, previousState);
	const placeContext = resolvePlaceContext({
		placeId: raw.placeId,
		selectedPlaceContext,
		state: resolutionState
	});
	if (compact(raw.placeId) && !placeContext) {
		return {
			action: 'reply',
			scopeKind,
			reply: FALLBACK_REPLY,
			state: resolutionState,
			reason: 'invalid_place_id'
		};
	}
	return {
		action,
		scopeKind,
		researchQuestion: compact(raw.researchQuestion, 1600) || compact(message, 1600),
		placeContext,
		acknowledgement: normalizeAcknowledgement(raw.acknowledgement, {
			state,
			researchQuestion: raw.researchQuestion,
			placeContext,
			message
		}),
		state,
		reason: compact(raw.reason, 120)
	};
}

export async function runIntakeConversation({
	history = [],
	message,
	intakeState = null,
	selectedPlaceContext = null,
	apiKey,
	fetchImpl = fetch,
	getToken
}) {
	const previousState = normalizeIntakeState(intakeState);
	const first = await callIntakeModel({
		history,
		message,
		intakeState: previousState,
		selectedPlaceContext,
		toolResult: null,
		fetchImpl,
		getToken
	});
	let decision = normalizeDecision({
		raw: first,
		previousState,
		selectedPlaceContext,
		message
	});

	if (decision.action !== 'lookup_place') return decision;
	if (!apiKey) throw new Error('places_api_key_missing');

	const places = await searchText({ query: decision.placesQuery, apiKey, fetchImpl });
	const candidates = placesToCandidates(places);
	const toolResult = {
		type: 'places_text_search',
		placesQuery: decision.placesQuery,
		candidates
	};
	const stateWithCandidates = mergeState({
		modelState: first.state,
		previousState,
		candidates
	});
	const second = await callIntakeModel({
		history,
		message,
		intakeState: stateWithCandidates,
		selectedPlaceContext,
		toolResult,
		fetchImpl,
		getToken
	});
	decision = normalizeDecision({
		raw: second,
		previousState: stateWithCandidates,
		selectedPlaceContext,
		candidates,
		message
	});
	return decision.action === 'lookup_place'
		? {
				action: 'reply',
				scopeKind: decision.scopeKind,
				reply: FALLBACK_REPLY,
				state: stateWithCandidates,
				reason: 'lookup_loop_limit'
			}
		: decision;
}
