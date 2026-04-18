/**
 * Shuffle + short/long interleave for topic pills.
 *
 * The non-obvious piece: after picking N random items, we sort by label
 * length and then interleave from both ends (shortest, longest,
 * second-shortest, second-longest, …). This keeps flex-wrap rows from
 * collapsing into a lopsided short-on-top / long-on-bottom layout.
 */

export interface TopicPillItem {
	label: string;
	mobile: string;
	color: string;
	query: string;
}

export function shuffle<T>(arr: readonly T[]): T[] {
	const a = [...arr];
	for (let i = a.length - 1; i > 0; i--) {
		const j = Math.floor(Math.random() * (i + 1));
		[a[i], a[j]] = [a[j], a[i]];
	}
	return a;
}

export function pickPills(
	pool: readonly TopicPillItem[],
	visibleCount: number,
	mobile = false
): TopicPillItem[] {
	const picked = shuffle(pool).slice(0, visibleCount);
	const key = (p: TopicPillItem) => (mobile ? p.mobile : p.label).length;
	picked.sort((a, b) => key(a) - key(b));
	const ordered: TopicPillItem[] = [];
	let lo = 0;
	let hi = picked.length - 1;
	while (lo <= hi) {
		ordered.push(picked[lo++]);
		if (lo <= hi) ordered.push(picked[hi--]);
	}
	return ordered;
}
