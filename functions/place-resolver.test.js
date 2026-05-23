import { describe, it, mock } from 'node:test';
import assert from 'node:assert/strict';

import { normalizePlaceText, resolveClarificationFocus } from './place-resolver.js';

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

function fetchPlaces(places) {
	return mock.fn(async () => ({
		ok: true,
		json: async () => ({ places })
	}));
}

describe('normalizePlaceText', () => {
	it('folds accents and punctuation for place matching', () => {
		assert.equal(
			normalizePlaceText('Monsun, Świętojańska 69b — Gdynia'),
			'monsun swietojanska 69b gdynia'
		);
	});
});

describe('resolveClarificationFocus', () => {
	it('resolves a restaurant and city when Places has one strong match', async () => {
		const fetchImpl = fetchPlaces([
			place({
				name: 'Monsun Gdynia',
				address: 'Świętojańska 69b, 81-389 Gdynia, Poland'
			}),
			place({
				id: 'other',
				name: 'Monsun Warszawa',
				address: 'Warsaw, Poland'
			})
		]);

		const result = await resolveClarificationFocus({
			message: 'monsun gdynia',
			apiKey: 'key',
			fetchImpl
		});

		assert.deepEqual(result, {
			name: 'Monsun Gdynia',
			secondary: 'Świętojańska 69b, 81-389 Gdynia, Poland',
			placeId: 'ChIJtest'
		});
		const [, init] = fetchImpl.mock.calls[0].arguments;
		assert.equal(init.headers['X-Goog-Api-Key'], 'key');
		assert.equal(JSON.parse(init.body).textQuery, 'monsun gdynia');
	});

	it('resolves restaurant plus street and city without requiring a house number', async () => {
		const result = await resolveClarificationFocus({
			message: 'monsun swietojanska in gdynia',
			apiKey: 'key',
			fetchImpl: fetchPlaces([
				place({
					name: 'Monsun Gdynia',
					address: 'Świętojańska 69b, 81-389 Gdynia, Poland'
				})
			])
		});

		assert.equal(result?.placeId, 'ChIJtest');
	});

	it('resolves conversational place answers with proximity filler', async () => {
		const result = await resolveClarificationFocus({
			message: 'Around monsun in Gdynia',
			apiKey: 'key',
			fetchImpl: fetchPlaces([
				place({
					name: 'Monsun Gdynia',
					address: 'Świętojańska 69b, 81-389 Gdynia, Poland'
				})
			])
		});

		assert.equal(result?.placeId, 'ChIJtest');
	});

	it('does not choose among multiple strong same-query matches', async () => {
		const result = await resolveClarificationFocus({
			message: 'zeit fur brot berlin',
			apiKey: 'key',
			fetchImpl: fetchPlaces([
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
			])
		});

		assert.equal(result, null);
	});

	it('does not resolve self-referential answers', async () => {
		const fetchImpl = fetchPlaces([
			place({
				name: 'Nearby Cafe',
				address: 'Gdynia, Poland'
			})
		]);

		const result = await resolveClarificationFocus({
			message: 'near me',
			apiKey: 'key',
			fetchImpl
		});

		assert.equal(result, null);
		assert.equal(fetchImpl.mock.callCount(), 0);
	});

	it('does not resolve a one-token restaurant name without geography', async () => {
		const result = await resolveClarificationFocus({
			message: 'monsun',
			apiKey: 'key',
			fetchImpl: fetchPlaces([
				place({
					name: 'Monsun Gdynia',
					address: 'Świętojańska 69b, Gdynia, Poland'
				})
			])
		});

		assert.equal(result, null);
	});
});
