const PLACES_TEXT_SEARCH_URL = 'https://places.googleapis.com/v1/places:searchText';
const TEXT_SEARCH_FIELDS = [
	'places.id',
	'places.displayName',
	'places.formattedAddress',
	'places.primaryType',
	'places.types'
].join(',');

const FOOD_DRINK_PLACE_TYPES = new Set([
	'bagel_shop',
	'bakery',
	'bar',
	'bistro',
	'cafe',
	'coffee_shop',
	'deli',
	'dessert_shop',
	'ice_cream_shop',
	'meal_delivery',
	'meal_takeaway',
	'pub',
	'restaurant',
	'sandwich_shop',
	'snack_bar',
	'tea_house',
	'wine_bar'
]);

const STOP_WORDS = new Set([
	'a',
	'an',
	'and',
	'area',
	'at',
	'branch',
	'city',
	'for',
	'in',
	'near',
	'of',
	'on',
	'or',
	'place',
	'restaurant',
	'restaurants',
	'street',
	'the',
	'to',
	'ul',
	'ulica'
]);

const SELF_REFERENTIAL_PATTERN =
	/\b(my|our|near me|near us|nearby|local|my area|our area|my competitors|our competitors)\b/i;

export function normalizePlaceText(value) {
	return String(value || '')
		.normalize('NFD')
		.replace(/[\u0300-\u036f]/g, '')
		.toLowerCase()
		.replace(/[^\p{L}\p{N}\s'-]/gu, ' ')
		.replace(/\s+/g, ' ')
		.trim();
}

function meaningfulTokens(value) {
	return normalizePlaceText(value)
		.split(/\s+/)
		.filter((token) => token.length >= 3 && !STOP_WORDS.has(token));
}

function placeName(place) {
	return place?.displayName?.text || '';
}

function placeAddress(place) {
	return place?.formattedAddress || '';
}

function isFoodService(place) {
	const primaryType = place?.primaryType;
	if (
		typeof primaryType === 'string' &&
		(FOOD_DRINK_PLACE_TYPES.has(primaryType) || primaryType.endsWith('_restaurant'))
	) {
		return true;
	}
	const types = place?.types;
	return (
		Array.isArray(types) &&
		types.some(
			(type) =>
				typeof type === 'string' &&
				(FOOD_DRINK_PLACE_TYPES.has(type) || type.endsWith('_restaurant'))
		)
	);
}

function levenshteinDistance(a, b) {
	if (a === b) return 0;
	if (!a) return b.length;
	if (!b) return a.length;

	const prev = Array.from({ length: b.length + 1 }, (_, i) => i);
	const curr = Array.from({ length: b.length + 1 }, () => 0);

	for (let i = 1; i <= a.length; i++) {
		curr[0] = i;
		for (let j = 1; j <= b.length; j++) {
			const cost = a[i - 1] === b[j - 1] ? 0 : 1;
			curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
		}
		prev.splice(0, prev.length, ...curr);
	}
	return prev[b.length];
}

function tokenMatches(candidateToken, queryToken) {
	if (candidateToken.includes(queryToken) || queryToken.includes(candidateToken)) return true;
	if (queryToken.length < 7 || candidateToken.length < 7) return false;
	return levenshteinDistance(candidateToken, queryToken) <= 2;
}

function placeCoversTokens(place, tokens) {
	const candidateTokens = meaningfulTokens(`${placeName(place)} ${placeAddress(place)}`);
	return tokens.every((token) =>
		candidateTokens.some((candidateToken) => tokenMatches(candidateToken, token))
	);
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
			maxResultCount: 5
		})
	});
	if (!response.ok) {
		const body = await response.text().catch(() => '');
		throw new Error(`places_text_search_failed:${response.status}:${body.slice(0, 160)}`);
	}
	const payload = await response.json();
	return Array.isArray(payload?.places) ? payload.places : [];
}

export async function resolveClarificationFocus({ message, apiKey, fetchImpl = fetch }) {
	const query = String(message || '').trim();
	if (!query || !apiKey || SELF_REFERENTIAL_PATTERN.test(query)) return null;

	const tokens = meaningfulTokens(query);
	if (!tokens.length) return null;

	const places = await searchText({ query, apiKey, fetchImpl });
	const candidates = places.filter((place) => toPlaceContext(place));
	if (!candidates.length) return null;

	const strongMatches = candidates.filter((place) => placeCoversTokens(place, tokens));
	if (strongMatches.length !== 1) return null;

	const match = strongMatches[0];
	if (isFoodService(match) && tokens.length < 2) return null;

	return toPlaceContext(match);
}
