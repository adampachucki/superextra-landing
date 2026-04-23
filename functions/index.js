import crypto from 'node:crypto';
import { onRequest } from 'firebase-functions/v2/https';
import { defineSecret } from 'firebase-functions/params';
import { CloudTasksClient } from '@google-cloud/tasks';
import { initializeApp } from 'firebase-admin/app';
import { getAuth } from 'firebase-admin/auth';
import { getFirestore, FieldValue } from 'firebase-admin/firestore';
import {
	esc,
	row,
	confirmationHtml,
	stripMarkdown,
	checkRateLimit,
	validatePlaceContext
} from './utils.js';
export { watchdog } from './watchdog.js';

initializeApp();
const db = getFirestore();

const relayKey = defineSecret('RELAY_KEY');
const elevenlabsKey = defineSecret('ELEVENLABS_API_KEY');
const DEST = 'hello@superextra.ai';

const PROJECT = 'superextra-site';

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
		res.status(503).json({ ok: false, error: 'Email service unreachable' });
		return;
	}

	if (!result.ok) {
		const body = await result.text().catch(() => '');
		console.error('Resend error:', result.status, body);
		const error =
			result.status === 401 ? 'Email API key invalid' : `Email service error (${result.status})`;
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

// --- Agent chat endpoint (enqueues work to Cloud Tasks → superextra-worker) ---

const rateLimitMap = new Map();
const uidRateLimitMap = new Map();
const UID_RATE_LIMIT_WINDOW_MS = 60 * 60 * 1000; // 1 hour
const UID_RATE_LIMIT_MAX = 20; // per-UID pipeline runs per hour (plan default)

// Plan §5 / §6 — shared 10-turn cap per chat, counted across all contributors.
const MAX_TURNS_PER_SESSION = 10;

// Cloud Tasks config. WORKER_URL is canonically set at deploy time: the
// workflow describes the deployed `superextra-worker` Cloud Run service and
// writes the URL into `functions/.env.superextra-site`, which
// firebase-functions v2 loads into `process.env`. The fallback default uses
// this project's observed Cloud Run URL pattern
// (`<service>-<project-hash>-<region-short>.a.run.app`) as defense-in-depth
// against a deploy that forgot to set the env var. The older project-number
// URL pattern is NOT used by this project's Cloud Run services.
const TASKS_LOCATION = 'us-central1';
const TASKS_QUEUE = 'agent-dispatch';
const WORKER_SA = 'superextra-worker@superextra-site.iam.gserviceaccount.com';
const DISPATCH_DEADLINE_S = 1800; // plan-mandated — overrides 10-min default
const DEFAULT_WORKER_URL = 'https://superextra-worker-22b3fxahka-uc.a.run.app';
const WORKER_URL = () => process.env.WORKER_URL || DEFAULT_WORKER_URL;

let _tasksClient;
function getTasksClient() {
	if (!_tasksClient) _tasksClient = new CloudTasksClient();
	return _tasksClient;
}

async function enqueueRunTask({ runId, body }) {
	const workerUrl = WORKER_URL();
	const client = getTasksClient();
	const parent = client.queuePath(PROJECT, TASKS_LOCATION, TASKS_QUEUE);
	await client.createTask({
		parent,
		task: {
			// Name must be unique per runId so retries don't get new tasks and
			// we get 24h dedup on accidental double-enqueues of the same turn.
			name: `${parent}/tasks/${runId}`,
			dispatchDeadline: { seconds: DISPATCH_DEADLINE_S, nanos: 0 },
			httpRequest: {
				httpMethod: 'POST',
				url: `${workerUrl}/run`,
				headers: { 'Content-Type': 'application/json' },
				body: Buffer.from(JSON.stringify(body)).toString('base64'),
				oidcToken: {
					serviceAccountEmail: WORKER_SA,
					audience: workerUrl
				}
			}
		}
	});
}

class AgentStreamError extends Error {
	constructor(status, code) {
		super(code);
		this.status = status;
		this.code = code;
	}
}

export const agentStream = onRequest({ cors: true, timeoutSeconds: 30 }, async (req, res) => {
	if (req.method !== 'POST') {
		res.status(405).json({ ok: false, error: 'Method not allowed' });
		return;
	}

	// 1. Firebase ID token verification.
	const authHeader = req.headers.authorization || '';
	const tokenMatch = /^Bearer\s+(.+)$/i.exec(authHeader);
	if (!tokenMatch) {
		res.status(401).json({ ok: false, error: 'Authorization header required' });
		return;
	}
	let submitterUid;
	try {
		const decoded = await getAuth().verifyIdToken(tokenMatch[1]);
		submitterUid = decoded.uid;
	} catch (e) {
		console.warn('verifyIdToken rejected:', e.code || e.message);
		res.status(401).json({ ok: false, error: 'Invalid auth token' });
		return;
	}

	// 2. Rate limits — IP first (pre-UID) then UID (authenticated scope).
	// Rate limiting keys off the *submitter* UID from the request token,
	// regardless of whether this is a new chat or a shared-URL follow-up.
	const now = Date.now();
	const ip = req.ip || req.headers['x-forwarded-for'] || 'unknown';
	if (!checkRateLimit(rateLimitMap, ip, now, 10 * 60 * 1000, 20)) {
		res.status(429).json({ ok: false, error: 'Too many requests. Please wait a few minutes.' });
		return;
	}
	if (
		!checkRateLimit(
			uidRateLimitMap,
			submitterUid,
			now,
			UID_RATE_LIMIT_WINDOW_MS,
			UID_RATE_LIMIT_MAX
		)
	) {
		res.status(429).json({ ok: false, error: 'Hourly pipeline limit reached.' });
		return;
	}

	// 3. Input validation.
	const { message, sessionId } = req.body || {};
	const placeContext = validatePlaceContext(req.body?.placeContext);
	if (!message || typeof message !== 'string' || !sessionId) {
		res.status(400).json({ ok: false, error: 'message and sessionId are required' });
		return;
	}
	if (message.length > 2000) {
		res.status(400).json({ ok: false, error: 'Message too long' });
		return;
	}

	// 4. Server-generated runId — never trust a client-supplied one.
	const runId = crypto.randomUUID();
	const sessionRef = db.collection('sessions').doc(sessionId);

	// 5. Atomic session upsert + turn-doc creation under capability-URL rules
	// (plan §5 / §6 / §8). Two UID roles are explicit here:
	//   - `submitterUid` — caller of this request; goes into `participants` and
	//     rate limiting.
	//   - `creatorUid` — the session's stored `userId`, allocated on the first
	//     turn. Preserved across follow-ups (even from a different submitter)
	//     because the worker continues the shared Vertex Agent Engine session
	//     under the original creator UID.
	// Transactions can re-run on contention, so we capture decision signals
	// into outer-scope vars on every attempt; the last successful attempt
	// wins and those are the values we use for the Cloud Task body.
	let existingAdkSessionId = null;
	let isFirstMessage = false;
	let creatorUid = submitterUid;
	let newTurnIdx = 1;
	try {
		await db.runTransaction(async (t) => {
			const snap = await t.get(sessionRef);
			const existing = snap.exists ? snap.data() : null;

			// One-in-flight guard per chat (plan §6). The ownership gate is
			// intentionally gone — any signed-in visitor with the URL may
			// submit a turn.
			if (existing && (existing.status === 'queued' || existing.status === 'running')) {
				throw new AgentStreamError(409, 'previous_turn_in_flight');
			}

			const lastTurnIndex = existing?.lastTurnIndex ?? 0;
			if (lastTurnIndex >= MAX_TURNS_PER_SESSION) {
				throw new AgentStreamError(409, 'turn_cap_reached');
			}

			isFirstMessage = !existing;
			existingAdkSessionId = existing?.adkSessionId || null;
			creatorUid = existing?.userId || submitterUid;
			newTurnIdx = lastTurnIndex + 1;

			const perTurn = {
				currentRunId: runId,
				currentAttempt: 0,
				currentWorkerId: null,
				status: 'queued',
				queuedAt: FieldValue.serverTimestamp(),
				lastHeartbeat: null,
				lastEventAt: null,
				error: null,
				lastTurnIndex: newTurnIdx,
				updatedAt: FieldValue.serverTimestamp()
			};

			if (isFirstMessage) {
				t.set(sessionRef, {
					userId: submitterUid,
					participants: [submitterUid],
					createdAt: FieldValue.serverTimestamp(),
					adkSessionId: null, // worker creates on first turn
					placeContext: placeContext || null,
					title: null,
					...perTurn
				});
			} else {
				// Preserve userId / createdAt / adkSessionId / placeContext / title.
				// `participants` arrays-union'd so shared-URL contributors pin
				// the chat to their sidebar without overwriting prior UIDs.
				t.update(sessionRef, {
					...perTurn,
					participants: FieldValue.arrayUnion(submitterUid)
				});
			}

			// Create the turn doc in the same transaction so sidebar readers
			// and the worker see a consistent lastTurnIndex → turn-doc pairing.
			const turnKey = String(newTurnIdx).padStart(4, '0');
			const turnRef = sessionRef.collection('turns').doc(turnKey);
			t.set(turnRef, {
				turnIndex: newTurnIdx,
				runId,
				userMessage: message,
				status: 'pending',
				reply: null,
				sources: null,
				turnSummary: null,
				createdAt: FieldValue.serverTimestamp(),
				completedAt: null,
				error: null
			});
		});
	} catch (err) {
		if (err instanceof AgentStreamError) {
			res.status(err.status).json({ ok: false, error: err.code });
		} else {
			console.error('agentStream transaction failed:', err.message || err);
			res.status(500).json({ ok: false, error: 'session_upsert_failed' });
		}
		return;
	}

	// 6. Build the query text the worker feeds to the pipeline. Matches the
	// shape the current pipeline expects; worker doesn't do any further
	// mutation. [Context: ...] is only injected on the first message — after
	// that the ADK session holds the context in state.
	const today = new Date(now).toLocaleDateString('en-US', {
		year: 'numeric',
		month: 'long',
		day: 'numeric'
	});
	let queryText = `[Date: ${today}] ${message}`;
	if (isFirstMessage && placeContext && placeContext.name) {
		queryText = `[Context: asking about ${placeContext.name}, ${placeContext.secondary || ''} (Place ID: ${placeContext.placeId || 'unknown'})] ${queryText}`;
	}

	// 7. Enqueue Cloud Task. On enqueue failure, flip the freshly-queued
	// session to status=error so the watchdog doesn't sweep it, and surface
	// a 502 so the client can retry deterministically.
	//
	// Cloud Task body carries the creator UID (not the submitter UID) because
	// the worker uses it for Vertex Agent Engine session ownership. `turnIdx`
	// is sent as an integer; the worker formats to a zero-padded doc key on
	// its side.
	try {
		await enqueueRunTask({
			runId,
			body: {
				sessionId,
				runId,
				turnIdx: newTurnIdx,
				adkSessionId: existingAdkSessionId,
				userId: creatorUid,
				queryText,
				isFirstMessage,
				placeContext: placeContext || null
			}
		});
	} catch (err) {
		console.error('Cloud Tasks enqueue failed:', err.message || err);
		try {
			await sessionRef.update({
				status: 'error',
				error: 'enqueue_failed'
			});
		} catch (e2) {
			console.error('Post-enqueue status=error write failed:', e2.message || e2);
		}
		res.status(502).json({ ok: false, error: 'enqueue_failed' });
		return;
	}

	res.status(202).json({ ok: true, sessionId, runId });
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
		res.status(503).json({ ok: false, error: 'Speech service unreachable' });
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
				Accept: 'audio/mpeg'
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
		res.status(503).json({ ok: false, error: 'Speech service unreachable' });
	}
});

