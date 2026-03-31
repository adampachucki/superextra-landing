import { onRequest } from 'firebase-functions/v2/https';
import { defineSecret } from 'firebase-functions/params';
import { VertexAI } from '@google-cloud/vertexai';

const relayKey = defineSecret('RELAY_KEY');
const DEST = 'hello@superextra.ai';

// --- Vertex AI config ---
const PROJECT = 'superextra-site';
const LOCATION = 'us-central1';

export const intake = onRequest({ cors: true, secrets: [relayKey] }, async (req, res) => {
	const RELAY_KEY = relayKey.value();
	if (req.method !== 'POST') {
		res.status(405).json({ ok: false, error: 'Method not allowed' });
		return;
	}

	const data = req.body;

	const html = `
		<div style="font-family:sans-serif;max-width:520px">
			<h2 style="margin:0 0 16px">New access request</h2>
			<table style="border-collapse:collapse;width:100%">
				${row('Category', data.type)}
				${row('Country', data.country)}
				${row('Name', data.businessName)}
				${data.placeId ? row('Google Maps', `<a href="https://www.google.com/maps/place/?q=place_id:${esc(data.placeId)}">View on Maps</a>`, true) : ''}
				${data.locations ? row('Locations', data.locations) : ''}
				${data.webUrl ? row('URL', data.webUrl) : ''}
				${row('Contact', data.fullName)}
				${row('Email', data.email)}
				${data.phone ? row('Phone', data.phone) : ''}
			</table>
		</div>
	`;

	if (!RELAY_KEY) {
		console.error('RELAY_KEY env var is not set');
		res.status(500).json({ ok: false, error: 'Email service not configured' });
		return;
	}

	let result;
	try {
		result = await fetch('https://api.resend.com/emails', {
			method: 'POST',
			headers: {
				Authorization: `Bearer ${RELAY_KEY}`,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				from: 'Superextra <notify@superextra.ai>',
				to: DEST,
				subject: `Access request – ${data.businessName || data.type}`,
				html
			})
		});
	} catch (err) {
		console.error('Resend fetch failed:', err);
		res.status(500).json({ ok: false, error: 'Email service unreachable' });
		return;
	}

	if (!result.ok) {
		const body = await result.text().catch(() => '');
		console.error('Resend error:', result.status, body);
		const error = result.status === 401 ? 'Email API key invalid' : `Email service error (${result.status})`;
		res.status(502).json({ ok: false, error });
		return;
	}

	// Confirmation email to the submitter
	try {
		await fetch('https://api.resend.com/emails', {
			method: 'POST',
			headers: {
				Authorization: `Bearer ${RELAY_KEY}`,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				from: 'Adam Pachucki <ap@superextra.ai>',
				to: data.email,
				subject: "You've signed up for Superextra",
				html: confirmationHtml(data.fullName)
			})
		});
	} catch (err) {
		console.error('Confirmation email failed:', err);
	}

	res.json({ ok: true });
});

function row(label, value, raw = false) {
	return `<tr>
		<td style="padding:6px 12px 6px 0;color:#888;font-size:13px;white-space:nowrap">${esc(label)}</td>
		<td style="padding:6px 0;font-size:13px">${raw ? value : esc(value)}</td>
	</tr>`;
}

