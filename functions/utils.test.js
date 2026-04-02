import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
	esc, row, confirmationHtml, stripMarkdown, extractSourcesFromText,
	sendSSE, checkRateLimit, parseADKStream,
	SPECIALIST_RESULT_KEYS, SPECIALIST_KEYS, TOOL_LABELS,
} from './utils.js';

// --- esc ---

describe('esc', () => {
	it('escapes &, <, >', () => {
		assert.equal(esc('a & b < c > d'), 'a &amp; b &lt; c &gt; d');
	});

	it('converts non-strings to string', () => {
		assert.equal(esc(42), '42');
		assert.equal(esc(null), 'null');
	});

	it('passes through safe strings', () => {
		assert.equal(esc('hello world'), 'hello world');
	});
});

// --- row ---

describe('row', () => {
	it('escapes value by default', () => {
		const html = row('Name', '<script>');
		assert.ok(html.includes('&lt;script&gt;'));
		assert.ok(html.includes('Name'));
	});

	it('renders raw HTML when raw=true', () => {
		const html = row('Link', '<a href="#">click</a>', true);
		assert.ok(html.includes('<a href="#">click</a>'));
	});
});

// --- confirmationHtml ---

describe('confirmationHtml', () => {
	it('extracts first name', () => {
		const html = confirmationHtml('John Doe');
		assert.ok(html.includes('Hey John,'));
	});

	it('falls back to "there" when name is empty', () => {
		const html = confirmationHtml('');
		assert.ok(html.includes('Hey there,'));
	});

	it('escapes HTML in name', () => {
		const html = confirmationHtml('<script> Doe');
		assert.ok(html.includes('&lt;script&gt;'));
		assert.ok(!html.includes('<script>'));
	});
});

// --- stripMarkdown ---

describe('stripMarkdown', () => {
	it('removes headings', () => {
		assert.equal(stripMarkdown('# Title\n## Subtitle'), 'Title\nSubtitle');
	});

	it('removes bold', () => {
		assert.equal(stripMarkdown('**bold text**'), 'bold text');
	});

	it('removes italic', () => {
		assert.equal(stripMarkdown('*italic text*'), 'italic text');
	});

	it('removes strikethrough', () => {
		assert.equal(stripMarkdown('~~deleted~~'), 'deleted');
	});

	it('removes inline code', () => {
		assert.equal(stripMarkdown('use `console.log`'), 'use');
	});

	it('converts links to text', () => {
		assert.equal(stripMarkdown('[click here](https://example.com)'), 'click here');
	});

	it('removes list markers', () => {
		assert.equal(stripMarkdown('- item one\n* item two\n+ item three'), 'item one\nitem two\nitem three');
	});

	it('removes ordered list markers', () => {
		assert.equal(stripMarkdown('1. first\n2. second'), 'first\nsecond');
	});

	it('removes blockquotes', () => {
		assert.equal(stripMarkdown('> quoted text'), 'quoted text');
	});

	it('collapses excess newlines', () => {
		assert.equal(stripMarkdown('a\n\n\n\nb'), 'a\n\nb');
	});
});

// --- extractSourcesFromText ---

describe('extractSourcesFromText', () => {
	it('extracts a standard markdown link', () => {
		const sources = extractSourcesFromText('- [Example](https://example.com)');
		assert.deepEqual(sources, [{ title: 'Example', url: 'https://example.com' }]);
	});

	it('extracts link with domain suffix', () => {
		const sources = extractSourcesFromText('- [Title](https://redirect.google.com/foo){example.com}');
		assert.deepEqual(sources, [{
			title: 'Title',
			url: 'https://redirect.google.com/foo',
			domain: 'example.com',
		}]);
	});

	it('extracts multiple links', () => {
		const text = '- [A](https://a.com)\n- [B](https://b.com){b.com}';
		const sources = extractSourcesFromText(text);
		assert.equal(sources.length, 2);
		assert.equal(sources[0].url, 'https://a.com');
		assert.equal(sources[1].url, 'https://b.com');
	});

	it('deduplicates by URL', () => {
		const text = '- [A](https://a.com)\n- [A again](https://a.com)';
		const sources = extractSourcesFromText(text);
		assert.equal(sources.length, 1);
	});

	it('returns empty array when no links', () => {
		const sources = extractSourcesFromText('No links here');
		assert.deepEqual(sources, []);
	});

	it('handles empty title', () => {
		const sources = extractSourcesFromText('[](https://example.com)');
		assert.equal(sources[0].title, '');
	});

	it('handles URLs with query params', () => {
		const sources = extractSourcesFromText('[Q](https://example.com/page?a=1&b=2)');
		assert.equal(sources[0].url, 'https://example.com/page?a=1&b=2');
	});
});

// --- sendSSE ---

