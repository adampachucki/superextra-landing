import { describe, expect, it } from 'vitest';
import { splitChartSegments } from './chart-blocks';

describe('splitChartSegments', () => {
	it('returns plain markdown when no chart fence is present', () => {
		const segs = splitChartSegments('Just some text.\n\n## Heading');
		expect(segs).toEqual([{ kind: 'md', text: 'Just some text.\n\n## Heading' }]);
	});

	it('parses a single valid chart fence into a chart segment', () => {
		const text = [
			'Before.',
			'```chart',
			'{"type":"bar","title":"T","data":[{"label":"A","value":1}]}',
			'```',
			'After.'
		].join('\n');
		const segs = splitChartSegments(text);
		expect(segs.map((s) => s.kind)).toEqual(['md', 'chart', 'md']);
		const chart = segs[1];
		expect(chart.kind).toBe('chart');
		if (chart.kind === 'chart') {
			expect(chart.spec.type).toBe('bar');
			expect(chart.spec.data).toHaveLength(1);
		}
	});

	it('parses multiple chart fences in order', () => {
		const text = [
			'```chart',
			'{"type":"bar","data":[]}',
			'```',
			'',
			'Middle.',
			'',
			'```chart',
			'{"type":"pie","data":[]}',
			'```'
		].join('\n');
		const segs = splitChartSegments(text);
		const kinds = segs.map((s) => s.kind);
		expect(kinds).toEqual(['chart', 'md', 'chart']);
	});

	it('leaves malformed JSON as a literal markdown code block', () => {
		const text = '```chart\n{not json}\n```';
		const segs = splitChartSegments(text);
		expect(segs).toHaveLength(1);
		expect(segs[0].kind).toBe('md');
		if (segs[0].kind === 'md') {
			expect(segs[0].text).toContain('```chart');
			expect(segs[0].text).toContain('{not json}');
		}
	});

	it('rejects unknown chart types as malformed', () => {
		const text = '```chart\n{"type":"scatter","data":[]}\n```';
		const segs = splitChartSegments(text);
		expect(segs[0].kind).toBe('md');
	});

	it('rejects specs missing data array', () => {
		const text = '```chart\n{"type":"bar"}\n```';
		const segs = splitChartSegments(text);
		expect(segs[0].kind).toBe('md');
	});
});
