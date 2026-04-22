// Parses ```chart <json>``` fenced blocks out of a markdown string.
// Returns a list of segments preserving source order: plain markdown segments
// are rendered as HTML via marked; chart segments render via <ChartBlock/>.
//
// Malformed chart fences are left as plain markdown — the default code-block
// rendering then shows them as a literal code block, which is the graceful
// fallback the synth-prompt promises.

export type ChartType = 'bar' | 'pie' | 'line';

export interface ChartSpec {
	type: ChartType;
	title?: string;
	data: Array<Record<string, unknown>>;
}

export type Segment = { kind: 'md'; text: string } | { kind: 'chart'; spec: ChartSpec };

// Match ```chart ... ``` fences (case-insensitive, at line start). Capture the
// body so we can JSON.parse it. Non-greedy body so two charts in one reply
// don't collapse into one segment.
const CHART_FENCE = /```chart\s*\n([\s\S]*?)\n?```/gim;

const VALID_TYPES: ReadonlySet<ChartType> = new Set(['bar', 'pie', 'line']);

function isValidSpec(value: unknown): value is ChartSpec {
	if (!value || typeof value !== 'object') return false;
	const v = value as Record<string, unknown>;
	if (!VALID_TYPES.has(v.type as ChartType)) return false;
	if (!Array.isArray(v.data)) return false;
	return true;
}

export function splitChartSegments(text: string): Segment[] {
	const segments: Segment[] = [];
	let cursor = 0;
	CHART_FENCE.lastIndex = 0;
	let match: RegExpExecArray | null;
	while ((match = CHART_FENCE.exec(text)) !== null) {
		const before = text.slice(cursor, match.index);
		if (before) segments.push({ kind: 'md', text: before });

		let spec: ChartSpec | null = null;
		try {
			const parsed: unknown = JSON.parse(match[1]);
			if (isValidSpec(parsed)) spec = parsed;
		} catch {
			// Fall through — leave the fence as a literal code block.
		}

		if (spec) {
			segments.push({ kind: 'chart', spec });
		} else {
			// Keep malformed fence verbatim so the user at least sees the data.
			segments.push({ kind: 'md', text: match[0] });
		}
		cursor = match.index + match[0].length;
	}
	const tail = text.slice(cursor);
	if (tail) segments.push({ kind: 'md', text: tail });
	return segments.length ? segments : [{ kind: 'md', text }];
}