describe('sendSSE', () => {
	it('writes SSE-formatted event', () => {
		let written = '';
		const mockRes = { write(chunk) { written += chunk; } };
		sendSSE(mockRes, 'progress', { stage: 'context', status: 'complete' });
		assert.equal(written, 'event: progress\ndata: {"stage":"context","status":"complete"}\n\n');
	});

	it('serializes complex data', () => {
		let written = '';
		const mockRes = { write(chunk) { written += chunk; } };
		sendSSE(mockRes, 'complete', { reply: 'hello', sources: [{ url: 'https://a.com' }] });
		assert.ok(written.startsWith('event: complete\ndata: '));
		const data = JSON.parse(written.split('data: ')[1].trim());
		assert.equal(data.reply, 'hello');
		assert.equal(data.sources[0].url, 'https://a.com');
	});
});

// --- checkRateLimit ---

describe('checkRateLimit', () => {
	it('allows requests under limit', () => {
		const map = new Map();
		const now = Date.now();
		assert.equal(checkRateLimit(map, '1.2.3.4', now, 600000, 20), true);
		assert.equal(checkRateLimit(map, '1.2.3.4', now + 1000, 600000, 20), true);
	});

	it('blocks at limit', () => {
		const map = new Map();
		const now = Date.now();
		for (let i = 0; i < 20; i++) {
			assert.equal(checkRateLimit(map, '1.2.3.4', now, 600000, 20), true);
		}
		assert.equal(checkRateLimit(map, '1.2.3.4', now, 600000, 20), false);
	});

	it('resets after window expires', () => {
		const map = new Map();
		const now = Date.now();
		for (let i = 0; i < 20; i++) {
			checkRateLimit(map, '1.2.3.4', now, 600000, 20);
		}
		assert.equal(checkRateLimit(map, '1.2.3.4', now, 600000, 20), false);
		// After window
		assert.equal(checkRateLimit(map, '1.2.3.4', now + 600001, 600000, 20), true);
	});

	it('tracks IPs independently', () => {
		const map = new Map();
		const now = Date.now();
		for (let i = 0; i < 20; i++) {
			checkRateLimit(map, '1.1.1.1', now, 600000, 20);
		}
		assert.equal(checkRateLimit(map, '1.1.1.1', now, 600000, 20), false);
		assert.equal(checkRateLimit(map, '2.2.2.2', now, 600000, 20), true);
	});
});

// --- Constants ---

describe('constants', () => {
	it('SPECIALIST_RESULT_KEYS has 9 entries', () => {
		assert.equal(SPECIALIST_RESULT_KEYS.length, 9);
	});

	it('SPECIALIST_KEYS is a Set matching SPECIALIST_RESULT_KEYS', () => {
		assert.ok(SPECIALIST_KEYS instanceof Set);
		assert.equal(SPECIALIST_KEYS.size, 9);
		for (const key of SPECIALIST_RESULT_KEYS) {
			assert.ok(SPECIALIST_KEYS.has(key), `Missing ${key}`);
		}
	});

	it('TOOL_LABELS maps all specialist agent names', () => {
		assert.equal(TOOL_LABELS.market_landscape, 'Market Landscape');
		assert.equal(TOOL_LABELS.guest_intelligence, 'Guest Intelligence');
		assert.equal(TOOL_LABELS.dynamic_researcher_1, 'Research');
	});
});

// --- parseADKStream ---

function mockReader(chunks) {
	const encoder = new TextEncoder();
	let i = 0;
	return {
		read() {
			if (i >= chunks.length) return Promise.resolve({ done: true, value: undefined });
			return Promise.resolve({ done: false, value: encoder.encode(chunks[i++]) });
		}
	};
}

function adkEvent(overrides = {}) {
	return JSON.stringify({
		actions: { stateDelta: {}, ...overrides.actions },
		content: overrides.content || { parts: [] },
		author: overrides.author || '',
		partial: overrides.partial ?? null,
	});
}

