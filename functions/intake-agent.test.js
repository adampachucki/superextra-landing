import { describe, it, mock } from 'node:test';
import assert from 'node:assert/strict';

import { buildIntakePrompt, normalizeIntakeState, runIntakeConversation } from './intake-agent.js';

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

const emptyState = {
	summary: '',
	originalIntent: '',
	scopeSummary: '',
	pendingQuestion: '',
	candidateSet: 'clear'
};

describe('buildIntakePrompt', () => {
	it('frames intake as a model-owned conversation without fixed rounds', () => {
		const prompt = buildIntakePrompt({
			history: [
				{ role: 'user', text: 'What has opened or closed in my area recently?' },
				{ role: 'assistant', text: 'What area should I check?' }
			],
			message: 'Around Zeit fur Brot in Berlin',
			intakeState: {
				originalIntent: 'What has opened or closed in my area recently?'
			}
		});

		assert.match(prompt, /fast conversation layer/);
		assert.match(prompt, /Do not assume fixed rounds/);
		assert.match(prompt, /Google Places lookup/);
		assert.match(prompt, /selected place context is relevant/i);
		assert.match(prompt, /avoid filler or reassurance/i);
		assert.match(prompt, /newline characters/i);
		assert.match(prompt, /1\. Name - address/);
		assert.match(prompt, /acknowledgementOptions/);
		assert.match(prompt, /report will take a few minutes/);
		assert.match(prompt, /first-person sentence/);
		assert.match(prompt, /I have enough context/);
		assert.doesNotMatch(prompt, /first round/i);
		assert.doesNotMatch(prompt, /second round/i);
	});
});

describe('normalizeIntakeState', () => {
	it('keeps compact model-authored state and known candidates', () => {
		assert.deepEqual(
			normalizeIntakeState({
				summary: 'Need openings/closures around a branch.',
				originalIntent: 'What opened nearby?',
				candidates: [
					{
						optionNumber: 9,
						placeId: 'a',
						name: 'Zeit für Brot',
						address: 'Alte Schönhauser Str. 4, Berlin'
					}
				]
			}),
			{
				summary: 'Need openings/closures around a branch.',
				originalIntent: 'What opened nearby?',
				scopeSummary: '',
				pendingQuestion: '',
				candidates: [
					{
						optionNumber: 1,
						placeId: 'a',
						name: 'Zeit für Brot',
						address: 'Alte Schönhauser Str. 4, Berlin',
						primaryType: '',
						types: []
					}
				]
			}
		);
	});
});

