import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import LiveActivity from './LiveActivity.svelte';

describe('LiveActivity', () => {
	it('uses the live status label over the run-start placeholder', () => {
		const { body } = render(LiveActivity, {
			props: {
				events: [
					{
						kind: 'detail',
						id: 'run-start:1',
						group: 'platform',
						family: 'Analysis',
						text: 'Starting research'
					}
				],
				startedAtMs: 1000,
				elapsedMs: 0,
				statusLabel: 'Building context'
			}
		});

		expect(body).toContain('Building context');
		expect(body).not.toContain('Starting research');
	});

	it('keeps real timeline events ahead of the live status label', () => {
		const { body } = render(LiveActivity, {
			props: {
				events: [
					{
						kind: 'detail',
						id: 'run-start:1',
						group: 'platform',
						family: 'Analysis',
						text: 'Starting research'
					},
					{
						kind: 'detail',
						id: 'tool:call:1',
						group: 'platform',
						family: 'Google Maps',
						text: 'searching places'
					}
				],
				startedAtMs: 1000,
				elapsedMs: 0,
				statusLabel: 'Building context'
			}
		});

		expect(body).toContain('Looking up venue data');
		expect(body).not.toContain('Building context');
	});

	it('does not render the run-start status as the first activity step', () => {
		const { body } = render(LiveActivity, {
			props: {
				events: [
					{
						kind: 'detail',
						id: 'run-start:1',
						group: 'platform',
						family: 'Analysis',
						text: 'Starting research'
					},
					{
						kind: 'thought',
						id: 'thought:1',
						author: 'research_lead',
						text: 'Reading local signals'
					}
				],
				startedAtMs: 1000,
				elapsedMs: 0
			}
		});

		expect(body).toContain('Reading local signals');
		expect(body).not.toContain('Starting research');
	});

	it('uses public labels for specialist and unknown thought authors', () => {
		const { body } = render(LiveActivity, {
			props: {
				events: [
					{
						kind: 'thought',
						id: 'thought:1',
						author: 'dynamic_researcher_1',
						text: 'Checking closure signals'
					},
					{
						kind: 'thought',
						id: 'thought:2',
						author: 'custom_internal_helper',
						text: 'Reading local sources'
					}
				],
				startedAtMs: 1000,
				elapsedMs: 0
			}
		});

		expect(body).toContain('Researching');
		expect(body).not.toContain('Dynamic researcher');
		expect(body).not.toContain('Custom internal helper');
	});
});
