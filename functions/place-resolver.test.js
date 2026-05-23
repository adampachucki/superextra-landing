import { describe, it, mock } from 'node:test';
import assert from 'node:assert/strict';

import { buildScopePrompt, resolveClarificationFocus } from './place-resolver.js';

function place({
	id = 'ChIJtest',
	name,
	address = '',
	primaryType = 'restaurant',
	types = ['restaurant']
}) {
	return {
		id,
		displayName: { text: name },
		formattedAddress: address,
		primaryType,
		types
	};
}

function modelJson(data) {
	return {
		ok: true,
		json: async () => ({
			candidates: [
				{
					content: {
						parts: [{ text: JSON.stringify(data) }]
					}
				}
			]
		})
	};
}

function placesJson(places) {
	return {
		ok: true,
		json: async () => ({ places })
	};
}

function fetchSequence(responses) {
	const pending = [...responses];
	return mock.fn(async () => {
		const response = pending.shift();
		if (!response) throw new Error('unexpected fetch call');
		return response;
	});
}

describe('resolveClarificationFocus', () => {
	it('includes the active clarification question in the model scope prompt', () => {
		const prompt = buildScopePrompt({
			message: 'the one on Alte Schönhauser',
			originalQuestion: 'What has opened or closed in my area recently?',
			clarificationQuestion: 'Which Zeit für Brot location in Berlin do you mean?'
		});

		assert.match(prompt, /Original question/);
		assert.match(prompt, /Clarification question/);
		assert.match(prompt, /Which Zeit für Brot location in Berlin/);
		assert.match(prompt, /the one on Alte Schönhauser/);
	});

	it('uses the model Places query and accepts a selected candidate', async () => {
		const fetchImpl = fetchSequence([
			modelJson({
				scopeType: 'place',
				placesQuery: 'Monsun Gdynia',
				relationship: 'around',
				needsPlacesLookup: true,
				reason: 'restaurant_city_anchor'
			}),
			placesJson([
				place({
					name: 'Monsun Gdynia',
					address: 'Świętojańska 69b, 81-389 Gdynia, Poland'
				}),
				place({
					id: 'other',
					name: 'Monsun Warszawa',
					address: 'Warsaw, Poland'
				})
			]),
			modelJson({
				action: 'accept_place',
				candidateIndex: 0,
				reason: 'clear_branch_match'
			})
		]);

		const result = await resolveClarificationFocus({
			message: 'Around monsun in Gdynia',
			originalQuestion: 'What has opened or closed in my area recently?',
			apiKey: 'key',
			fetchImpl,
			getToken: async () => 'token'
		});

		assert.deepEqual(result, {
			name: 'Monsun Gdynia',
			secondary: 'Świętojańska 69b, 81-389 Gdynia, Poland',
			placeId: 'ChIJtest'
		});
		const [, placesInit] = fetchImpl.mock.calls[1].arguments;
		assert.equal(placesInit.headers['X-Goog-Api-Key'], 'key');
		assert.deepEqual(JSON.parse(placesInit.body), {
			textQuery: 'Monsun Gdynia',
			pageSize: 5
		});
	});

	it('lets the model handle non-English relationship wording', async () => {
		const result = await resolveClarificationFocus({
			message: 'Wokół Monsun w Gdyni',
			originalQuestion: 'Co otworzyło się albo zamknęło w mojej okolicy?',
			apiKey: 'key',
			fetchImpl: fetchSequence([
				modelJson({
					scopeType: 'place',
					placesQuery: 'Monsun Gdynia',
					relationship: 'around',
					needsPlacesLookup: true,
					reason: 'restaurant_city_anchor'
				}),
				placesJson([
					place({
						name: 'Monsun Gdynia',
						address: 'Świętojańska 69b, 81-389 Gdynia, Poland'
					})
				]),
				modelJson({
					action: 'accept_place',
					candidateIndex: 0,
					reason: 'clear_branch_match'
				})
			]),
			getToken: async () => 'token'
		});

		assert.equal(result?.placeId, 'ChIJtest');
	});

	it('returns a clarification question when candidates are ambiguous', async () => {
		const result = await resolveClarificationFocus({
			message: 'near Zeit fur Brot in Berlin',
			originalQuestion: 'What has opened or closed in my area recently?',
			apiKey: 'key',
			fetchImpl: fetchSequence([
				modelJson({
					scopeType: 'place',
					placesQuery: 'Zeit für Brot Berlin',
					relationship: 'near',
					needsPlacesLookup: true,
					reason: 'restaurant_city_anchor'
				}),
				placesJson([
					place({
						id: 'a',
						name: 'Zeit für Brot',
						address: 'Alte Schönhauser Str. 4, Berlin, Germany'
					}),
					place({
						id: 'b',
						name: 'Zeit für Brot',
						address: 'Konstanzer Str. 1, Berlin, Germany'
					})
				]),
				modelJson({
					action: 'ask_user',
					question: 'Which Zeit für Brot location in Berlin do you mean?',
					reason: 'multiple_plausible_branches'
				})
			]),
			getToken: async () => 'token'
		});

		assert.deepEqual(result, {
			question: 'Which Zeit für Brot location in Berlin do you mean?',
			reason: 'multiple_plausible_branches'
		});
	});

	it('does not call Places when the model interprets the answer as an area', async () => {
		const fetchImpl = fetchSequence([
			modelJson({
				scopeType: 'area',
				placesQuery: '',
				relationship: 'in',
				needsPlacesLookup: false,
				reason: 'neighborhood_answer'
			})
		]);

		const result = await resolveClarificationFocus({
			message: 'Williamsburg, Brooklyn',
			originalQuestion: 'What has opened or closed in my area recently?',
			apiKey: 'key',
			fetchImpl,
			getToken: async () => 'token'
		});

		assert.equal(result, null);
		assert.equal(fetchImpl.mock.callCount(), 1);
	});

	it('returns null when Places has no usable candidates', async () => {
		const result = await resolveClarificationFocus({
			message: 'around made up restaurant in Gdynia',
			originalQuestion: 'What has opened or closed in my area recently?',
			apiKey: 'key',
			fetchImpl: fetchSequence([
				modelJson({
					scopeType: 'place',
					placesQuery: 'Made Up Restaurant Gdynia',
					relationship: 'around',
					needsPlacesLookup: true,
					reason: 'restaurant_city_anchor'
				}),
				placesJson([])
			]),
			getToken: async () => 'token'
		});

		assert.equal(result, null);
	});
});
