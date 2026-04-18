import { describe, it, expect, vi, afterEach } from 'vitest';
import { pickPills, type TopicPillItem } from './topic-pills-shuffle';

function pill(label: string, mobile = label): TopicPillItem {
	return { label, mobile, color: '#000', query: `q:${label}` };
}

afterEach(() => {
	vi.restoreAllMocks();
});

describe('pickPills', () => {
	const pool: TopicPillItem[] = [
		pill('A', 'a'),
		pill('BB'),
		pill('CCC'),
		pill('DDDD'),
		pill('EEEEE'),
		pill('FFFFFF'),
		pill('GGGGGGG'),
		pill('HHHHHHHH')
	];

	it('returns exactly visibleCount items when pool is larger', () => {
		const out = pickPills(pool, 6);
		expect(out.length).toBe(6);
	});

	it('returns at most pool.length items when visibleCount exceeds it', () => {
		const small = pool.slice(0, 3);
		const out = pickPills(small, 6);
		expect(out.length).toBe(3);
	});

	it('interleaves short and long by label length (flex-wrap balance)', () => {
		// Verify the interleave property directly — don't depend on shuffle
		// ordering. For any N-item output sorted-then-interleaved, consecutive
		// pairs alternate "short" / "long" relative to the median length.
		const out = pickPills(pool, 6);
		const lengths = out.map((p) => p.label.length);
		const sortedAsc = [...lengths].sort((a, b) => a - b);
		// Reconstruct the expected interleave from the sorted-asc lengths.
		const expected: number[] = [];
		let lo = 0;
		let hi = sortedAsc.length - 1;
		while (lo <= hi) {
			expected.push(sortedAsc[lo++]);
			if (lo <= hi) expected.push(sortedAsc[hi--]);
		}
		expect(lengths).toEqual(expected);
	});

	it('uses mobile label length when mobile=true', () => {
		// Pool where mobile and label lengths disagree — a mobile-unaware sort
		// would interleave on label length, producing a different order.
		const mixedPool: TopicPillItem[] = [
			{ label: 'long desktop label', mobile: 'tiny', color: '#000', query: 'q' },
			{ label: 'a', mobile: 'huge mobile label', color: '#000', query: 'q' }
		];
		const out = pickPills(mixedPool, 2, true);
		// mobile lengths: 4 ('tiny'), 17 ('huge mobile label'). Sort asc by
		// mobile length → [tiny, huge]; interleave of two items keeps order.
		expect(out.map((p) => p.mobile)).toEqual(['tiny', 'huge mobile label']);
	});

	it('never duplicates items across a pick', () => {
		const out = pickPills(pool, 6);
		const unique = new Set(out.map((p) => p.label));
		expect(unique.size).toBe(out.length);
	});
});
