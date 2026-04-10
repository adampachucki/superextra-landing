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
	'location_result', 'ops_result', 'marketing_result', 'review_result',
	'dynamic_result_1', 'dynamic_result_2',
];

export const SPECIALIST_KEYS = new Set([
	'guest_result', 'pricing_result', 'revenue_result', 'market_result',
	'location_result', 'ops_result', 'marketing_result', 'review_result',
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

export const PLACES_TOOL_LABELS = {
	get_restaurant_details: 'Loading restaurant details',
	find_nearby_restaurants: 'Finding nearby competitors',
	search_restaurants: 'Searching restaurants',
};

/**
 * Extract the last complete sentence (>10 chars) from text.
 * Strips markdown before splitting.
 */
export function extractLastSentence(text) {
	const plain = stripMarkdown(text);
	const sentences = plain.split(/(?<=[.!?])\s+/).filter(s => s.length > 10);
	if (sentences.length === 0) return '';
	const last = sentences[sentences.length - 1].trim();
	return last.length > 120 ? last.slice(0, 117) + '...' : last;
}

// --- ADK stream parser ---

/**
 * Extract displayName from a Places API place object.
 * Handles both { text: "..." } (Google API) and plain string forms.
 */
function extractPlaceName(place) {
	if (!place) return '';
	const dn = place.displayName;
	return (typeof dn === 'object' ? dn?.text : dn) || '';
}

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

	// Activity tracking
	let activitySeq = 0;
	const pendingSearchesByAuthor = new Map(); // author → Set<activityId>
	const emittedSourceUrls = new Set();
	const placeIdToName = new Map();            // place_id → displayName (from search/nearby responses)
	const discoveredPlaceNames = [];             // accumulated place names for typewriter detail
	let placesTotal = 0;                         // total places found from search/nearby
	let placesCompleted = 0;                     // how many get_restaurant_details responses received
	let checkEmitted = false;                    // whether data-check activity has been emitted
	let totalSpecialists = 0;                    // specialist count from set_specialist_briefs
	let completedSpecialists = 0;                // how many specialists have completed

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

					// 0a. Context enricher Places API tool calls → aggregated data-check counter
					if (author === 'context_enricher') {
						for (const p of parts) {
							const fc = p.functionCall;
							if (!fc || !PLACES_TOOL_LABELS[fc.name]) continue;

							if (fc.name === 'find_nearby_restaurants' || fc.name === 'search_restaurants') {
								if (!checkEmitted) {
									checkEmitted = true;
									emit('activity', {
										id: 'data-check',
										category: 'data',
										status: 'running',
										label: 'Checking nearby places',
										agent: 'context_enricher',
									});
								}
							}
							if (fc.name === 'get_restaurant_details') {
								if (!checkEmitted) {
									// First detail call (primary place from prompt)
									emit('activity', {
										id: 'data-primary',
										category: 'data',
										status: 'running',
										label: 'Loading place details',
										agent: 'context_enricher',
									});
								} else {
									// Advance counter on each call (fallback when functionResponse missing)
									placesCompleted++;
									const placeId = fc.args?.place_id || '';
									const knownName = placeIdToName.get(placeId);
									if (knownName && !discoveredPlaceNames.includes(knownName)) {
										discoveredPlaceNames.push(knownName);
									}
									const counterLabel = placesTotal > 0
										? `Checking nearby places: ${placesCompleted}/${placesTotal}`
										: `Checking nearby places: ${placesCompleted}`;
									emit('activity', {
										id: 'data-check',
										category: 'data',
										status: 'running',
										label: counterLabel,
										detail: discoveredPlaceNames.length > 0 ? discoveredPlaceNames.join(', ') : undefined,
										agent: 'context_enricher',
									});
								}
							}
						}
					}

					// 0b. Context enricher functionResponse → update counter + detail
					if (author === 'context_enricher') {
						for (const p of parts) {
							const fr = p.functionResponse;
							if (!fr) continue;

							if (fr.name === 'find_nearby_restaurants' || fr.name === 'search_restaurants') {
								const results = fr.response?.results || [];
								for (const r of results) {
									const name = extractPlaceName(r);
									if (r.id && name) placeIdToName.set(r.id, name);
								}
								placesTotal += results.length;
								if (!checkEmitted) checkEmitted = true;
								emit('activity', {
									id: 'data-check',
									category: 'data',
									status: 'running',
									label: `Checking nearby places: ${placesTotal}`,
									agent: 'context_enricher',
								});
							}

							if (fr.name === 'get_restaurant_details') {
								const place = fr.response?.place;
								if (place) {
									const name = extractPlaceName(place);
									const placeDetail = name
										? (place.userRatingCount ? `${name}, ${place.userRatingCount.toLocaleString()} reviews` : name)
										: '';

									if (!checkEmitted) {
										// Primary place response
										emit('activity', {
											id: 'data-primary',
											category: 'data',
											status: 'complete',
											label: 'Loading place details',
											detail: placeDetail || undefined,
											agent: 'context_enricher',
										});
									} else {
										// Accumulate place name (upgrade plain name → enriched)
										if (placeDetail) {
											const plainIdx = discoveredPlaceNames.indexOf(name);
											if (plainIdx >= 0) {
												discoveredPlaceNames[plainIdx] = placeDetail;
											} else if (!discoveredPlaceNames.includes(placeDetail)) {
												discoveredPlaceNames.push(placeDetail);
											}
										}
										emit('activity', {
											id: 'data-check',
											category: 'data',
											status: 'running',
											detail: discoveredPlaceNames.length > 0 ? discoveredPlaceNames.join(', ') : undefined,
											agent: 'context_enricher',
										});
									}
								}
							}
						}
					}

					// 1. Context enricher complete
					if (delta.places_context && !contextDone) {
						contextDone = true;
						let label = 'Place data gathered';
						const ctx = typeof delta.places_context === 'string' ? delta.places_context : '';
						const nameMatch = ctx.match(/(?:Name|Display\s*Name):\s*(.+?)(?:\n|$)/i);
						const reviewMatch = ctx.match(/([\d,]+)\s*review/i);
						if (nameMatch) {
							label = nameMatch[1].replace(/[*#_]/g, '').trim();
							if (reviewMatch) label += ` · ${reviewMatch[1]} reviews`;
						}
						emit('progress', { stage: 'context', status: 'complete', label });
						// Finalize counter with completed count
						if (checkEmitted) {
							const finalLabel = placesTotal > 0
								? `Checking nearby places: ${placesTotal}/${placesTotal}`
								: 'Checking nearby places';
							emit('activity', {
								id: 'data-check',
								category: 'data',
								status: 'complete',
								label: finalLabel,
								agent: 'context_enricher',
							});
						}
						emit('activity', { category: 'data', status: 'all-complete' });
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
						// activity:analyze — pending for each specialist
						for (const k of briefKeys) {
							if (TOOL_LABELS[k]) {
								emit('activity', {
									id: `analyze-${k}`,
									category: 'analyze',
									status: 'pending',
									label: TOOL_LABELS[k],
									agent: k,
								});
							}
						}
						// activity:search — aggregate "Searching the web" counter
						totalSpecialists = briefKeys.filter(k => TOOL_LABELS[k]).length;
						completedSpecialists = 0;
						if (totalSpecialists > 0) {
							emit('activity', {
								id: 'search-web',
								category: 'search',
								status: 'running',
								label: 'Searching the web',
								agent: 'research_orchestrator',
							});
						}
					}

					// 4. google_search calls from any agent → activity:search
					{
						const searchCall = parts.find(p => p.functionCall?.name === 'google_search');
						if (searchCall) {
							const query = searchCall.functionCall.args?.query;
							if (query) {
								// Existing progress event for specialists
								if (TOOL_LABELS[author]) {
									emit('progress', {
										stage: author,
										status: 'searching',
										label: `Searching: "${query.length > 80 ? query.slice(0, 77) + '...' : query}"`,
									});
								}
								// activity:search for all agents
								const searchId = `search-${activitySeq++}`;
								emit('activity', {
									id: searchId,
									category: 'search',
									status: 'running',
									label: query.length > 80 ? query.slice(0, 77) + '...' : query,
									agent: author,
								});
								if (!pendingSearchesByAuthor.has(author)) pendingSearchesByAuthor.set(author, new Set());
								pendingSearchesByAuthor.get(author).add(searchId);
							}
						}
					}

					// 4b. Grounding search queries from state delta (model-side grounding, not function call)
					{
						const queries = delta._web_search_queries;
						if (queries && Array.isArray(queries)) {
							for (const q of queries) {
								if (typeof q !== 'string' || !q.trim()) continue;
								const searchId = `search-${activitySeq++}`;
								emit('activity', {
									id: searchId,
									category: 'search',
									status: 'complete',
									label: q.length > 80 ? q.slice(0, 77) + '...' : q,
									agent: author,
								});
							}
						}
					}

					// 4c. Fallback: grounding metadata directly on event
					{
						const gQueries = evt.groundingMetadata?.webSearchQueries;
						if (gQueries && Array.isArray(gQueries) && !delta._web_search_queries) {
							for (const q of gQueries) {
								if (typeof q !== 'string' || !q.trim()) continue;
								const searchId = `search-${activitySeq++}`;
								emit('activity', {
									id: searchId,
									category: 'search',
									status: 'complete',
									label: q.length > 80 ? q.slice(0, 77) + '...' : q,
									agent: author,
								});
							}
						}
					}

					// 4d. Specialist partial text → activity:analyze (sentence excerpt)
					if (TOOL_LABELS[author] && evt.partial === true && author !== 'synthesizer') {
						const partialText = parts.find(p => p.text)?.text;
						if (partialText) {
							const sentence = extractLastSentence(partialText);
							if (sentence) {
								// Complete any pending searches for this author
								const pending = pendingSearchesByAuthor.get(author);
								if (pending?.size) {
									for (const sid of pending) {
										emit('activity', { id: sid, category: 'search', status: 'complete', agent: author });
									}
									pending.clear();
								}
								emit('activity', {
									id: `analyze-${author}`,
									category: 'analyze',
									status: 'running',
									label: TOOL_LABELS[author],
									detail: sentence,
									agent: author,
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
							// Complete pending searches for this author
							const pending = pendingSearchesByAuthor.get(author);
							if (pending?.size) {
								for (const sid of pending) {
									emit('activity', { id: sid, category: 'search', status: 'complete', agent: author });
								}
								pending.clear();
							}
							// activity:analyze — complete
							emit('activity', {
								id: `analyze-${author}`,
								category: 'analyze',
								status: 'complete',
								label: TOOL_LABELS[author],
								detail: preview,
								agent: author,
							});
							// activity:read — sources from this specialist's output
							for (const s of extractSourcesFromText(delta[outputKey])) {
								if (!emittedSourceUrls.has(s.url)) {
									emittedSourceUrls.add(s.url);
									emit('activity', {
										id: `read-${activitySeq++}`,
										category: 'read',
										status: 'complete',
										label: s.domain || (() => { try { const h = new URL(s.url).hostname; return h.includes('vertexaisearch') ? (s.title || 'Source') : h; } catch { return s.title || 'Source'; } })(),
										detail: s.title || '',
										url: s.url,
										agent: author,
									});
								}
							}
							// activity:search — update web search counter
							completedSpecialists++;
							if (totalSpecialists > 0) {
								emit('activity', {
									id: 'search-web',
									category: 'search',
									status: completedSpecialists >= totalSpecialists ? 'complete' : 'running',
									label: `Searching the web (${completedSpecialists}/${totalSpecialists})`,
									detail: completedSpecialists < totalSpecialists ? TOOL_LABELS[author] : undefined,
									agent: 'research_orchestrator',
								});
							}
						}
					}

					// 6. Synthesizer streaming tokens
					if (author === 'synthesizer' && evt.partial === true) {
						if (!synthesisStarted) {
							synthesisStarted = true;
							emit('progress', { stage: 'synthesis', status: 'running', label: 'Synthesizing findings' });
							emit('activity', {
								id: 'analyze-synthesizer',
								category: 'analyze',
								status: 'running',
								label: 'Synthesizing findings',
								agent: 'synthesizer',
							});
						}
						const text = parts.find(p => p.text)?.text;
						if (text) emit('token', { text });
					}

					// 7. Final report
					if (delta.final_report) {
						reply = delta.final_report;
						emit('activity', {
							id: 'analyze-synthesizer',
							category: 'analyze',
							status: 'complete',
							label: 'Research complete',
							agent: 'synthesizer',
						});
					}

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
