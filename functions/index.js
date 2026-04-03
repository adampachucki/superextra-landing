import { onRequest } from 'firebase-functions/v2/https';
import { defineSecret } from 'firebase-functions/params';
import { VertexAI } from '@google-cloud/vertexai';
import { GoogleAuth } from 'google-auth-library';
import { initializeApp } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';
import {
	esc, row, confirmationHtml, stripMarkdown, extractSourcesFromText,
	sendSSE, checkRateLimit, parseADKStream,
	SPECIALIST_RESULT_KEYS, SPECIALIST_KEYS, TOOL_LABELS,
} from './utils.js';

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

// row, esc, confirmationHtml imported from ./utils.js

// --- Agent chat endpoint (proxies to ADK Cloud Run) ---

const ADK_SERVICE_URL = 'https://superextra-agent-907466498524.us-central1.run.app';
const auth = new GoogleAuth();

// SPECIALIST_RESULT_KEYS, extractSourcesFromText imported from ./utils.js

const rateLimitMap = new Map();

// Maps frontend sessionId → ADK session ID (resets on cold start)
const sessionMap = new Map();

async function persistSession(sessionId, adkSessionId, userId) {
	try {
		await db.collection('sessions').doc(sessionId).set({
			adkSessionId, userId, createdAt: Date.now()
		});
	} catch (e) {
		console.warn('Firestore session write failed, retrying:', e.message);
		try {
			await db.collection('sessions').doc(sessionId).set({
				adkSessionId, userId, createdAt: Date.now()
			});
		} catch (e2) {
			console.error('Firestore session write failed permanently:', e2.message);
		}
	}
}

