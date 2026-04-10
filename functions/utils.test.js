import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
	esc, row, confirmationHtml, stripMarkdown, extractSourcesFromText,
	sendSSE, checkRateLimit, parseADKStream, extractLastSentence,
	SPECIALIST_RESULT_KEYS, SPECIALIST_KEYS, TOOL_LABELS, PLACES_TOOL_LABELS,
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
	it('SPECIALIST_RESULT_KEYS has 10 entries', () => {
		assert.equal(SPECIALIST_RESULT_KEYS.length, 10);
	});

	it('SPECIALIST_KEYS is a Set matching SPECIALIST_RESULT_KEYS', () => {
		assert.ok(SPECIALIST_KEYS instanceof Set);
		assert.equal(SPECIALIST_KEYS.size, 10);
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
		assert.ok(!ctx.d.label.includes('★'), 'should not contain star symbol');
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

// --- extractLastSentence ---

describe('extractLastSentence', () => {
	it('returns last sentence from multi-sentence text', () => {
		const text = 'First sentence here. Second sentence is longer than ten characters. Third one too.';
		assert.equal(extractLastSentence(text), 'Third one too.');
	});

	it('returns empty string for short text', () => {
		assert.equal(extractLastSentence('Hi.'), '');
	});

	it('strips markdown before extracting', () => {
		assert.equal(
			extractLastSentence('## Title\nFirst sentence here. **Bold text** with a longer sentence here.'),
			'Bold text with a longer sentence here.'
		);
	});

	it('truncates to 120 chars', () => {
		const long = 'A'.repeat(150) + '.';
		const result = extractLastSentence(long);
		assert.ok(result.length <= 120);
		assert.ok(result.endsWith('...'));
	});

	it('returns empty for empty input', () => {
		assert.equal(extractLastSentence(''), '');
	});
});

// --- parseADKStream activity events ---

describe('parseADKStream activity events', () => {
	it('emits data-primary for first get_restaurant_details before search/nearby', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'get_restaurant_details', args: { place_id: 'ChIJ123' } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const data = events.find(ev => ev.e === 'activity' && ev.d.category === 'data');
		assert.ok(data);
		assert.equal(data.d.id, 'data-primary');
		assert.equal(data.d.status, 'running');
		assert.equal(data.d.label, 'Loading place details');
	});

	it('emits data-check counter on find_nearby_restaurants call', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'find_nearby_restaurants', args: { latitude: 40.7, longitude: -74.0 } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const check = events.find(ev => ev.e === 'activity' && ev.d.id === 'data-check');
		assert.ok(check);
		assert.equal(check.d.status, 'running');
		assert.equal(check.d.label, 'Checking nearby places');
	});

	it('emits all-complete for data when places_context set', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'get_restaurant_details', args: { place_id: 'x' } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: { places_context: 'Name: Test\n100 reviews' } },
				content: { parts: [] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const complete = events.find(ev => ev.e === 'activity' && ev.d.status === 'all-complete');
		assert.ok(complete);
		assert.equal(complete.d.category, 'data');
	});

	it('emits search activity for google_search from any agent', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'google_search', args: { query: 'orchestrator search query' } } }] },
				author: 'research_orchestrator',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'google_search', args: { query: 'specialist search query' } } }] },
				author: 'market_landscape',
				partial: null,
			})}\n\n`
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const searches = events.filter(ev => ev.e === 'activity' && ev.d.category === 'search');
		assert.equal(searches.length, 2);
		assert.equal(searches[0].d.label, 'orchestrator search query');
		assert.equal(searches[0].d.agent, 'research_orchestrator');
		assert.equal(searches[1].d.label, 'specialist search query');
		assert.equal(searches[1].d.agent, 'market_landscape');
	});

	it('marks searches complete when specialist outputs', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'google_search', args: { query: 'test query' } } }] },
				author: 'market_landscape',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: { market_result: 'The market analysis shows significant growth patterns in the region.' } },
				content: { parts: [] },
				author: 'market_landscape',
				partial: null,
			})}\n\n`
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const searches = events.filter(ev => ev.e === 'activity' && ev.d.category === 'search');
		assert.equal(searches.length, 2); // running + complete
		assert.equal(searches[0].d.status, 'running');
		assert.equal(searches[1].d.status, 'complete');
		assert.equal(searches[1].d.id, searches[0].d.id); // same ID updated
	});

	it('emits read activities from specialist source text', async () => {
		const result = 'Analysis here.\n\n## Sources\n- [NYC Eats](https://eater.com/nyc){eater.com}\n- [Grub](https://grubstreet.com)';
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: { market_result: result } },
				content: { parts: [] },
				author: 'market_landscape',
				partial: null,
			})}\n\n`
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const reads = events.filter(ev => ev.e === 'activity' && ev.d.category === 'read');
		assert.equal(reads.length, 2);
		assert.equal(reads[0].d.label, 'eater.com');
		assert.equal(reads[0].d.detail, 'NYC Eats');
		assert.equal(reads[0].d.url, 'https://eater.com/nyc');
		assert.equal(reads[1].d.url, 'https://grubstreet.com');
	});

	it('emits analyze pending on briefs, running on partial, complete on output', async () => {
		const reader = mockReader([
			// Briefs assigned
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'set_specialist_briefs', args: { briefs: { market_landscape: 'Investigate market.' } } } }] },
				author: 'research_orchestrator',
				partial: null,
			})}\n\n`,
			// Specialist partial text
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ text: 'The market landscape shows five direct competitors within a short distance.' }] },
				author: 'market_landscape',
				partial: true,
			})}\n\n`,
			// Specialist completes
			`data: ${JSON.stringify({
				actions: { stateDelta: { market_result: 'Full market analysis with significant findings about the competitive landscape.' } },
				content: { parts: [] },
				author: 'market_landscape',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const analyze = events.filter(ev => ev.e === 'activity' && ev.d.category === 'analyze');
		assert.ok(analyze.length >= 3);
		// pending
		const pending = analyze.find(a => a.d.status === 'pending');
		assert.ok(pending);
		assert.equal(pending.d.label, 'Market Landscape');
		// running with excerpt
		const running = analyze.find(a => a.d.status === 'running');
		assert.ok(running);
		assert.ok(running.d.detail.length > 0);
		// complete
		const complete = analyze.find(a => a.d.status === 'complete');
		assert.ok(complete);
		assert.equal(complete.d.label, 'Market Landscape');
	});

	it('emits synthesizer analyze activity', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ text: 'Based on' }] },
				author: 'synthesizer',
				partial: true,
			})}\n\n`
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const synth = events.find(ev => ev.e === 'activity' && ev.d.id === 'analyze-synthesizer');
		assert.ok(synth);
		assert.equal(synth.d.status, 'running');
		assert.equal(synth.d.label, 'Synthesizing findings');
	});

	it('emits search-web activity on set_specialist_briefs', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'set_specialist_briefs', args: { briefs: {
					market_landscape: 'brief1',
					menu_pricing: 'brief2',
					guest_intelligence: 'brief3',
				} } } }] },
				author: 'research_orchestrator',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const searchWeb = events.find(ev => ev.e === 'activity' && ev.d.id === 'search-web');
		assert.ok(searchWeb);
		assert.equal(searchWeb.d.status, 'running');
		assert.equal(searchWeb.d.label, 'Searching the web');
		assert.equal(searchWeb.d.category, 'search');
	});

	it('updates search-web counter as specialists complete', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'set_specialist_briefs', args: { briefs: {
					market_landscape: 'brief1',
					menu_pricing: 'brief2',
				} } } }] },
				author: 'research_orchestrator',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: { market_result: 'Full analysis of the competitive landscape.' } },
				content: { parts: [] },
				author: 'market_landscape',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const searchUpdates = events.filter(ev => ev.e === 'activity' && ev.d.id === 'search-web');
		const last = searchUpdates[searchUpdates.length - 1];
		assert.equal(last.d.label, 'Searching the web (1/2)');
		assert.equal(last.d.status, 'running');
		assert.equal(last.d.detail, 'Market Landscape');
	});

	it('marks search-web complete when all specialists done', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'set_specialist_briefs', args: { briefs: {
					market_landscape: 'brief1',
				} } } }] },
				author: 'research_orchestrator',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: { market_result: 'Full analysis.' } },
				content: { parts: [] },
				author: 'market_landscape',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const searchUpdates = events.filter(ev => ev.e === 'activity' && ev.d.id === 'search-web');
		const last = searchUpdates[searchUpdates.length - 1];
		assert.equal(last.d.status, 'complete');
		assert.equal(last.d.label, 'Searching the web (1/1)');
	});

	it('updates counter with total on find_nearby_restaurants functionResponse', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'find_nearby_restaurants', args: { latitude: 40.7, longitude: -74.0 } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionResponse: { name: 'find_nearby_restaurants', response: { status: 'success', results: [
					{ id: 'ChIJ1', displayName: { text: 'Shake Shack' } },
					{ id: 'ChIJ2', displayName: { text: 'Five Guys' } },
					{ id: 'ChIJ3', displayName: { text: 'Bareburger' } },
				] } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const checks = events.filter(ev => ev.e === 'activity' && ev.d.id === 'data-check');
		assert.equal(checks.length, 2); // initial + count update
		assert.equal(checks[1].d.label, 'Checking nearby places: 3');
	});

	it('builds place_id map and shows name on get_restaurant_details call', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'find_nearby_restaurants', args: {} } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionResponse: { name: 'find_nearby_restaurants', response: { status: 'success', results: [
					{ id: 'ChIJ_ABC', displayName: { text: 'Shake Shack' } },
				] } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'get_restaurant_details', args: { place_id: 'ChIJ_ABC' } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const checks = events.filter(ev => ev.e === 'activity' && ev.d.id === 'data-check');
		const withDetail = checks.find(c => c.d.detail === 'Shake Shack');
		assert.ok(withDetail);
	});

	it('updates counter on functionCall and detail on functionResponse', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'find_nearby_restaurants', args: {} } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionResponse: { name: 'find_nearby_restaurants', response: { status: 'success', results: [
					{ id: 'ChIJ1', displayName: { text: 'Shake Shack' } },
					{ id: 'ChIJ2', displayName: { text: 'Five Guys' } },
				] } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			// functionCall advances counter + shows known name
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'get_restaurant_details', args: { place_id: 'ChIJ1' } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			// functionResponse updates detail with full info
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionResponse: { name: 'get_restaurant_details', response: { status: 'success', place: {
					id: 'ChIJ1',
					displayName: { text: 'Shake Shack' },
					userRatingCount: 1234,
				} } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const checks = events.filter(ev => ev.e === 'activity' && ev.d.id === 'data-check');
		// functionCall should advance counter
		const callCheck = checks.find(c => c.d.label?.includes('1/2'));
		assert.ok(callCheck);
		assert.equal(callCheck.d.detail, 'Shake Shack');
		// functionResponse should update detail with reviews
		const respCheck = checks[checks.length - 1];
		assert.equal(respCheck.d.detail, 'Shake Shack, 1,234 reviews');
	});

	it('completes primary place detail with name and reviews (no stars)', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'get_restaurant_details', args: { place_id: 'ChIJ123' } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionResponse: { name: 'get_restaurant_details', response: { status: 'success', place: {
					id: 'ChIJ123',
					displayName: { text: 'Shake Shack' },
					rating: 4.5,
					userRatingCount: 1234,
				} } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const primary = events.filter(ev => ev.e === 'activity' && ev.d.id === 'data-primary');
		assert.equal(primary.length, 2); // running + complete
		assert.equal(primary[1].d.status, 'complete');
		assert.equal(primary[1].d.label, 'Loading place details');
		assert.equal(primary[1].d.detail, 'Shake Shack, 1,234 reviews');
		assert.ok(!primary[1].d.detail.includes('★'), 'should not contain star symbol');
	});

	it('handles displayName as plain string', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'get_restaurant_details', args: { place_id: 'ChIJplain' } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionResponse: { name: 'get_restaurant_details', response: { status: 'success', place: {
					id: 'ChIJplain',
					displayName: 'Plain Name Restaurant',
					userRatingCount: 500,
				} } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const primary = events.find(ev => ev.e === 'activity' && ev.d.id === 'data-primary' && ev.d.status === 'complete');
		assert.ok(primary);
		assert.ok(primary.d.detail.includes('Plain Name Restaurant'));
	});

	it('handles functionResponse with error status gracefully', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'get_restaurant_details', args: { place_id: 'ChIJerr' } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionResponse: { name: 'get_restaurant_details', response: { status: 'error', error_message: 'API error 401' } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const dataEvents = events.filter(ev => ev.e === 'activity' && ev.d.category === 'data');
		// Only the running event from functionCall — no crash, no update from error
		assert.equal(dataEvents.length, 1);
		assert.equal(dataEvents[0].d.status, 'running');
	});

	it('deduplicates read sources across specialists', async () => {
		const sharedSource = 'Text.\n\n## Sources\n- [Same](https://shared.com){shared.com}';
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: { market_result: sharedSource } },
				content: { parts: [] },
				author: 'market_landscape',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: { pricing_result: sharedSource } },
				content: { parts: [] },
				author: 'menu_pricing',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const reads = events.filter(ev => ev.e === 'activity' && ev.d.category === 'read');
		assert.equal(reads.length, 1); // deduplicated
	});

	it('accumulates place names in detail across multiple get_restaurant_details calls', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'find_nearby_restaurants', args: {} } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionResponse: { name: 'find_nearby_restaurants', response: { status: 'success', results: [
					{ id: 'ChIJ1', displayName: { text: 'Shake Shack' } },
					{ id: 'ChIJ2', displayName: { text: 'Five Guys' } },
				] } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'get_restaurant_details', args: { place_id: 'ChIJ1' } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ functionCall: { name: 'get_restaurant_details', args: { place_id: 'ChIJ2' } } }] },
				author: 'context_enricher',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const checks = events.filter(ev => ev.e === 'activity' && ev.d.id === 'data-check');
		const lastCheck = checks[checks.length - 1];
		assert.ok(lastCheck.d.detail.includes('Shake Shack'));
		assert.ok(lastCheck.d.detail.includes('Five Guys'));
	});

	it('emits search activities from _web_search_queries in stateDelta', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: { _web_search_queries: ['restaurant reviews NYC', 'best pizza Brooklyn'] } },
				content: { parts: [{ text: 'Some text' }] },
				author: 'market_landscape',
				partial: true,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const searches = events.filter(ev => ev.e === 'activity' && ev.d.category === 'search');
		assert.equal(searches.length, 2);
		assert.equal(searches[0].d.label, 'restaurant reviews NYC');
		assert.equal(searches[0].d.status, 'complete');
		assert.equal(searches[1].d.label, 'best pizza Brooklyn');
		assert.equal(searches[1].d.agent, 'market_landscape');
	});

	it('emits search activities from groundingMetadata.webSearchQueries', async () => {
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: {} },
				content: { parts: [{ text: 'Some text' }] },
				author: 'guest_intelligence',
				partial: true,
				groundingMetadata: { webSearchQueries: ['test grounding query'] },
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const searches = events.filter(ev => ev.e === 'activity' && ev.d.category === 'search');
		assert.equal(searches.length, 1);
		assert.equal(searches[0].d.label, 'test grounding query');
	});

	it('read activity label avoids vertexaisearch hostname', async () => {
		const source = 'Text.\n\n## Sources\n- [Yelp Review](https://vertexaisearch.cloud.google.com/redirect/abc)';
		const reader = mockReader([
			`data: ${JSON.stringify({
				actions: { stateDelta: { market_result: source } },
				content: { parts: [] },
				author: 'market_landscape',
				partial: null,
			})}\n\n`,
		]);
		const events = [];
		await parseADKStream(reader, (e, d) => events.push({ e, d }));
		const reads = events.filter(ev => ev.e === 'activity' && ev.d.category === 'read');
		assert.equal(reads.length, 1);
		assert.equal(reads[0].d.label, 'Yelp Review');
		assert.ok(!reads[0].d.label.includes('vertexaisearch'));
	});
});