// --- Agent delete endpoint (hard-deletes a chat, creator-only) ---
//
// Plan §6 / §8: possession of the chat URL grants read + continue, but hard
// deletion stays creator-only. Verifies a Firebase ID token, checks that the
// caller's UID matches the session's stored `userId`, then uses
// `db.recursiveDelete(...)` to reap the session doc plus both subcollections
// (`turns/*`, `events/*`) in one server call.
//
// No soft-delete, no undo, no mid-run drain protocol. If the worker is still
// writing when the delete lands, its next fenced write will hit OwnershipLost
// and bail; any event docs it writes before that are bounded by the 3-day
// events TTL.
export const agentDelete = onRequest(
	{ cors: true, timeoutSeconds: 120, memory: '256MiB' },
	async (req, res) => {
		if (req.method !== 'POST') {
			res.status(405).json({ ok: false, error: 'Method not allowed' });
			return;
		}

		// 1. Firebase ID token verification.
		const authHeader = req.headers.authorization || '';
		const tokenMatch = /^Bearer\s+(.+)$/i.exec(authHeader);
		if (!tokenMatch) {
			res.status(401).json({ ok: false, error: 'Authorization header required' });
			return;
		}
		let uid;
		try {
			const decoded = await getAuth().verifyIdToken(tokenMatch[1]);
			uid = decoded.uid;
		} catch (e) {
			console.warn('agentDelete verifyIdToken rejected:', e.code || e.message);
			res.status(401).json({ ok: false, error: 'Invalid auth token' });
			return;
		}

		// 2. Input validation.
		const { sid } = req.body || {};
		if (!sid || typeof sid !== 'string') {
			res.status(400).json({ ok: false, error: 'sid is required' });
			return;
		}

		// 3. Ownership check. Read the session first; a missing doc is a 404,
		// a non-creator caller is a 403. Admin SDK bypasses Firestore rules,
		// so this explicit check is load-bearing.
		const sessionRef = db.collection('sessions').doc(sid);
		let snap;
		try {
			snap = await sessionRef.get();
		} catch (err) {
			console.error('agentDelete session read failed:', sid, err.message || err);
			res.status(500).json({ ok: false, error: 'delete_failed' });
			return;
		}

		if (!snap.exists) {
			res.status(404).json({ ok: false, error: 'session_not_found' });
			return;
		}

		const data = snap.data() || {};
		if (data.userId !== uid) {
			res.status(403).json({ ok: false, error: 'not_creator' });
			return;
		}

		// 4. Recursive delete. Firebase Admin SDK 13 reaps the session doc and
		// both subcollections in one call. No batching, no BulkWriter, no
		// retry loop — on failure we log, return 500, and let the operator
		// (or the user) retry.
		try {
			await db.recursiveDelete(sessionRef);
		} catch (err) {
			console.error('agentDelete recursiveDelete failed:', sid, err.message || err);
			res.status(500).json({ ok: false, error: 'delete_failed' });
			return;
		}

		res.status(200).json({ ok: true });
	}
);