export const agent = onRequest({ cors: true, timeoutSeconds: 300 }, async (req, res) => {
	if (req.method !== 'POST') {
		res.status(405).json({ ok: false, error: 'Method not allowed' });
		return;
	}

	const ip = req.ip || req.headers['x-forwarded-for'] || 'unknown';
	if (!checkRateLimit(rateLimitMap, ip, Date.now(), 10 * 60 * 1000, 20)) {
		res.status(429).json({ ok: false, error: 'Too many requests. Please wait a few minutes.' });
		return;
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
		// userId must match the one used when the session was created — use stored value for existing sessions
		// (IP can change on mobile networks, wifi switches, etc.)
		let cached = sessionMap.get(sessionId);
		let adkSessionId = cached?.adkSessionId;
		let userId = cached?.userId || ip;
		if (!adkSessionId) {
			const doc = await db.collection('sessions').doc(sessionId).get();
			if (doc.exists) {
				adkSessionId = doc.data().adkSessionId;
				userId = doc.data().userId || ip;
				sessionMap.set(sessionId, { adkSessionId, userId });
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
			userId = ip;
			sessionMap.set(sessionId, { adkSessionId, userId });
			await persistSession(sessionId, adkSessionId, ip);
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
				user_id: userId,
				session_id: adkSessionId,
				new_message: { role: 'user', parts: [{ text: queryText }] },
				streaming: true
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
				const stateDelta = event.actions?.stateDelta || event.actions?.state_delta;
				if (stateDelta?.final_report) {
					reply = stateDelta.final_report;
				} else if (stateDelta?.router_response && !reply) {
					reply = stateDelta.router_response;
				}
				// Extract sources from specialist result text (markdown links)
				for (const key of SPECIALIST_RESULT_KEYS) {
					if (stateDelta?.[key]) {
						for (const s of extractSourcesFromText(stateDelta[key])) {
							if (!sources.some(x => x.url === s.url)) {
								sources.push(s);
							}
						}
					}
				}
			} catch (e) {
				console.warn('[agent] Malformed SSE event, skipping:', line.slice(0, 200), e.message);
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
					contents: [{ role: 'user', parts: [{ text:
						`Summarize this message into a short title, max 4 words.\n` +
						`Rules:\n` +
						`- Use the SAME LANGUAGE as the message\n` +
						`- No markdown, no quotes, no punctuation, no numbering\n` +
						`- Do not answer the question — just label the topic\n` +
						`- Reply with ONLY the title, nothing else\n\n` +
						`Message: "${message}"`
					}] }]
				});
				const raw = titleResult.response.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
				if (raw) {
					const cleaned = raw
						.replace(/^["']|["']$/g, '')
						.replace(/[*#_`~>\-]/g, '')
						.replace(/^\d+\.\s*/, '')
						.trim();
					const words = cleaned.split(/\s+/);
					if (words.length <= 8 && cleaned.length > 0) {
						title = words.slice(0, 4).join(' ');
					}
				}
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

// --- Streaming agent endpoint (SSE progress + token streaming) ---

// TOOL_LABELS, SPECIALIST_KEYS, sendSSE imported from ./utils.js

async function generateTitle(message) {
	try {
		const vertexAI = new VertexAI({ project: PROJECT, location: LOCATION });
		const flashModel = vertexAI.getGenerativeModel({ model: 'gemini-2.5-flash' });
		const titleResult = await Promise.race([
			flashModel.generateContent({
				contents: [{ role: 'user', parts: [{ text:
					`Summarize this message into a short title, max 4 words.\n` +
					`Rules:\n` +
					`- Use the SAME LANGUAGE as the message\n` +
					`- No markdown, no quotes, no punctuation, no numbering\n` +
					`- Do not answer the question — just label the topic\n` +
					`- Reply with ONLY the title, nothing else\n\n` +
					`Message: "${message}"`
				}] }]
			}),
			new Promise((_, reject) => setTimeout(() => reject(new Error('Title generation timed out')), 8000))
		]);
		const raw = titleResult.response.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
		if (raw) {
			const cleaned = raw
				.replace(/^["']|["']$/g, '')
				.replace(/[*#_`~>\-]/g, '')
				.replace(/^\d+\.\s*/, '')
				.trim();
			const words = cleaned.split(/\s+/);
			if (words.length <= 8 && cleaned.length > 0) {
				return words.slice(0, 4).join(' ');
			}
		}
	} catch (e) {
		console.warn('Title generation failed:', e.message);
	}
	return undefined;
}

export const agentStream = onRequest({ cors: true, timeoutSeconds: 300 }, async (req, res) => {
	if (req.method !== 'POST') {
		res.status(405).json({ ok: false, error: 'Method not allowed' });
		return;
	}

	const ip = req.ip || req.headers['x-forwarded-for'] || 'unknown';
	if (!checkRateLimit(rateLimitMap, ip, Date.now(), 10 * 60 * 1000, 20)) {
		res.status(429).json({ ok: false, error: 'Too many requests. Please wait a few minutes.' });
		return;
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

	// SSE headers — write() immediately to flush headers to the client.
	// writeHead() alone does NOT flush in Node.js; without an early write(),
	// the client's fetch() stays pending and Cloud Run infrastructure may
	// close the idle connection before the first keepalive at t+15s.
	res.writeHead(200, {
		'Content-Type': 'text/event-stream',
		'Cache-Control': 'no-cache',
		'X-Accel-Buffering': 'no',
	});
	res.write(': ok\n\n');

	const t0 = Date.now();
	const keepalive = setInterval(() => res.write(': keepalive\n\n'), 15000);
	const ac = new AbortController();
	res.on('close', () => {
		const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
		if (!res.writableEnded) console.warn(`Client disconnected at +${elapsed}s (before stream completed)`);
		ac.abort();
		clearInterval(keepalive);
	});

	try {
		const client = await auth.getIdTokenClient(ADK_SERVICE_URL);
		const headers = await client.getRequestHeaders();
		console.log(`[stream +${((Date.now() - t0) / 1000).toFixed(1)}s] auth ready`);

		// Session management (same as agent endpoint)
		let cached = sessionMap.get(sessionId);
		let adkSessionId = cached?.adkSessionId;
		let userId = cached?.userId || ip;
		if (!adkSessionId) {
			const doc = await db.collection('sessions').doc(sessionId).get();
			if (doc.exists) {
				adkSessionId = doc.data().adkSessionId;
				userId = doc.data().userId || ip;
				sessionMap.set(sessionId, { adkSessionId, userId });
			}
		}
		console.log(`[stream +${((Date.now() - t0) / 1000).toFixed(1)}s] session lookup: ${adkSessionId ? 'found' : 'new'}`);

		if (!adkSessionId) {
			const createRes = await fetch(`${ADK_SERVICE_URL}/apps/superextra_agent/users/${encodeURIComponent(ip)}/sessions`, {
				method: 'POST',
				headers: { ...headers, 'Content-Type': 'application/json' },
				body: JSON.stringify({})
			});
			if (!createRes.ok) {
				sendSSE(res, 'error', { error: 'Agent unavailable. Please try again.' });
				res.end();
				clearInterval(keepalive);
				return;
			}
			const sessionData = await createRes.json();
			adkSessionId = sessionData.id;
			userId = ip;
			sessionMap.set(sessionId, { adkSessionId, userId });
			await persistSession(sessionId, adkSessionId, ip);
			console.log(`[stream +${((Date.now() - t0) / 1000).toFixed(1)}s] session created: ${adkSessionId}`);
		}

		// Build query
		const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
		let queryText = `[Date: ${today}] ${message}`;
		const isFirstMessage = !history || history.length === 0;
		if (placeContext && placeContext.name && isFirstMessage) {
			queryText = `[Context: asking about ${placeContext.name}, ${placeContext.secondary || ''} (Place ID: ${placeContext.placeId || 'unknown'})] ${queryText}`;
		}

		// Title generation in parallel (first message only)
		const titlePromise = isFirstMessage ? generateTitle(message) : null;

		// Call ADK with streaming — 240s timeout leaves 60s buffer for completion handling
		console.log(`[stream +${((Date.now() - t0) / 1000).toFixed(1)}s] calling run_sse (aborted=${ac.signal.aborted})`);
		const adkTimeout = AbortSignal.timeout(240_000);
		const adkResponse = await fetch(`${ADK_SERVICE_URL}/run_sse`, {
			method: 'POST',
			headers: { ...headers, 'Content-Type': 'application/json' },
			body: JSON.stringify({
				app_name: 'superextra_agent',
				user_id: userId,
				session_id: adkSessionId,
				new_message: { role: 'user', parts: [{ text: queryText }] },
				streaming: true
			}),
			signal: AbortSignal.any([ac.signal, adkTimeout])
		});

		if (!adkResponse.ok) {
			sendSSE(res, 'error', { error: 'Agent unavailable. Please try again.' });
			res.end();
			clearInterval(keepalive);
			return;
		}

		// Stream-parse ADK SSE events and emit frontend SSE events
		console.log(`[stream +${((Date.now() - t0) / 1000).toFixed(1)}s] run_sse connected`);
		const reader = adkResponse.body.getReader();
		const { reply, routerResponse, sources } = await parseADKStream(reader, (event, data) => sendSSE(res, event, data));

		// Fallback: fetch sources from session state specialist results
		if (sources.length === 0 && (reply || routerResponse)) {
			try {
				const sessionRes = await fetch(
					`${ADK_SERVICE_URL}/apps/superextra_agent/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(adkSessionId)}`,
					{ headers }
				);
				if (sessionRes.ok) {
					const session = await sessionRes.json();
					for (const key of SPECIALIST_RESULT_KEYS) {
						if (session.state?.[key]) {
							for (const s of extractSourcesFromText(session.state[key])) {
								if (!sources.some(x => x.url === s.url)) {
									sources.push(s);
								}
							}
						}
					}
				}
			} catch {
				// sources unavailable — not critical
			}
		}

		const title = titlePromise ? await titlePromise : undefined;
		const finalReply = reply || routerResponse || 'I wasn\'t able to generate a response. Please try rephrasing your question.';
		sendSSE(res, 'complete', {
			reply: finalReply,
			sources,
			...(title && { title }),
		});
	} catch (err) {
		if (err.name === 'AbortError') {
			console.warn('Agent stream aborted (client disconnect or timeout)');
		} else {
			console.error('Agent stream error:', err.message || err);
			sendSSE(res, 'error', { error: 'Agent unavailable. Please try again.' });
		}
	} finally {
		clearInterval(keepalive);
		res.end();
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
	if (!checkRateLimit(sttRateLimitMap, ip, Date.now(), 10 * 60 * 1000, 10)) {
		res.status(429).json({ ok: false, error: 'Too many requests. Please wait a few minutes.' });
		return;
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

// stripMarkdown imported from ./utils.js

export const tts = onRequest({ cors: true, secrets: [elevenlabsKey] }, async (req, res) => {
	if (req.method !== 'POST') {
		res.status(405).json({ ok: false, error: 'Method not allowed' });
		return;
	}

	const ip = req.ip || req.headers['x-forwarded-for'] || 'unknown';
	if (!checkRateLimit(ttsRateLimitMap, ip, Date.now(), 10 * 60 * 1000, 20)) {
		res.status(429).json({ ok: false, error: 'Too many requests. Please wait a few minutes.' });
		return;
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
				model_id: 'eleven_flash_v2_5',
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

// --- Agent check endpoint (recovers latest agent response if frontend missed it) ---

export const agentCheck = onRequest({ cors: true, timeoutSeconds: 30 }, async (req, res) => {
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
			res.json({ ok: false, reason: 'session_not_found' });
			return;
		}

		const { adkSessionId, userId, createdAt } = doc.data();
		const client = await auth.getIdTokenClient(ADK_SERVICE_URL);
		const headers = await client.getRequestHeaders();

		const adkRes = await fetch(
			`${ADK_SERVICE_URL}/apps/superextra_agent/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(adkSessionId)}`,
			{ headers }
		);

		if (!adkRes.ok) {
			res.json({ ok: false, reason: 'agent_unavailable' });
			return;
		}

		const session = await adkRes.json();
		const reply = session.state?.final_report || session.state?.router_response || null;

		if (!reply) {
			// Detect stuck sessions: if no reply after 5 minutes, the pipeline is dead
			// createdAt may be a Firestore Timestamp (.toMillis()) or a plain epoch ms number
			const createdMs = typeof createdAt === 'number' ? createdAt : createdAt?.toMillis?.() ?? Date.now();
			const ageMs = Date.now() - createdMs;
			if (ageMs > 5 * 60 * 1000) {
				res.json({ ok: false, reason: 'timed_out' });
				return;
			}
			res.json({ ok: true, reply: null, status: 'processing' });
			return;
		}

		// Extract sources from specialist result text (markdown links)
		const sources = [];
		for (const key of SPECIALIST_RESULT_KEYS) {
			if (session.state?.[key]) {
				for (const s of extractSourcesFromText(session.state[key])) {
					if (!sources.some(x => x.url === s.url)) {
						sources.push(s);
					}
				}
			}
		}

		res.json({ ok: true, reply, sources: sources.length ? sources : undefined, status: 'complete' });
	} catch (err) {
		console.error('Agent check error:', err.message || err);
		res.json({ ok: false, reason: 'agent_unavailable' });
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
