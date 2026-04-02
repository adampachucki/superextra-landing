// Pure utility functions extracted from index.js for testability.

// --- HTML helpers (email templates) ---

export function esc(s) {
	return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function row(label, value, raw = false) {
	return `<tr>
		<td style="padding:6px 12px 6px 0;color:#888;font-size:13px;white-space:nowrap">${esc(label)}</td>
		<td style="padding:6px 0;font-size:13px">${raw ? value : esc(value)}</td>
	</tr>`;
}

export function confirmationHtml(name) {
	const firstName = esc(name.split(' ')[0] || 'there');
	return `<div style="font-family:sans-serif;max-width:520px;color:#1a1a1a;font-size:14px;line-height:1.6">
<p>Hey ${firstName},</p>
<p>I'm Adam, co-founder of Superextra.</p>
<p>We believe the restaurant industry deserves better access to reliable information, and we're building Superextra to make that happen.</p>
<p>This is an automated message, but I'll follow up personally soon.</p>
<p>In the meantime, it would help to know:</p>
<ol>
<li>What challenges can we help you solve?</li>
<li>What information would make the biggest difference?</li>
<li>How did you find us?</li>
</ol>
<p>Just hit reply and let me know.</p>
<p>Best,<br>Adam</p>
</div>`;
}

// --- Markdown / source extraction ---

export function stripMarkdown(text) {
	return text
		.replace(/^#{1,6}\s+/gm, '')          // headings
		.replace(/\*\*(.+?)\*\*/g, '$1')       // bold
		.replace(/\*(.+?)\*/g, '$1')           // italic
		.replace(/~~(.+?)~~/g, '$1')           // strikethrough
		.replace(/`{1,3}[^`]*`{1,3}/g, '')    // inline/block code
		.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // links → text only
		.replace(/^[-*+]\s+/gm, '')            // unordered list markers
		.replace(/^\d+\.\s+/gm, '')            // ordered list markers
		.replace(/^>\s+/gm, '')                // blockquotes
		.replace(/\n{3,}/g, '\n\n')            // collapse excess newlines
		.trim();
}

// Extract markdown links from specialist result text: - [Title](URL){domain}
// The {domain} suffix is optional — when present it carries the real source domain
// (the URL itself may be a vertexaisearch.cloud.google.com redirect).
const MD_LINK_RE = /\[([^\]]*)\]\((https?:\/\/[^)]+)\)(?:\{([^}]*)\})?/g;

export function extractSourcesFromText(text) {
	const sources = [];
	let match;
	while ((match = MD_LINK_RE.exec(text)) !== null) {
		const url = match[2];
		if (!sources.some(s => s.url === url)) {
			sources.push({ title: match[1] || '', url, ...(match[3] && { domain: match[3] }) });
		}
	}
	MD_LINK_RE.lastIndex = 0;
	return sources;
}

// --- SSE helpers ---

export function sendSSE(res, event, data) {
	res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

// --- Rate limiting ---

/**
 * Check and update rate limit for an IP.
 * @returns {boolean} true if request is allowed, false if rate limited
 */
export function checkRateLimit(map, ip, now, windowMs, maxRequests) {
	const entry = map.get(ip);
	if (entry && now - entry.start < windowMs) {
		if (entry.count >= maxRequests) return false;
		entry.count++;
	} else {
		map.set(ip, { start: now, count: 1 });
	}
	return true;
}

// --- Constants ---

export const SPECIALIST_RESULT_KEYS = [
	'market_result', 'pricing_result', 'revenue_result', 'guest_result',
	'location_result', 'ops_result', 'marketing_result',
	'dynamic_result_1', 'dynamic_result_2',
];

export const SPECIALIST_KEYS = new Set([
	'guest_result', 'pricing_result', 'revenue_result', 'market_result',
	'location_result', 'ops_result', 'marketing_result',
	'dynamic_result_1', 'dynamic_result_2',
]);

export const TOOL_LABELS = {
	market_landscape: 'Market Landscape',
	menu_pricing: 'Menu & Pricing',
	revenue_sales: 'Revenue & Sales',
	guest_intelligence: 'Guest Intelligence',
	location_traffic: 'Location & Traffic',
	operations: 'Operations',
	marketing_digital: 'Marketing & Digital',
	dynamic_researcher_1: 'Research',
	dynamic_researcher_2: 'Research',
};

export const SPECIALIST_OUTPUT_KEYS = {
	market_landscape: 'market_result',
	menu_pricing: 'pricing_result',
	revenue_sales: 'revenue_result',
	guest_intelligence: 'guest_result',
	location_traffic: 'location_result',
	operations: 'ops_result',
	marketing_digital: 'marketing_result',
	dynamic_researcher_1: 'dynamic_result_1',
	dynamic_researcher_2: 'dynamic_result_2',
};

// --- ADK stream parser ---

/**
 * Parse ADK SSE stream events and emit frontend-facing SSE events.
 *
 * @param {object} reader - ReadableStream-like reader with read() returning {done, value}
 * @param {(event: string, data: object) => void} emit - Callback for emitting SSE events
 * @returns {Promise<{reply: string, routerResponse: string, sources: object[]}>}
 */
export async function parseADKStream(reader, emit) {
	const decoder = new TextDecoder();
	let buffer = '';
	let reply = '';
	let routerResponse = '';
	const sources = [];
	let synthesisStarted = false;
	let contextDone = false;
	let planningDone = false;

	while (true) {
		const { done, value } = await reader.read();
		if (done) break;

		buffer += decoder.decode(value, { stream: true });

		let boundary;
		while ((boundary = buffer.indexOf('\n\n')) !== -1) {
			const block = buffer.slice(0, boundary);
			buffer = buffer.slice(boundary + 2);

			for (const line of block.split('\n')) {
				if (!line.startsWith('data: ')) continue;
				try {
					const evt = JSON.parse(line.slice(6));
					const delta = evt.actions?.stateDelta || {};
					const deltaKeys = Object.keys(delta);
					const parts = evt.content?.parts || [];
					const author = evt.author || '';

					// 1. Context enricher complete
					if (delta.places_context && !contextDone) {
						contextDone = true;
						let label = 'Place data gathered';
						const ctx = typeof delta.places_context === 'string' ? delta.places_context : '';
						const nameMatch = ctx.match(/(?:Name|Display\s*Name):\s*(.+?)(?:\n|$)/i);
						const ratingMatch = ctx.match(/Rating:\s*([\d.]+)/i);
						const reviewMatch = ctx.match(/([\d,]+)\s*review/i);
						if (nameMatch) {
							label = nameMatch[1].replace(/[*#_]/g, '').trim();
							if (ratingMatch) label += ` — ${ratingMatch[1]}★`;
							if (reviewMatch) label += ` · ${reviewMatch[1]} reviews`;
						}
						emit('progress', { stage: 'context', status: 'complete', label });
					}

					// 2. Research plan complete (orchestrator set_specialist_briefs or output)
					if (delta.research_plan && !planningDone) {
						planningDone = true;
						emit('progress', { stage: 'planning', status: 'complete', label: 'Research planned' });
					}

					// 3. Orchestrator assigned specialists via set_specialist_briefs
					const briefsCall = parts.find(p => p.functionCall?.name === 'set_specialist_briefs');
					if (briefsCall) {
						const briefKeys = Object.keys(briefsCall.functionCall.args?.briefs || {});
						const labels = briefKeys.map(k => TOOL_LABELS[k]).filter(Boolean);
						if (labels.length) {
							emit('progress', { stage: 'specialists', status: 'running', label: `Researching: ${labels.join(', ')}` });
						}
					}

					// 4. Individual specialist google_search calls
					if (TOOL_LABELS[author]) {
						const searchCall = parts.find(p => p.functionCall?.name === 'google_search');
						if (searchCall) {
							const query = searchCall.functionCall.args?.query;
							if (query) {
								emit('progress', {
									stage: author,
									status: 'searching',
									label: `Searching: "${query.length > 80 ? query.slice(0, 77) + '...' : query}"`,
								});
							}
						}
					}

					// 5. Individual specialist completion (output_key in stateDelta)
					if (TOOL_LABELS[author]) {
						const outputKey = SPECIALIST_OUTPUT_KEYS[author];
						if (outputKey && delta[outputKey] && typeof delta[outputKey] === 'string' && delta[outputKey] !== 'NOT_RELEVANT') {
							const text = delta[outputKey].replace(/[#*_\n]+/g, ' ').replace(/\s+/g, ' ').trim();
							const preview = text.slice(0, 120) + (text.length > 120 ? '...' : '');
							emit('progress', {
								stage: author,
								status: 'complete',
								label: TOOL_LABELS[author],
								preview,
							});
						}
					}

					// 6. Synthesizer streaming tokens
					if (author === 'synthesizer' && evt.partial === true) {
						if (!synthesisStarted) {
							synthesisStarted = true;
							emit('progress', { stage: 'synthesis', status: 'running', label: 'Synthesizing findings' });
						}
						const text = parts.find(p => p.text)?.text;
						if (text) emit('token', { text });
					}

					// 7. Final report
					if (delta.final_report) reply = delta.final_report;

					// 8. Router response
					if (delta.router_response && !reply) routerResponse = delta.router_response;

					// 9. Extract sources from specialist results
					for (const key of SPECIALIST_RESULT_KEYS) {
						if (delta[key]) {
							for (const s of extractSourcesFromText(delta[key])) {
								if (!sources.some(x => x.url === s.url)) {
									sources.push(s);
								}
							}
						}
					}
				} catch (e) {
					console.warn('[stream] Malformed SSE event, skipping:', line.slice(0, 200), e.message);
				}
			}
		}
	}

	return { reply, routerResponse, sources };
}