describe('runIntakeConversation', () => {
	it('asks directly when the model needs missing scope', async () => {
		const result = await runIntakeConversation({
			message: 'What has opened or closed in my area recently?',
			fetchImpl: fetchSequence([
				modelJson({
					action: 'reply',
					reply: 'What area should I check?',
					acknowledgementOptions: {
						primary: 'Should not be used.',
						alternate: '',
						brief: ''
					},
					reason: 'missing_scope',
					state: {
						...emptyState,
						originalIntent: 'What has opened or closed in my area recently?',
						pendingQuestion: 'What area should I check?'
					}
				})
			]),
			getToken: async () => 'token'
		});

		assert.equal(result.action, 'reply');
		assert.equal(result.reply, 'What area should I check?');
		assert.equal(result.state.originalIntent, 'What has opened or closed in my area recently?');
	});

	it('starts research from an area answer without a Places call', async () => {
		const fetchImpl = fetchSequence([
			modelJson({
				action: 'start_research',
				researchQuestion: 'What has opened or closed in Williamsburg, Brooklyn recently?',
				acknowledgementOptions: {
					primary:
						"I have enough context to start on Williamsburg, Brooklyn; I'll review local market movement and prepare the report in a few minutes.",
					alternate:
						'I have enough scope for Williamsburg, Brooklyn; the report will take a few minutes to prepare.',
					brief:
						'I can start the Williamsburg, Brooklyn openings and closures analysis now; it will take a few minutes.'
				},
				reason: 'area_scope_ready',
				state: {
					...emptyState,
					originalIntent: 'What has opened or closed in my area recently?',
					scopeSummary: 'Williamsburg, Brooklyn'
				}
			})
		]);

		const result = await runIntakeConversation({
			history: [
				{ role: 'user', text: 'What has opened or closed in my area recently?' },
				{ role: 'assistant', text: 'What area should I check?' }
			],
			message: 'Williamsburg, Brooklyn',
			intakeState: {
				originalIntent: 'What has opened or closed in my area recently?'
			},
			apiKey: 'key',
			fetchImpl,
			getToken: async () => 'token'
		});

		assert.equal(fetchImpl.mock.callCount(), 1);
		assert.equal(result.action, 'start_research');
		assert.equal(
			result.researchQuestion,
			'What has opened or closed in Williamsburg, Brooklyn recently?'
		);
		assert.deepEqual(result.acknowledgements.slice(0, 2), [
			"I have enough context to start on Williamsburg, Brooklyn; I'll review local market movement and prepare the report in a few minutes.",
			'I have enough scope for Williamsburg, Brooklyn; the report will take a few minutes to prepare.'
		]);
		assert.ok(result.acknowledgements.length > 2);
		assert.match(result.acknowledgements.at(-1), /Williamsburg, Brooklyn/);
		assert.equal(result.placeContext, null);
	});

	it('replaces vague model acknowledgements with scoped options that meet the product contract', async () => {
		const result = await runIntakeConversation({
			message: 'Should we open a second taco shop near Pike Place, or is that area too saturated?',
			fetchImpl: fetchSequence([
				modelJson({
					action: 'start_research',
					researchQuestion:
						'Market saturation analysis for taco shops near Pike Place Market in Seattle.',
					acknowledgementOptions: {
						primary:
							'There is enough context to analyze the taco shop market near Pike Place Market. The report will be ready in a few minutes.',
						alternate:
							'Research on the taco shop market around Pike Place Market is underway. Expect the report shortly.',
						brief:
							'Analyzing taco shop market saturation near Pike Place Market. Report coming soon.'
					},
					reason: 'market_scope_ready',
					state: {
						...emptyState,
						originalIntent:
							'Should we open a second taco shop near Pike Place, or is that area too saturated?',
						scopeSummary: 'Pike Place taco-shop expansion and saturation analysis'
					}
				})
			]),
			getToken: async () => 'token'
		});

		assert.equal(result.action, 'start_research');
		assert.equal(result.acknowledgements.length, 6);
		for (const acknowledgement of result.acknowledgements) {
			assert.match(acknowledgement, /Pike Place taco-shop/);
			assert.match(acknowledgement, /\bI\b|I['’](ll|ve|m)\b/);
			assert.match(acknowledgement, /few minutes/);
			assert.doesNotMatch(acknowledgement, /Superextra|the models/i);
			assert.doesNotMatch(acknowledgement, /\b(you|your)\b/i);
			assert.doesNotMatch(acknowledgement, /\?/);
		}
	});

	it('uses Places and accepts a model-selected place by Place ID', async () => {
		const fetchImpl = fetchSequence([
			modelJson({
				action: 'lookup_place',
				placesQuery: 'Monsun Gdynia',
				reason: 'place_lookup_needed',
				state: {
					...emptyState,
					originalIntent: 'What has opened or closed in my area recently?',
					scopeSummary: 'Monsun in Gdynia'
				}
			}),
			placesJson([
				place({
					id: 'monsun',
					name: 'Monsun Gdynia',
					address: 'Świętojańska 69b, 81-389 Gdynia, Poland'
				})
			]),
			modelJson({
				action: 'start_research',
				researchQuestion: 'What has opened or closed around Monsun Gdynia recently?',
				placeId: 'monsun',
				reason: 'single_candidate_ready',
				state: {
					...emptyState,
					originalIntent: 'What has opened or closed in my area recently?',
					scopeSummary: 'Monsun Gdynia'
				}
			})
		]);

		const result = await runIntakeConversation({
			history: [
				{ role: 'user', text: 'What has opened or closed in my area recently?' },
				{ role: 'assistant', text: 'What area should I check?' }
			],
			message: 'Around monsun in Gdynia',
			apiKey: 'key',
			fetchImpl,
			getToken: async () => 'token'
		});

		assert.equal(fetchImpl.mock.callCount(), 3);
		const [, placesInit] = fetchImpl.mock.calls[1].arguments;
		assert.equal(placesInit.headers['X-Goog-Api-Key'], 'key');
		assert.deepEqual(JSON.parse(placesInit.body), {
			textQuery: 'Monsun Gdynia',
			pageSize: 5
		});
		assert.equal(result.action, 'start_research');
		assert.deepEqual(result.placeContext, {
			name: 'Monsun Gdynia',
			secondary: 'Świętojańska 69b, 81-389 Gdynia, Poland',
			placeId: 'monsun'
		});
	});

	it('persists ambiguous candidates when the model replies with options', async () => {
		const result = await runIntakeConversation({
			history: [
				{ role: 'user', text: 'What has opened or closed in my area recently?' },
				{ role: 'assistant', text: 'What area should I check?' }
			],
			message: 'Around Zeit fur Brit in Berlin',
			apiKey: 'key',
			fetchImpl: fetchSequence([
				modelJson({
					action: 'lookup_place',
					placesQuery: 'Zeit für Brot Berlin',
					reason: 'place_lookup_needed',
					state: {
						...emptyState,
						originalIntent: 'What has opened or closed in my area recently?',
						scopeSummary: 'Zeit für Brot in Berlin'
					}
				}),
				placesJson([
					place({
						id: 'a',
						name: 'Zeit für Brot',
						address: 'Alte Schönhauser Str. 4, Berlin, Germany'
					}),
					place({
						id: 'b',
						name: 'ZEIT FÜR BROT',
						address: 'Eberswalder Str. 26, Berlin, Germany'
					})
				]),
				modelJson({
					action: 'reply',
					reply:
						'There are multiple Zeit für Brot locations in Berlin:\n1. Alte Schönhauser Str. 4\n2. Eberswalder Str. 26\nWhich one should I use?',
					reason: 'multiple_candidates',
					state: {
						...emptyState,
						originalIntent: 'What has opened or closed in my area recently?',
						scopeSummary: 'Zeit für Brot in Berlin',
						pendingQuestion: 'Which Zeit für Brot location should I use?',
						candidateSet: 'keep'
					}
				})
			]),
			getToken: async () => 'token'
		});

		assert.equal(result.action, 'reply');
		assert.equal(result.state.candidates.length, 2);
		assert.equal(result.state.candidates[0].optionNumber, 1);
		assert.equal(result.state.candidates[0].placeId, 'a');
		assert.match(result.reply, /Alte Schönhauser/);
	});

	it('starts research from a later user pick using remembered candidates', async () => {
		const result = await runIntakeConversation({
			history: [
				{ role: 'user', text: 'Around Zeit fur Brit in Berlin' },
				{ role: 'assistant', text: 'Which Zeit für Brot location should I use?' }
			],
			message: 'the one on Alte Schönhauser',
			intakeState: {
				originalIntent: 'What has opened or closed in my area recently?',
				scopeSummary: 'Zeit für Brot in Berlin',
				pendingQuestion: 'Which Zeit für Brot location should I use?',
				candidates: [
					{
						placeId: 'a',
						name: 'Zeit für Brot',
						address: 'Alte Schönhauser Str. 4, Berlin, Germany'
					},
					{
						placeId: 'b',
						name: 'ZEIT FÜR BROT',
						address: 'Eberswalder Str. 26, Berlin, Germany'
					}
				]
			},
			apiKey: 'key',
			fetchImpl: fetchSequence([
				modelJson({
					action: 'start_research',
					researchQuestion:
						'What has opened or closed around Zeit für Brot on Alte Schönhauser Str. 4 recently?',
					placeId: 'a',
					reason: 'candidate_selected',
					state: {
						...emptyState,
						originalIntent: 'What has opened or closed in my area recently?',
						scopeSummary: 'Zeit für Brot, Alte Schönhauser Str. 4',
						candidateSet: 'keep'
					}
				})
			]),
			getToken: async () => 'token'
		});

		assert.equal(result.action, 'start_research');
		assert.equal(result.placeContext.placeId, 'a');
		assert.match(result.researchQuestion, /Alte Schönhauser/);
	});

	it('accepts model references to remembered candidates by option number', async () => {
		const result = await runIntakeConversation({
			message: '1',
			intakeState: {
				originalIntent: 'What has opened or closed in my area recently?',
				candidates: [
					{
						optionNumber: 1,
						placeId: 'a',
						name: 'Zeit für Brot',
						address: 'Alte Schönhauser Str. 4, Berlin, Germany'
					}
				]
			},
			fetchImpl: fetchSequence([
				modelJson({
					action: 'start_research',
					researchQuestion:
						'What has opened or closed around Zeit für Brot on Alte Schönhauser Str. 4 recently?',
					placeId: '1',
					reason: 'candidate_selected',
					state: {
						...emptyState,
						originalIntent: 'What has opened or closed in my area recently?',
						scopeSummary: 'Zeit für Brot, Alte Schönhauser Str. 4',
						candidateSet: 'clear'
					}
				})
			]),
			getToken: async () => 'token'
		});

		assert.equal(result.action, 'start_research');
		assert.equal(result.placeContext.placeId, 'a');
	});

	it('accepts model references to remembered candidates by street text', async () => {
		const result = await runIntakeConversation({
			message: 'the one on Alte Schönhauser',
			intakeState: {
				originalIntent: 'What has opened or closed in my area recently?',
				candidates: [
					{
						optionNumber: 1,
						placeId: 'a',
						name: 'Zeit für Brot',
						address: 'Alte Schönhauser Str. 4, Berlin, Germany'
					}
				]
			},
			fetchImpl: fetchSequence([
				modelJson({
					action: 'start_research',
					researchQuestion:
						'What has opened or closed around Zeit für Brot on Alte Schönhauser Str. 4 recently?',
					placeId: 'Alte Schönhauser',
					reason: 'candidate_selected',
					state: {
						...emptyState,
						originalIntent: 'What has opened or closed in my area recently?',
						scopeSummary: 'Zeit für Brot, Alte Schönhauser Str. 4',
						candidateSet: 'clear'
					}
				})
			]),
			getToken: async () => 'token'
		});

		assert.equal(result.action, 'start_research');
		assert.equal(result.placeContext.placeId, 'a');
	});

	it('uses a selected place context when the model chooses it', async () => {
		const selectedPlaceContext = {
			name: 'Zeit für Brot',
			secondary: 'Alte Schönhauser Str. 4, Berlin',
			placeId: 'selected'
		};
		const result = await runIntakeConversation({
			history: [
				{ role: 'user', text: 'What has opened or closed in my area recently?' },
				{ role: 'assistant', text: 'What area should I check?' }
			],
			message: 'Use this branch',
			selectedPlaceContext,
			intakeState: {
				originalIntent: 'What has opened or closed in my area recently?'
			},
			fetchImpl: fetchSequence([
				modelJson({
					action: 'start_research',
					researchQuestion: 'What has opened or closed around this Zeit für Brot branch recently?',
					placeId: 'selected',
					reason: 'selected_place_ready',
					state: {
						...emptyState,
						originalIntent: 'What has opened or closed in my area recently?',
						scopeSummary: 'Zeit für Brot, Alte Schönhauser Str. 4'
					}
				})
			]),
			getToken: async () => 'token'
		});

		assert.equal(result.action, 'start_research');
		assert.deepEqual(result.placeContext, selectedPlaceContext);
	});
});
