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

// Deterministic fallbacks fire only when the model call fails or returns
// unusable text, so they can't rely on the model to self-localize. Keyed by
// the detected prompt language (en/de/pl), English otherwise.
const FALLBACK_REPLY_BY_LANG = {
	en: 'Which restaurant, street, neighborhood, city, or market should I check?',
	de: 'Welches Restaurant, welche Straße, welches Viertel, welche Stadt oder welchen Markt soll ich prüfen?',
	pl: 'Którą restaurację, ulicę, dzielnicę, miasto lub rynek mam sprawdzić?'
};

const ACK_FRAME_BY_LANG = {
	en: (focus) => `Reviewing ${focus}. The report will take a few minutes.`,
	de: (focus) => `Ich prüfe ${focus}. Der Bericht dauert ein paar Minuten.`,
	pl: (focus) => `Sprawdzam ${focus}. Raport zajmie kilka minut.`
};

function fallbackReply(language) {
	return FALLBACK_REPLY_BY_LANG[language] || FALLBACK_REPLY_BY_LANG.en;
}

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

const INTAKE_SCHEMA = {
	type: 'OBJECT',
	properties: {
		action: { type: 'STRING', enum: ['reply', 'lookup_place', 'start_research'] },
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
	const frame = ACK_FRAME_BY_LANG[context?.language] || ACK_FRAME_BY_LANG.en;
	return frame(focus);
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
	toolResult = null,
	language = 'en'
}) {
	return [
		'You are Superextra intake, the fast conversation layer before restaurant market research.',
		`Write all user-visible text (reply, acknowledgement) in the language with ISO code "${language}".`,
		'Help the user reach a research-ready request. Do not research, browse, or answer the business question.',
		'Use the conversation naturally. Do not assume fixed rounds or that the latest message only answers the previous question.',
		'Use your knowledge of restaurants, brands, geography, and districts to interpret the user. Recognise known chains as multi-branch, known districts as areas, and obvious typos as repair opportunities — without overthinking the classification.',
		'If your previous reply proposed a specific entity, area, or correction, and the user latest message agrees with it or repeats it, treat it as confirmed and start research.',
		'Ask only when the missing detail is needed. If the user gives enough restaurant, address, area, market, or broad industry scope, start research.',
		'Use Google Places lookup when a restaurant, venue, branch, address, or landmark should be validated or disambiguated.',
		'Do not ask the user to choose a branch before using Places when a lookup can reveal the real candidates.',
		'If the user reply names a place or area not in your prior candidate list, treat it as fresh input — run a new Places lookup with the new wording before deciding scope. Do not drop the user named token to fall back to the broader city.',
		'If known candidates exist and the user asks to see them, asks whether there are multiple, or picks by number, street, branch, name, or Place ID, use those candidates.',
		'If selected place context is relevant, set placeId to its Place ID.',
		'Never invent a Place ID. start_research.placeId must be the selected Place ID or one of the known candidate Place IDs.',
		'Write user-visible replies in the user language. Keep replies concise and direct; avoid filler or reassurance. When listing candidates, include newline characters between options, like "Which one?\\n1. Name - address\\n2. Name - address".',
		'When starting research, researchQuestion must be a complete standalone request preserving the business intent and resolved scope.',
		'For start_research only, write an acknowledgement in the user language. Start with the work or focus, not a conversational opener. Say the report will take a few minutes. Use an empty acknowledgement for reply and lookup_place.',
		'',
		'Return JSON only with one action:',
		'- reply: write reply and updated state.',
		'- lookup_place: write placesQuery and updated state.',
		'- start_research: write researchQuestion, optional placeId, acknowledgement, and updated state.',
		'Always include every string field. Use an empty string when a field or acknowledgement is not relevant to the selected action.',
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
	language,
	fetchImpl,
	getToken
}) {
	return generateGeminiJson({
		prompt: buildIntakePrompt({
			history,
			message,
			intakeState,
			selectedPlaceContext,
			toolResult,
			language
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
	message,
	language = 'en'
}) {
	const state = mergeState({ modelState: raw?.state, previousState, candidates });
	const action = raw?.action;
	if (!['reply', 'lookup_place', 'start_research'].includes(action)) {
		throw new Error('intake_model_invalid_action');
	}

	if (action === 'reply') {
		return {
			action,
			reply: compactReply(raw.reply, 1400) || fallbackReply(language),
			state,
			reason: compact(raw.reason, 120)
		};
	}

	if (action === 'lookup_place') {
		const placesQuery = compact(raw.placesQuery, 240);
		if (!placesQuery) throw new Error('intake_model_missing_places_query');
		return {
			action,
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
			reply: fallbackReply(language),
			state: resolutionState,
			reason: 'invalid_place_id'
		};
	}
	return {
		action,
		researchQuestion: compact(raw.researchQuestion, 1600) || compact(message, 1600),
		placeContext,
		acknowledgement: normalizeAcknowledgement(raw.acknowledgement, {
			state,
			researchQuestion: raw.researchQuestion,
			placeContext,
			message,
			language
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
	language = 'en',
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
		language,
		fetchImpl,
		getToken
	});
	let decision = normalizeDecision({
		raw: first,
		previousState,
		selectedPlaceContext,
		message,
		language
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
		language,
		fetchImpl,
		getToken
	});
	decision = normalizeDecision({
		raw: second,
		previousState: stateWithCandidates,
		selectedPlaceContext,
		candidates,
		message,
		language
	});
	return decision.action === 'lookup_place'
		? {
				action: 'reply',
				reply: fallbackReply(language),
				state: stateWithCandidates,
				reason: 'lookup_loop_limit'
			}
		: decision;
}
