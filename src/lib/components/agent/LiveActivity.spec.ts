import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import LiveActivity from './LiveActivity.svelte';

describe('LiveActivity', () => {
	it('uses the analysis event text as the live status label', () => {
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
				elapsedMs: 0
			}
		});

		expect(body).toContain('Starting research');
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
});
