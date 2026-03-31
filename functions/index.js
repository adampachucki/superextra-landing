import { onRequest } from 'firebase-functions/v2/https';
import { defineSecret } from 'firebase-functions/params';
import { VertexAI } from '@google-cloud/vertexai';
import { GoogleAuth } from 'google-auth-library';
import { initializeApp } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';

initializeApp();
const db = getFirestore();

const relayKey = defineSecret('RELAY_KEY');
const elevenlabsKey = defineSecret('ELEVENLABS_API_KEY');
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

// --- Agent chat endpoint (proxies to ADK Cloud Run) ---

const ADK_SERVICE_URL = 'https://superextra-agent-907466498524.us-central1.run.app';
const auth = new GoogleAuth();

const rateLimitMap = new Map();

// Maps frontend sessionId → ADK session ID (resets on cold start)
const sessionMap = new Map();

export const agent = onRequest({ cors: true, timeoutSeconds: 300 }, async (req, res) => {
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

	try {
		// Get IAM identity token for Cloud Run
		const client = await auth.getIdTokenClient(ADK_SERVICE_URL);
		const headers = await client.getRequestHeaders();

		// Get or create ADK session (check cache → Firestore → create new)
		let adkSessionId = sessionMap.get(sessionId);
		if (!adkSessionId) {
			const doc = await db.collection('sessions').doc(sessionId).get();
			if (doc.exists) {
				adkSessionId = doc.data().adkSessionId;
				sessionMap.set(sessionId, adkSessionId);
			}
		}
		if (!adkSessionId) {
			const createRes = await fetch(`${ADK_SERVICE_URL}/apps/superextra_agent/users/${encodeURIComponent(ip)}/sessions`, {
				method: 'POST',
				headers: { ...headers, 'Content-Type': 'application/json' },
				body: JSON.stringify({})
			});
			if (!createRes.ok) {
				console.error('Session creation failed:', createRes.status);
				res.status(502).json({ ok: false, error: 'Agent unavailable. Please try again.' });
				return;
			}
			const sessionData = await createRes.json();
			adkSessionId = sessionData.id;
			sessionMap.set(sessionId, adkSessionId);
			await db.collection('sessions').doc(sessionId).set({
				adkSessionId,
				userId: ip,
				createdAt: Date.now()
			});
		}

		// Build the query text with date and optional place context
		const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
		let queryText = `[Date: ${today}] ${message}`;
		if (placeContext && placeContext.name) {
			const isFirstMessage = !history || history.length === 0;
			if (isFirstMessage) {
				queryText = `[Context: asking about ${placeContext.name}, ${placeContext.secondary || ''} (Place ID: ${placeContext.placeId || 'unknown'})] ${queryText}`;
			}
		}

		// Call ADK Cloud Run service
		const adkResponse = await fetch(`${ADK_SERVICE_URL}/run_sse`, {
			method: 'POST',
			headers: { ...headers, 'Content-Type': 'application/json' },
			body: JSON.stringify({
				app_name: 'superextra_agent',
				user_id: ip,
				session_id: adkSessionId,
				new_message: { role: 'user', parts: [{ text: queryText }] },
				streaming: false
			})
		});

		if (!adkResponse.ok) {
			const errText = await adkResponse.text().catch(() => '');
			console.error('ADK error:', adkResponse.status, errText);
			res.status(502).json({ ok: false, error: 'Agent unavailable. Please try again.' });
			return;
		}

		// Parse SSE events to extract the response
		// Priority: final_report (full pipeline) > router_response (clarifying question)
		const sseText = await adkResponse.text();
		let reply = '';
		const sources = [];

		for (const line of sseText.split('\n')) {
			if (!line.startsWith('data: ')) continue;
			try {
				const event = JSON.parse(line.slice(6));
				const stateDelta = event.actions?.stateDelta;
				if (stateDelta?.final_report) {
					reply = stateDelta.final_report;
				} else if (stateDelta?.router_response && !reply) {
					reply = stateDelta.router_response;
				}
				// Collect grounding sources from specialist events
				const chunks = event.groundingMetadata?.groundingChunks;
				if (chunks) {
					for (const c of chunks) {
						if (c.web && !sources.some(s => s.url === c.web.uri)) {
							sources.push({ title: c.web.title, url: c.web.uri });
						}
					}
				}
			} catch {
				// skip malformed events
			}
		}

		if (!reply) {
			reply = 'I wasn\'t able to generate a response. Please try rephrasing your question.';
		}

		// Generate a short title for new conversations
		let title = undefined;
		const isFirstMessage = !history || history.length === 0;
		if (isFirstMessage) {
			try {
				const vertexAI = new VertexAI({ project: PROJECT, location: LOCATION });
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

// --- STT token endpoint (mints single-use ElevenLabs Scribe tokens) ---

const sttRateLimitMap = new Map();

export const sttToken = onRequest({ cors: true, secrets: [elevenlabsKey] }, async (req, res) => {
	if (req.method !== 'POST') {
		res.status(405).json({ ok: false, error: 'Method not allowed' });
		return;
	}

	const ip = req.ip || req.headers['x-forwarded-for'] || 'unknown';
	const now = Date.now();
	const window = 10 * 60 * 1000;
	const entry = sttRateLimitMap.get(ip);
	if (entry && now - entry.start < window) {
		if (entry.count >= 10) {
			res.status(429).json({ ok: false, error: 'Too many requests. Please wait a few minutes.' });
			return;
		}
		entry.count++;
	} else {
		sttRateLimitMap.set(ip, { start: now, count: 1 });
	}

	try {
		const response = await fetch('https://api.elevenlabs.io/v1/single-use-token/realtime_scribe', {
			method: 'POST',
			headers: { 'xi-api-key': elevenlabsKey.value() }
		});

		if (!response.ok) {
			const body = await response.text().catch(() => '');
			console.error('ElevenLabs token error:', response.status, body);
			res.status(502).json({ ok: false, error: 'Speech service unavailable' });
			return;
		}

		const data = await response.json();
		res.json({ ok: true, token: data.token });
	} catch (err) {
		console.error('ElevenLabs token fetch failed:', err);
		res.status(500).json({ ok: false, error: 'Speech service unreachable' });
	}
});

// --- TTS endpoint (converts agent text to speech via ElevenLabs) ---

const TTS_VOICE_ID = 'SAz9YHcvj6GT2YYXdXww'; // River – Relaxed, Neutral, Informative
const ttsRateLimitMap = new Map();

function stripMarkdown(text) {
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

export const tts = onRequest({ cors: true, secrets: [elevenlabsKey] }, async (req, res) => {
	if (req.method !== 'POST') {
		res.status(405).json({ ok: false, error: 'Method not allowed' });
		return;
	}

	const ip = req.ip || req.headers['x-forwarded-for'] || 'unknown';
	const now = Date.now();
	const window = 10 * 60 * 1000;
	const entry = ttsRateLimitMap.get(ip);
	if (entry && now - entry.start < window) {
		if (entry.count >= 20) {
			res.status(429).json({ ok: false, error: 'Too many requests. Please wait a few minutes.' });
			return;
		}
		entry.count++;
	} else {
		ttsRateLimitMap.set(ip, { start: now, count: 1 });
	}

	const { text } = req.body || {};
	if (!text || typeof text !== 'string') {
		res.status(400).json({ ok: false, error: 'text is required' });
		return;
	}

	const plainText = stripMarkdown(text);
	if (plainText.length > 5000) {
		res.status(400).json({ ok: false, error: 'Text too long for speech synthesis' });
		return;
	}

	try {
		const response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${TTS_VOICE_ID}`, {
			method: 'POST',
			headers: {
				'xi-api-key': elevenlabsKey.value(),
				'Content-Type': 'application/json',
				'Accept': 'audio/mpeg'
			},
			body: JSON.stringify({
				text: plainText,
				model_id: 'eleven_multilingual_v2',
				voice_settings: {
					stability: 0.5,
					similarity_boost: 0.75
				}
			})
		});

		if (!response.ok) {
			const body = await response.text().catch(() => '');
			console.error('ElevenLabs TTS error:', response.status, body);
			res.status(502).json({ ok: false, error: 'Speech synthesis failed' });
			return;
		}

		const arrayBuffer = await response.arrayBuffer();
		res.set('Content-Type', 'audio/mpeg');
		res.send(Buffer.from(arrayBuffer));
	} catch (err) {
		console.error('ElevenLabs TTS fetch failed:', err);
		res.status(500).json({ ok: false, error: 'Speech service unreachable' });
	}
});

// --- Agent debug endpoint (retrieves full ADK session by frontend sessionId) ---

export const agentDebug = onRequest({ cors: true, timeoutSeconds: 30 }, async (req, res) => {
	if (req.method !== 'GET') {
		res.status(405).json({ ok: false, error: 'Method not allowed' });
		return;
	}

	const sid = req.query.sid;
	if (!sid) {
		res.status(400).json({ ok: false, error: 'sid query parameter is required' });
		return;
	}

	try {
		const doc = await db.collection('sessions').doc(sid).get();
		if (!doc.exists) {
			res.status(404).json({ ok: false, error: 'Session not found' });
			return;
		}

		const { adkSessionId, userId } = doc.data();
		const client = await auth.getIdTokenClient(ADK_SERVICE_URL);
		const headers = await client.getRequestHeaders();

		const adkRes = await fetch(
			`${ADK_SERVICE_URL}/apps/superextra_agent/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(adkSessionId)}`,
			{ headers }
		);

		if (!adkRes.ok) {
			const errText = await adkRes.text().catch(() => '');
			console.error('ADK session fetch failed:', adkRes.status, errText);
			res.status(502).json({ ok: false, error: 'Could not retrieve session from agent' });
			return;
		}

		const session = await adkRes.json();
		res.json({ ok: true, session });
	} catch (err) {
		console.error('Debug endpoint error:', err.message || err);
		res.status(500).json({ ok: false, error: 'Failed to retrieve session' });
	}
});
