#!/usr/bin/env node

/**
 * Mock SSE server that replays realistic agent stream events.
 *
 * Usage:
 *   node scripts/mock-stream.js              # default "full-research" scenario
 *   node scripts/mock-stream.js quick        # router-only (no research pipeline)
 *   node scripts/mock-stream.js slow         # one specialist takes much longer
 *
 * Then in vite.config.ts, point the proxy at localhost:3099:
 *   '/api/agent/stream': { target: 'http://localhost:3099', ... }
 *
 * The server accepts POST to any path, ignores the body, and replays the scenario.
 */

import http from 'node:http';

const PORT = 3099;

// --- SSE helpers ---

function sse(res, event, data) {
	res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

function wait(ms) {
	return new Promise((r) => setTimeout(r, ms));
}

// --- Scenarios ---

/**
 * Each scenario is an async function that writes SSE events to `res`.
 * It should end by writing the `complete` event and calling `res.end()`.
 */

const FINAL_REPORT = `## Competitive Landscape Analysis: Shake Shack Union Square

### Market Position

Shake Shack Union Square operates in one of NYC's most competitive fast-casual dining corridors. The immediate 0.3-mile radius contains **5 direct competitors** including Bareburger, Smashburger, and Five Guys, plus 12 indirect competitors in the broader fast-casual segment.

### Pricing Analysis

Average burger price at Shake Shack ($9.29) sits **18% above** the category median ($7.89). However, the perceived value proposition remains strong: customer reviews mentioning "worth the price" outnumber "overpriced" complaints 3.2:1.

### Guest Sentiment

Across 1,234 Google reviews and 890 Yelp reviews, the dominant positive themes are:
- **Quality consistency** (mentioned in 42% of 4-5 star reviews)
- **Speed of service** (31%)
- **Shake quality** as a differentiator (28%)

The primary negative theme is **wait times during peak hours** (mentioned in 67% of 1-2 star reviews), particularly Friday/Saturday 12-2pm.

### Key Recommendations

1. **Off-peak incentives** — targeted promotions for 2-4pm could shift 15-20% of peak traffic
2. **Menu engineering** — the $5.49 chicken sandwich has the highest margin-to-popularity ratio
3. **Digital ordering** — competitors with kiosk/app ordering report 23% shorter perceived wait times`;

const SOURCES = [
	{
		title: 'NYC Burger Market Report 2026',
		url: 'https://eater.com/nyc-burger-report-2026',
		domain: 'eater.com'
	},
	{
		title: 'Shake Shack Menu Prices',
		url: 'https://thrillist.com/shake-shack-prices',
		domain: 'thrillist.com'
	},
	{
		title: 'Fast Casual Dining Trends',
		url: 'https://restaurant-dive.com/fast-casual-2026',
		domain: 'restaurant-dive.com'
	},
	{
		title: 'Union Square Dining Guide',
		url: 'https://grubstreet.com/union-square-restaurants',
		domain: 'grubstreet.com'
	},
	{
		title: 'Customer Review Analysis',
		url: 'https://yelp.com/biz/shake-shack-new-york',
		domain: 'yelp.com'
	},
	{
		title: 'Restaurant Foot Traffic Data',
		url: 'https://placer.ai/restaurant-trends',
		domain: 'placer.ai'
	}
];

async function fullResearch(res) {
	// Phase 1: Context enricher — primary place, then find nearby + detail each

	// Primary place detail (from user's prompt)
	await wait(400);
	sse(res, 'activity', {
		id: 'data-primary',
		category: 'data',
		status: 'running',
		label: 'Loading place details',
		agent: 'context_enricher'
	});
	await wait(600);
	sse(res, 'activity', {
		id: 'data-primary',
		category: 'data',
		status: 'complete',
		label: 'Loading place details: Shake Shack, 1,234 reviews',
		agent: 'context_enricher'
	});

	// find_nearby call
	await wait(300);
	sse(res, 'activity', {
		id: 'data-check',
		category: 'data',
		status: 'running',
		label: 'Checking nearby places',
		agent: 'context_enricher'
	});
	await wait(800);
	// find_nearby response → total count
	sse(res, 'activity', {
		id: 'data-check',
		category: 'data',
		status: 'running',
		label: 'Checking nearby places: 15',
		agent: 'context_enricher'
	});

	// Sequential get_restaurant_details for competitors
	const competitors = [
		{ name: 'Bareburger', reviews: 567 },
		{ name: 'Five Guys', reviews: 890 },
		{ name: 'Smashburger', reviews: 423 },
		{ name: 'Chipotle Mexican Grill', reviews: 2100 },
		{ name: 'Shake Shack Madison Square', reviews: 1876 },
		{ name: 'Umami Burger', reviews: 312 },
		{ name: 'Black Tap Craft Burgers', reviews: 1543 },
		{ name: "Joe's Pizza", reviews: 3456 },
		{ name: "Artichoke Basille's", reviews: 1876 },
		{ name: 'Di Fara Pizza', reviews: 890 },
		{ name: 'Prince Street Pizza', reviews: 2100 },
		{ name: 'Corner Bistro', reviews: 654 },
		{ name: 'Blue Smoke', reviews: 1200 },
		{ name: 'Gramercy Tavern', reviews: 3200 },
		{ name: 'Union Square Cafe', reviews: 2800 }
	];

	for (let i = 0; i < competitors.length; i++) {
		const c = competitors[i];

		// Show place name while loading
		sse(res, 'activity', {
			id: 'data-current',
			category: 'data',
			status: 'running',
			label: c.name,
			agent: 'context_enricher'
		});
		await wait(300 + Math.random() * 250);

		// Detail response → update counter + cycling name
		sse(res, 'activity', {
			id: 'data-check',
			category: 'data',
			status: 'running',
			label: `Checking nearby places: ${i + 1}/${competitors.length}`,
			agent: 'context_enricher'
		});
		sse(res, 'activity', {
			id: 'data-current',
			category: 'data',
			status: 'running',
			label: `${c.name}, ${c.reviews.toLocaleString()} reviews`,
			agent: 'context_enricher'
		});
		await wait(80);
	}

	// Context complete — finalize counter
	sse(res, 'activity', {
		id: 'data-check',
		category: 'data',
		status: 'complete',
		label: `Checking nearby places: ${competitors.length}/${competitors.length}`,
		agent: 'context_enricher'
	});
	sse(res, 'activity', { category: 'data', status: 'all-complete' });

	sse(res, 'progress', {
		stage: 'context',
		status: 'complete',
		label: 'Shake Shack — 4.5\u2605 \u00b7 1,234 reviews'
	});
	sse(res, 'activity', { category: 'data', status: 'all-complete' });

	// Phase 2: Orchestrator plans + assigns briefs
	await wait(500);
	sse(res, 'progress', { stage: 'planning', status: 'complete', label: 'Research planned' });

	await wait(300);
	const specialists = [
		'market_landscape',
		'menu_pricing',
		'guest_intelligence',
		'location_traffic',
		'marketing_digital'
	];
	const labels = {
		market_landscape: 'Market Landscape',
		menu_pricing: 'Menu & Pricing',
		guest_intelligence: 'Guest Intelligence',
		location_traffic: 'Location & Traffic',
		marketing_digital: 'Marketing & Digital'
	};
	sse(res, 'progress', {
		stage: 'specialists',
		status: 'running',
		label: `Researching: ${specialists.map((s) => labels[s]).join(', ')}`
	});
	for (const s of specialists) {
		sse(res, 'activity', {
			id: `analyze-${s}`,
			category: 'analyze',
			status: 'pending',
			label: labels[s],
			agent: s
		});
	}

	// Phase 3: Specialists search in parallel (staggered)
	const searches = [
		{ agent: 'market_landscape', query: 'shake shack competitors union square NYC 2026' },
		{ agent: 'menu_pricing', query: 'shake shack menu prices vs competitors NYC' },
		{ agent: 'guest_intelligence', query: 'shake shack union square customer reviews sentiment' },
		{ agent: 'market_landscape', query: 'fast casual burger market NYC growth trends' },
		{ agent: 'location_traffic', query: 'union square foot traffic restaurant data' },
		{ agent: 'marketing_digital', query: 'shake shack digital marketing social media presence' },
		{ agent: 'menu_pricing', query: 'NYC fast casual burger price comparison 2026' }
	];

	for (let i = 0; i < searches.length; i++) {
		await wait(200 + Math.random() * 300);
		const s = searches[i];
		sse(res, 'activity', {
			id: `search-${i}`,
			category: 'search',
			status: 'running',
			label: s.query,
			agent: s.agent
		});
		sse(res, 'progress', { stage: s.agent, status: 'searching', label: `Searching: "${s.query}"` });
	}

	// Phase 4: Specialists produce partial text, then complete (staggered)
	const completions = [
		{
			agent: 'market_landscape',
			delay: 1200,
			excerpts: [
				'Five direct competitors identified within 0.3 miles of the Union Square location.',
				'Bareburger and Smashburger represent the closest competitive threat in the premium burger segment.'
			],
			preview:
				'Five direct competitors within 0.3mi. Bareburger and Smashburger are the closest premium burger threats. Fast-casual segment growing 8% YoY.',
			sources: [SOURCES[0], SOURCES[3]]
		},
		{
			agent: 'menu_pricing',
			delay: 800,
			excerpts: [
				'Average burger price of $9.29 positions Shake Shack 18% above the category median.',
				'The chicken sandwich at $5.49 shows the highest margin-to-popularity ratio across the menu.'
			],
			preview:
				'Shake Shack burger at $9.29 is 18% above category median ($7.89). Chicken sandwich at $5.49 has highest margin-to-popularity ratio.',
			sources: [SOURCES[1]]
		},
		{
			agent: 'guest_intelligence',
			delay: 1500,
			excerpts: [
				'Quality consistency mentioned in 42% of positive reviews as the primary driver.',
				'Wait times during peak hours represent the dominant negative theme across all platforms.'
			],
			preview:
				'Quality consistency (42% of 4-5 star reviews), speed of service (31%), shake quality (28%). Peak wait times are the #1 complaint.',
			sources: [SOURCES[4]]
		},
		{
			agent: 'location_traffic',
			delay: 600,
			excerpts: [
				'Union Square station delivers approximately 32,000 daily commuters past the storefront.',
				'Friday and Saturday lunch sees 3.2x average foot traffic versus weekday baseline.'
			],
			preview:
				'32,000 daily commuters via Union Square station. Fri/Sat lunch sees 3.2x normal foot traffic. Peak congestion 12-2pm.',
			sources: [SOURCES[5]]
		},
		{
			agent: 'marketing_digital',
			delay: 900,
			excerpts: [
				'Instagram engagement rate of 4.2% significantly outperforms the fast-casual category average of 1.8%.'
			],
			preview:
				'Instagram engagement 4.2% vs 1.8% category average. Strong UGC pipeline. TikTok presence growing but underutilized.',
			sources: [SOURCES[2]]
		}
	];

	// Sort by delay to simulate parallel completion
	completions.sort((a, b) => a.delay - b.delay);

	let lastDelay = 0;
	for (const c of completions) {
		const gap = c.delay - lastDelay;
		lastDelay = c.delay;

		await wait(gap);

		// Complete searches for this agent
		for (let i = 0; i < searches.length; i++) {
			if (searches[i].agent === c.agent) {
				sse(res, 'activity', {
					id: `search-${i}`,
					category: 'search',
					status: 'complete',
					agent: c.agent
				});
			}
		}

		// Partial text excerpts (sentence rotation)
		for (const excerpt of c.excerpts) {
			sse(res, 'activity', {
				id: `analyze-${c.agent}`,
				category: 'analyze',
				status: 'running',
				label: labels[c.agent],
				detail: excerpt,
				agent: c.agent
			});
			await wait(400);
		}

		// Completion
		sse(res, 'progress', {
			stage: c.agent,
			status: 'complete',
			label: labels[c.agent],
			preview: c.preview
		});
		sse(res, 'activity', {
			id: `analyze-${c.agent}`,
			category: 'analyze',
			status: 'complete',
			label: labels[c.agent],
			detail: c.preview,
			agent: c.agent
		});

		// Sources
		for (const src of c.sources) {
			sse(res, 'activity', {
				id: `read-${src.domain}`,
				category: 'read',
				status: 'complete',
				label: src.domain,
				detail: src.title,
				url: src.url,
				agent: c.agent
			});
		}
	}

	// Phase 5: Synthesis
	await wait(500);
	sse(res, 'progress', { stage: 'synthesis', status: 'running', label: 'Synthesizing findings' });
	sse(res, 'activity', {
		id: 'analyze-synthesizer',
		category: 'analyze',
		status: 'running',
		label: 'Synthesizing findings',
		agent: 'synthesizer'
	});

	// Stream tokens in chunks (simulating real token streaming)
	const words = FINAL_REPORT.split(' ');
	for (let i = 0; i < words.length; i += 3) {
		const chunk = words.slice(i, i + 3).join(' ') + ' ';
		sse(res, 'token', { text: chunk });
		await wait(30 + Math.random() * 40);
	}

	await wait(200);
	sse(res, 'activity', {
		id: 'analyze-synthesizer',
		category: 'analyze',
		status: 'complete',
		label: 'Research complete',
		agent: 'synthesizer'
	});
	sse(res, 'complete', {
		reply: FINAL_REPORT,
		sources: SOURCES,
		title: 'Shake Shack Union Square Analysis'
	});
	res.end();
}

async function quickRouter(res) {
	// Router responds directly — no research pipeline
	await wait(800);

	const reply =
		"I'd be happy to help analyze a restaurant! Could you tell me which restaurant you'd like me to research? You can share the name and location, or select it from the search above.";
	const words = reply.split(' ');

	// No activity events — just tokens directly from router
	for (let i = 0; i < words.length; i += 2) {
		const chunk = words.slice(i, i + 2).join(' ') + ' ';
		sse(res, 'token', { text: chunk });
		await wait(40);
	}

	await wait(100);
	sse(res, 'complete', { reply, sources: [] });
	res.end();
}

async function slowSpecialist(res) {
	// Same as fullResearch but one specialist takes much longer
	await wait(300);

	// Primary place
	sse(res, 'activity', {
		id: 'data-primary',
		category: 'data',
		status: 'running',
		label: 'Loading place details',
		agent: 'context_enricher'
	});
	await wait(400);
	sse(res, 'activity', {
		id: 'data-primary',
		category: 'data',
		status: 'complete',
		label: "Loading place details: Joe's Pizza, 3,456 reviews",
		agent: 'context_enricher'
	});

	// find_nearby
	await wait(200);
	sse(res, 'activity', {
		id: 'data-check',
		category: 'data',
		status: 'running',
		label: 'Checking nearby places',
		agent: 'context_enricher'
	});
	await wait(400);
	sse(res, 'activity', {
		id: 'data-check',
		category: 'data',
		status: 'running',
		label: 'Checking nearby places: 6',
		agent: 'context_enricher'
	});

	// Sequential detail calls
	const competitors = [
		{ name: 'Prince Street Pizza', reviews: 2100 },
		{ name: "Artichoke Basille's", reviews: 1876 },
		{ name: 'Di Fara Pizza', reviews: 890 },
		{ name: 'Corner Bistro', reviews: 654 }
	];

	for (let i = 0; i < competitors.length; i++) {
		const c = competitors[i];
		sse(res, 'activity', {
			id: 'data-current',
			category: 'data',
			status: 'running',
			label: c.name,
			agent: 'context_enricher'
		});
		await wait(300 + Math.random() * 200);
		sse(res, 'activity', {
			id: 'data-check',
			category: 'data',
			status: 'running',
			label: `Checking nearby places: ${i + 1}/6`,
			agent: 'context_enricher'
		});
		sse(res, 'activity', {
			id: 'data-current',
			category: 'data',
			status: 'running',
			label: `${c.name}, ${c.reviews.toLocaleString()} reviews`,
			agent: 'context_enricher'
		});
		await wait(80);
	}

	sse(res, 'activity', {
		id: 'data-check',
		category: 'data',
		status: 'complete',
		label: 'Checking nearby places: 6/6',
		agent: 'context_enricher'
	});
	sse(res, 'activity', { category: 'data', status: 'all-complete' });

	sse(res, 'progress', {
		stage: 'context',
		status: 'complete',
		label: "Joe's Pizza — 4.7\u2605 \u00b7 3,456 reviews"
	});
	sse(res, 'activity', { category: 'data', status: 'all-complete' });

	await wait(400);
	sse(res, 'progress', { stage: 'planning', status: 'complete', label: 'Research planned' });

	await wait(200);
	const specs = ['market_landscape', 'menu_pricing', 'guest_intelligence'];
	const labels = {
		market_landscape: 'Market Landscape',
		menu_pricing: 'Menu & Pricing',
		guest_intelligence: 'Guest Intelligence'
	};
	for (const s of specs) {
		sse(res, 'activity', {
			id: `analyze-${s}`,
			category: 'analyze',
			status: 'pending',
			label: labels[s],
			agent: s
		});
	}

	// Searches
	sse(res, 'activity', {
		id: 'search-0',
		category: 'search',
		status: 'running',
		label: 'NYC pizza market analysis 2026',
		agent: 'market_landscape'
	});
	sse(res, 'activity', {
		id: 'search-1',
		category: 'search',
		status: 'running',
		label: "joe's pizza menu prices competitors",
		agent: 'menu_pricing'
	});
	sse(res, 'activity', {
		id: 'search-2',
		category: 'search',
		status: 'running',
		label: "joe's pizza customer reviews analysis",
		agent: 'guest_intelligence'
	});

	// Fast completions
	await wait(800);
	sse(res, 'activity', {
		id: 'search-0',
		category: 'search',
		status: 'complete',
		agent: 'market_landscape'
	});
	sse(res, 'activity', {
		id: `analyze-market_landscape`,
		category: 'analyze',
		status: 'running',
		label: 'Market Landscape',
		detail: 'NYC pizza segment remains dominated by independent operators with 73% market share.',
		agent: 'market_landscape'
	});
	await wait(500);
	sse(res, 'activity', {
		id: `analyze-market_landscape`,
		category: 'analyze',
		status: 'complete',
		label: 'Market Landscape',
		detail:
			"NYC pizza dominated by independents (73%). Joe's competes in the premium slice segment.",
		agent: 'market_landscape'
	});
	sse(res, 'activity', {
		id: 'read-eater',
		category: 'read',
		status: 'complete',
		label: 'eater.com',
		detail: 'Best Pizza in NYC 2026',
		url: 'https://eater.com/nyc-best-pizza',
		agent: 'market_landscape'
	});

	await wait(400);
	sse(res, 'activity', {
		id: 'search-1',
		category: 'search',
		status: 'complete',
		agent: 'menu_pricing'
	});
	sse(res, 'activity', {
		id: `analyze-menu_pricing`,
		category: 'analyze',
		status: 'complete',
		label: 'Menu & Pricing',
		detail: 'Slice price of $3.75 is competitive. Average ticket $8.50.',
		agent: 'menu_pricing'
	});

	// Slow specialist — guest_intelligence takes a long time
	await wait(3000);
	sse(res, 'activity', {
		id: 'search-2',
		category: 'search',
		status: 'complete',
		agent: 'guest_intelligence'
	});
	sse(res, 'activity', {
		id: `analyze-guest_intelligence`,
		category: 'analyze',
		status: 'running',
		label: 'Guest Intelligence',
		detail: 'Analyzing 3,456 reviews across Google and Yelp platforms.',
		agent: 'guest_intelligence'
	});
	await wait(800);
	sse(res, 'activity', {
		id: `analyze-guest_intelligence`,
		category: 'analyze',
		status: 'complete',
		label: 'Guest Intelligence',
		detail: '4.7 stars with 92% positive sentiment. Speed and crust quality are top mentions.',
		agent: 'guest_intelligence'
	});
	sse(res, 'activity', {
		id: 'read-yelp',
		category: 'read',
		status: 'complete',
		label: 'yelp.com',
		detail: "Joe's Pizza Reviews",
		url: 'https://yelp.com/biz/joes-pizza-new-york',
		agent: 'guest_intelligence'
	});

	// Synthesis
	await wait(400);
	sse(res, 'activity', {
		id: 'analyze-synthesizer',
		category: 'analyze',
		status: 'running',
		label: 'Synthesizing findings',
		agent: 'synthesizer'
	});

	const reply =
		"## Joe's Pizza Analysis\n\nJoe's Pizza maintains a dominant position in the NYC slice market with a 4.7-star rating across 3,456 reviews. The $3.75 slice price is competitive, and customer sentiment is overwhelmingly positive (92%) with speed and crust quality as key differentiators.";
	const words = reply.split(' ');
	for (let i = 0; i < words.length; i += 3) {
		sse(res, 'token', { text: words.slice(i, i + 3).join(' ') + ' ' });
		await wait(35);
	}

	sse(res, 'activity', {
		id: 'analyze-synthesizer',
		category: 'analyze',
		status: 'complete',
		label: 'Research complete',
		agent: 'synthesizer'
	});
	sse(res, 'complete', {
		reply,
		sources: [
			{
				title: 'Best Pizza in NYC 2026',
				url: 'https://eater.com/nyc-best-pizza',
				domain: 'eater.com'
			},
			{
				title: "Joe's Pizza Reviews",
				url: 'https://yelp.com/biz/joes-pizza-new-york',
				domain: 'yelp.com'
			}
		],
		title: "Joe's Pizza Market Analysis"
	});
	res.end();
}

// --- Server ---

const SCENARIOS = {
	full: fullResearch,
	'full-research': fullResearch,
	quick: quickRouter,
	slow: slowSpecialist
};

const scenarioName = process.argv[2] || 'full';
const scenarioFn = SCENARIOS[scenarioName];
if (!scenarioFn) {
	console.error(
		`Unknown scenario: "${scenarioName}". Available: ${Object.keys(SCENARIOS).join(', ')}`
	);
	process.exit(1);
}

const server = http.createServer(async (req, res) => {
	// CORS + SSE headers
	res.writeHead(200, {
		'Content-Type': 'text/event-stream',
		'Cache-Control': 'no-cache',
		Connection: 'keep-alive',
		'Access-Control-Allow-Origin': '*',
		'Access-Control-Allow-Methods': 'POST, OPTIONS',
		'Access-Control-Allow-Headers': 'Content-Type'
	});

	if (req.method === 'OPTIONS') {
		res.end();
		return;
	}

	// Drain request body (we don't use it)
	req.resume();

	res.write(': ok\n\n');

	const t0 = Date.now();
	console.log(`[mock] Starting "${scenarioName}" scenario`);

	try {
		await scenarioFn(res);
	} catch (err) {
		if (err.code === 'ERR_STREAM_WRITE_AFTER_END') {
			console.log(`[mock] Client disconnected early`);
		} else {
			console.error(`[mock] Error:`, err);
		}
	}

	const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
	console.log(`[mock] Completed in ${elapsed}s`);
});

server.listen(PORT, () => {
	console.log(`\n  Mock stream server running on http://localhost:${PORT}`);
	console.log(`  Scenario: ${scenarioName}`);
	console.log(`\n  To use: update vite.config.ts proxy target to http://localhost:${PORT}\n`);
});