describe('parseADKStream', () => {
	it('extracts final_report as reply', async () => {
		const reader = mockReader([
			`data: ${adkEvent({ actions: { stateDelta: { final_report: 'The full report.' } } })}\n\n`
		]);
		const events = [];
		const result = await parseADKStream(reader, (e, d) => events.push({ e, d }));
		assert.equal(result.reply, 'The full report.');
	});

	it('extracts router_response as routerResponse', async () => {
		const reader = mockReader([
			`data: ${adkEvent({ actions: { stateDelta: { router_response: 'Please clarify.' } } })}\n\n`
		]);
		const events = [];
		const result = await parseADKStream(reader, (e, d) => events.push({ e, d }));
		assert.equal(result.routerResponse, 'Please clarify.');
		assert.equal(result.reply, '');
	});

	it('scope_plan in stream is ignored (not used as reply)', async () => {
		const reader = mockReader([
			`data: ${adkEvent({ actions: { stateDelta: { scope_plan: 'Here is the plan.' } } })}\n\n`
		]);
		const events = [];
		const result = await parseADKStream(reader, (e, d) => events.push({ e, d }));
		assert.equal(result.reply, '');
	});

	it('emits context progress with name/rating/reviews', async () => {
		const placesCtx = 'Name: Shake Shack\nRating: 4.5\n1,234 reviews';
		const reader = mockReader([
			`data: ${adkEvent({ actions: { stateDelta: { places_context: placesCtx } } })}\n\n`
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const ctx = events.find(ev => ev.d.stage === 'context');
		assert.ok(ctx);
		assert.equal(ctx.d.status, 'complete');
		assert.ok(ctx.d.label.includes('Shake Shack'));
		assert.ok(ctx.d.label.includes('4.5★'));
		assert.ok(ctx.d.label.includes('1,234 reviews'));
	});

	it('emits planning progress on research_plan', async () => {
		const reader = mockReader([
			`data: ${adkEvent({ actions: { stateDelta: { research_plan: 'plan text' } } })}\n\n`
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const planning = events.find(ev => ev.d.stage === 'planning');
		assert.ok(planning);
		assert.equal(planning.d.status, 'complete');
	});

	it('emits specialists running on set_specialist_briefs call', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'set_specialist_briefs', args: { briefs: { market_landscape: 'Investigate...', guest_intelligence: 'Analyze...' } } } }] },
				author: 'research_orchestrator',
				partial: false,
			})}\n\n`
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const running = events.find(ev => ev.d.stage === 'specialists' && ev.d.status === 'running');
		assert.ok(running);
		assert.ok(running.d.label.includes('Market Landscape'));
		assert.ok(running.d.label.includes('Guest Intelligence'));
	});

	it('emits individual specialist completion with preview', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: { market_result: '## Market\nThe market is growing rapidly with new entrants.' } },
				content: { parts: [] },
				author: 'market_landscape',
				partial: false,
			})}\n\n`
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const complete = events.find(ev => ev.d.stage === 'market_landscape' && ev.d.status === 'complete');
		assert.ok(complete);
		assert.ok(complete.d.preview.includes('market is growing'));
	});

	it('emits synthesis progress and tokens for synthesizer', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ text: 'Analyzing' }] },
				author: 'synthesizer',
				partial: true,
			})}\n\n`
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const progress = events.find(ev => ev.e === 'progress' && ev.d.stage === 'synthesis');
		assert.ok(progress);
		const token = events.find(ev => ev.e === 'token');
		assert.ok(token);
		assert.equal(token.d.text, 'Analyzing');
	});

	it('extracts sources from specialist result text', async () => {
		const result = 'Analysis here.\n\n## Sources\n- [NYT](https://nyt.com){nyt.com}\n- [CNN](https://cnn.com)';
		const reader = mockReader([
			`data: ${adkEvent({ actions: { stateDelta: { market_result: result } } })}\n\n`
		]);
		const events = [];
		const { sources } = await parseADKStream(reader, (e, d) => events.push({ e, d }));
		assert.equal(sources.length, 2);
		assert.equal(sources[0].url, 'https://nyt.com');
		assert.equal(sources[0].domain, 'nyt.com');
		assert.equal(sources[1].url, 'https://cnn.com');
	});

	it('skips malformed JSON without crashing', async () => {
		const reader = mockReader([
			`data: {not valid json}\n\ndata: ${adkEvent({ actions: { stateDelta: { final_report: 'ok' } } })}\n\n`
		]);
		const events = [];
		const result = await parseADKStream(reader, (e, d) => events.push({ e, d }));
		assert.equal(result.reply, 'ok');
	});

	it('handles chunked events split across reads', async () => {
		const fullEvent = `data: ${adkEvent({ actions: { stateDelta: { final_report: 'chunked report' } } })}\n\n`;
		const mid = Math.floor(fullEvent.length / 2);
		const reader = mockReader([fullEvent.slice(0, mid), fullEvent.slice(mid)]);
		const events = [];
		const result = await parseADKStream(reader, (e, d) => events.push({ e, d }));
		assert.equal(result.reply, 'chunked report');
	});

	it('returns empty results for empty stream', async () => {
		const reader = mockReader([]);
		const events = [];
		const result = await parseADKStream(reader, (e, d) => events.push({ e, d }));
		assert.equal(result.reply, '');
		assert.equal(result.routerResponse, '');
		assert.equal(result.sources.length, 0);
		assert.equal(events.length, 0);
	});

	it('final_report is used as reply even when scope_plan present', async () => {
		const reader = mockReader([
			`data: ${adkEvent({ actions: { stateDelta: { scope_plan: 'plan' } } })}\n\n`,
			`data: ${adkEvent({ actions: { stateDelta: { final_report: 'report' } } })}\n\n`,
		]);
		const events = [];
		const result = await parseADKStream(reader, (e, d) => events.push({ e, d }));
		assert.equal(result.reply, 'report');
	});
});