function esc(s) {
	return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function confirmationHtml(name) {
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

// --- Agent chat endpoint ---

const SYSTEM_INSTRUCTION = `You are a restaurant market analyst working for Superextra, an AI-native market intelligence service for the restaurant industry. Your job is to answer questions about the competitive landscape, pricing, guest sentiment, foot traffic, operations, and market trends relevant to a specific restaurant or area.

Every conversation should be grounded in a specific restaurant or area. User messages may include a [Context: ...] prefix containing the restaurant name, location, and Google Place ID. Use this to focus your research on the relevant neighborhood, city, and competitive set.

If no context is provided and the user has not mentioned a specific restaurant or area, your first response must ask them to specify one. Do not research or answer market questions without knowing the location.

You cover seven layers of restaurant market intelligence:
1. Market landscape — openings/closings, competitor activity, cuisine trends, saturation, white space
2. Menu and pricing — competitor menus, price positioning, delivery markups, trending dishes
3. Revenue and sales — revenue estimates, check size, occupancy, channel splits, platform share
4. Marketing and digital — social media activity, ad spend, web presence, digital ordering
5. Guest intelligence — review sentiment, guest expectations, complaints/praise, tourist vs local
6. Location and traffic — foot traffic, demographics, purchasing power, rent, trade areas
7. Operations — labor availability, salary benchmarks, staffing trends, supplier pricing

Research thoroughly using web search before responding. Always cite sources. Structure answers with headings, lists, or tables. Lead with the most actionable insight. Be specific to the location. Acknowledge gaps honestly — never fabricate data. Keep responses concise but complete.

Tone: knowledgeable, data-driven, direct, professional but approachable. You do not have access to internal data (POS, financials). Do not provide legal, tax, or medical advice.

Always respond in the language of the user's question — not the language of the place name, address, or data sources. If the user writes their question in English, respond in English even if the restaurant is in Poland. If the user writes in Polish, respond in Polish even if the restaurant is in Germany. Only the language of the user's actual question determines your response language.`;

const rateLimitMap = new Map();

// Conversation history per session (in-memory, resets on cold start)
const sessionHistory = new Map();

export const agent = onRequest({ cors: true, timeoutSeconds: 120 }, async (req, res) => {
	if (req.method !== 'POST') {
		res.status(405).json({ ok: false, error: 'Method not allowed' });
		return;
	}

	// Basic rate limiting (20 requests per 10 min per IP)
	const ip = req.ip || req.headers['x-forwarded-for'] || 'unknown';
	const now = Date.now();
	const window = 10 * 60 * 1000;
	const entry = rateLimitMap.get(ip);
	if (entry && now - entry.start < window) {
		if (entry.count >= 20) {
			res.status(429).json({ ok: false, error: 'Too many requests. Please wait a few minutes.' });
			return;
		}
		entry.count++;
	} else {
		rateLimitMap.set(ip, { start: now, count: 1 });
	}

	const { message, sessionId, placeContext, history } = req.body || {};

	if (!message || typeof message !== 'string' || !sessionId) {
		res.status(400).json({ ok: false, error: 'message and sessionId are required' });
		return;
	}

	if (message.length > 2000) {
		res.status(400).json({ ok: false, error: 'Message too long' });
		return;
	}

	// Build the query text with optional place context (only on first message)
	let queryText = message;
	if (placeContext && placeContext.name) {
		const hasHistory = (history && history.length > 0) || sessionHistory.has(sessionId);
		if (!hasHistory) {
			queryText = `[Context: asking about ${placeContext.name}, ${placeContext.secondary || ''} (Place ID: ${placeContext.placeId || 'unknown'})] ${message}`;
		}
	}

	// Build conversation history for multi-turn
	const prevHistory = history || sessionHistory.get(sessionId) || [];
	const contents = [
		...prevHistory,
		{ role: 'user', parts: [{ text: queryText }] }
	];

	try {
		const vertexAI = new VertexAI({ project: PROJECT, location: LOCATION });
		const model = vertexAI.getGenerativeModel({
			model: 'gemini-2.5-pro',
			systemInstruction: { parts: [{ text: SYSTEM_INSTRUCTION }] },
			tools: [{ googleSearch: {} }]
		});

		const result = await model.generateContent({ contents });
		const response = result.response;

		// Extract text from response
		const reply = response.candidates?.[0]?.content?.parts
			?.filter(p => p.text)
			?.map(p => p.text)
			?.join('\n\n')
			|| 'I wasn\'t able to generate a response. Please try rephrasing your question.';

		// Store conversation history for this session
		const updatedHistory = [
			...contents,
			{ role: 'model', parts: [{ text: reply }] }
		];
		sessionHistory.set(sessionId, updatedHistory);

		// Extract grounding sources if available
		const grounding = response.candidates?.[0]?.groundingMetadata;
		const sources = grounding?.groundingChunks
			?.filter(c => c.web)
			?.map(c => ({ title: c.web.title, url: c.web.uri }))
			|| [];

		// Generate a short title for new conversations (no prior history)
		let title = undefined;
		const isFirstMessage = !prevHistory.length;
		if (isFirstMessage) {
			try {
				const flashModel = vertexAI.getGenerativeModel({ model: 'gemini-2.5-flash' });
				const titleResult = await flashModel.generateContent({
					contents: [{ role: 'user', parts: [{ text: `Generate a short conversational title (max 5 words, no quotes) for a chat that starts with this question about restaurants: "${message}"` }] }]
				});
				const raw = titleResult.response.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
				if (raw) title = raw.replace(/^["']|["']$/g, '').slice(0, 60);
			} catch (e) {
				console.error('Title generation failed:', e.message);
			}
		}

		res.json({ ok: true, reply, sources, ...(title && { title }) });
	} catch (err) {
		console.error('Agent error:', err.message || err);
		res.status(500).json({ ok: false, error: 'Agent unavailable. Please try again.' });
	}
});
