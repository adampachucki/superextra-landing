// Chat transport endpoints: `agentStream` (session/turn lifecycle + direct
// handoff to the Vertex AI Agent Engine), `agentCancel`, `agentFeedback`,
// and `agentDelete`. Firestore doc shapes: docs/firestore-contract.md.
import crypto from 'node:crypto';
import { onRequest } from 'firebase-functions/v2/https';
import { defineSecret } from 'firebase-functions/params';
import { getAuth } from 'firebase-admin/auth';
import { FieldValue } from 'firebase-admin/firestore';
import { db } from './firebase.js';
import { gearHandoff, gearHandoffCleanup } from './gear-handoff.js';
import { runIntakeConversation } from './intake-agent.js';
import { detectLanguage, SUPPORTED_LOCALES } from './detect-language.js';
import { checkRateLimit, validatePlaceContext } from './utils.js';

const googlePlacesKey = defineSecret('GOOGLE_PLACES_API_KEY');

const rateLimitMap = new Map();
const uidRateLimitMap = new Map();

// Test-only — bypass abuse limits so each test starts from a clean slate.
export function _resetRateLimits() {
	rateLimitMap.clear();
	uidRateLimitMap.clear();
}

// Hourly per-UID pipeline rate limit. An abuse cap that runs in front of
// every agentStream call — the product-level daily research limit is
// enforced inside the agent (see agent/superextra_agent/quota_gate.py).
const UID_RATE_LIMIT_WINDOW_MS = 60 * 60 * 1000; // 1 hour
const UID_RATE_LIMIT_MAX = 20;

class AgentStreamError extends Error {
	constructor(status, code) {
		super(code);
		this.status = status;
		this.code = code;
	}
}

class RunOwnershipLost extends Error {
	constructor() {
		super('run_ownership_lost');
	}
}

function assertRunOwnership(data, runId) {
	if (data?.currentRunId !== runId) throw new RunOwnershipLost();
	if (data?.status !== 'queued' && data?.status !== 'running') throw new RunOwnershipLost();
}

async function assertRunStillCurrent(sessionRef, runId) {
	const snap = await sessionRef.get();
	if (!snap.exists) throw new RunOwnershipLost();
	assertRunOwnership(snap.data() || {}, runId);
}

function finishAfterRunOwnershipLost(res, sessionId, runId) {
	res.status(202).json({ ok: true, sessionId, runId, cancelled: true });
}

// Shared recovery for agentStream catch blocks: if `err` — or a re-read of the
// session — shows this run no longer owns the turn, respond accordingly.
// Returns true when a response was sent and the caller must stop.
async function respondIfRunOwnershipLost(err, sessionRef, res, sessionId, runId) {
	if (err instanceof RunOwnershipLost) {
		finishAfterRunOwnershipLost(res, sessionId, runId);
		return true;
	}
	try {
		await assertRunStillCurrent(sessionRef, runId);
	} catch (ownershipErr) {
		if (ownershipErr instanceof RunOwnershipLost) {
			finishAfterRunOwnershipLost(res, sessionId, runId);
			return true;
		}
		console.error('agentStream ownership check failed:', ownershipErr.message || ownershipErr);
		res.status(500).json({ ok: false, error: 'session_ownership_check_failed' });
		return true;
	}
	return false;
}

function titleFromMessage(message) {
	const words = message
		.replace(/[^\p{L}\p{N}\s'-]/gu, ' ')
		.trim()
		.split(/\s+/)
		.filter(Boolean)
		.slice(0, 5);
	if (!words.length) return null;
	return words
		.map((word) => word.charAt(0).toUpperCase() + word.slice(1))
		.join(' ')
		.slice(0, 60);
}

async function completeDirectIntake({
	sessionRef,
	runId,
	turnIdx,
	reply,
	intakeState,
	startedAtMs,
	title
}) {
	const turnKey = String(turnIdx).padStart(4, '0');
	const turnRef = sessionRef.collection('turns').doc(turnKey);
	const finishedAtMs = Date.now();
	const elapsedMs = Math.max(0, finishedAtMs - startedAtMs);
	await db.runTransaction(async (tx) => {
		const snap = await tx.get(sessionRef);
		if (!snap.exists) throw new RunOwnershipLost();
		const data = snap.data() || {};
		assertRunOwnership(data, runId);

		const sessionUpdate = {
			status: 'complete',
			error: null,
			activeAgent: null,
			activeStage: null,
			engineSessionStarted: false,
			intakeState: intakeState || null,
			updatedAt: FieldValue.serverTimestamp()
		};
		if (!data.title && title) sessionUpdate.title = title;

		tx.update(sessionRef, sessionUpdate);
		tx.update(turnRef, {
			status: 'complete',
			reply,
			sources: [],
			turnKind: 'intake_reply',
			error: null,
			completedAt: FieldValue.serverTimestamp(),
			turnSummary: { startedAtMs, finishedAtMs, elapsedMs }
		});
	});
}

async function markEngineSessionStarted({ sessionRef, runId }) {
	await db.runTransaction(async (tx) => {
		const snap = await tx.get(sessionRef);
		if (!snap.exists) return;
		const data = snap.data() || {};
		if (data.currentRunId !== runId) return;
		tx.update(sessionRef, {
			engineSessionStarted: true,
			intakeState: null,
			updatedAt: FieldValue.serverTimestamp()
		});
	});
}

async function recordResearchStart({ sessionRef, runId, turnIdx, placeContext, acknowledgement }) {
	const turnKey = String(turnIdx).padStart(4, '0');
	const turnRef = sessionRef.collection('turns').doc(turnKey);
	await db.runTransaction(async (tx) => {
		const snap = await tx.get(sessionRef);
		if (!snap.exists) throw new RunOwnershipLost();
		const data = snap.data() || {};
		assertRunOwnership(data, runId);
		tx.update(sessionRef, {
			placeContext,
			updatedAt: FieldValue.serverTimestamp()
		});
		if (acknowledgement) {
			tx.update(turnRef, {
				acknowledgement,
				acknowledgedAt: FieldValue.serverTimestamp()
			});
		}
	});
}

async function readIntakeHistory(sessionRef, latestTurnIdx) {
	const history = [];
	for (let idx = 1; idx < latestTurnIdx; idx += 1) {
		const turnKey = String(idx).padStart(4, '0');
		const turnSnap = await sessionRef.collection('turns').doc(turnKey).get();
		if (!turnSnap.exists) continue;
		const turn = turnSnap.data() || {};
		if (turn.status !== 'complete') continue;
		if (typeof turn.userMessage === 'string' && turn.userMessage.trim()) {
			history.push({ role: 'user', text: turn.userMessage });
		}
		if (typeof turn.reply === 'string' && turn.reply.trim()) {
			history.push({ role: 'assistant', text: turn.reply });
		}
	}
	return history;
}

function defaultEngineSessionId(sid) {
	return `se-${sid}`;
}

function rotatedEngineSessionId(sid, generation) {
	return `se-${sid}-g${generation}`;
}

function compactForAgentState(text, maxChars) {
	return String(text || '')
		.replace(/\s+/g, ' ')
		.trim()
		.slice(0, maxChars);
}

async function readRotationSeedState(sessionRef, latestTurnIdx, previousStoppedRequest) {
	const transcript = [];
	let finalReport = null;
	let legacyFinalReport = null;
	for (let idx = 1; idx < latestTurnIdx; idx += 1) {
		const turnKey = String(idx).padStart(4, '0');
		const turnSnap = await sessionRef.collection('turns').doc(turnKey).get();
		if (!turnSnap.exists) continue;
		const turn = turnSnap.data() || {};
		const userMessage =
			typeof turn.userMessage === 'string' ? compactForAgentState(turn.userMessage, 500) : '';
		const reply = typeof turn.reply === 'string' ? compactForAgentState(turn.reply, 1600) : '';
		if (turn.status !== 'complete' || !reply) continue;
		if (turn.turnKind === 'research_report') {
			finalReport = turn.reply;
		} else if (
			!turn.turnKind &&
			legacyFinalReport === null &&
			Array.isArray(turn.sources) &&
			turn.sources.length > 0
		) {
			legacyFinalReport = turn.reply;
		}
		if (userMessage) {
			transcript.push(`Turn ${idx}\nUser: ${userMessage}\nAnswer: ${reply}`);
		}
	}
	const seedState = {
		places_by_id: {}
	};
	const report = finalReport || legacyFinalReport;
	if (report && report.trim()) {
		seedState.final_report = report;
	}
	if (transcript.length) {
		seedState.continuation_notes = transcript.join('\n\n').slice(-6000);
	}
	const stopped = compactForAgentState(previousStoppedRequest, 1000);
	if (stopped) {
		seedState.previous_stopped_request = stopped;
	}
	return seedState;
}

function placeContextPrefix(placeContext) {
	if (!placeContext?.name) return '';
	const focusLabel = [placeContext.name, placeContext.secondary].filter(Boolean).join(', ');
	return `[Context: selected focus: ${focusLabel} (Google Place ID: ${placeContext.placeId || 'unknown'})] `;
}

/**
 * Verify the Bearer ID token on a request, rejecting missing tokens and
 * anonymous sign-ins. On failure writes the 401 response and returns null;
 * on success returns the decoded token. `label` tags the rejection log line.
 */
async function verifyAuthedRequest(req, res, label) {
	const tokenMatch = /^Bearer\s+(.+)$/i.exec(req.headers.authorization || '');
	if (!tokenMatch) {
		res.status(401).json({ ok: false, error: 'Authorization header required' });
		return null;
	}
	try {
		const decoded = await getAuth().verifyIdToken(tokenMatch[1]);
		if (decoded?.firebase?.sign_in_provider === 'anonymous') {
			res.status(401).json({ ok: false, error: 'AUTH_REQUIRED' });
			return null;
		}
		return decoded;
	} catch (e) {
		console.warn(`${label} verifyIdToken rejected:`, e.code || e.message);
		res.status(401).json({ ok: false, error: 'Invalid auth token' });
		return null;
	}
}

const agentStreamOptions = { cors: true, timeoutSeconds: 90, secrets: [googlePlacesKey] };

export const agentStream = onRequest(agentStreamOptions, async (req, res) => {
	if (req.method !== 'POST') {
		res.status(405).json({ ok: false, error: 'Method not allowed' });
		return;
	}

	// 1. Firebase ID token verification.
	const decoded = await verifyAuthedRequest(req, res, 'agentStream');
	if (!decoded) return;
	const submitterUid = decoded.uid;
	const submitterClaims = {
		email: typeof decoded.email === 'string' ? decoded.email : null,
		displayName: typeof decoded.name === 'string' ? decoded.name : null,
		photoURL: typeof decoded.picture === 'string' ? decoded.picture : null
	};

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
	const submittedPlaceContext = validatePlaceContext(req.body?.placeContext);
	if (!message || typeof message !== 'string' || !sessionId) {
		res.status(400).json({ ok: false, error: 'message and sessionId are required' });
		return;
	}
	if (message.length > 2000) {
		res.status(400).json({ ok: false, error: 'Message too long' });
		return;
	}
	let placeContext = submittedPlaceContext;

	// 4. Server-generated runId — never trust a client-supplied one.
	const runId = crypto.randomUUID();
	const sessionRef = db.collection('sessions').doc(sessionId);

	// Language follows what the user WRITES, not the location they ask about.
	// The detector judges only ordinary prose and returns null when a message
	// is just a place name; the conversation's language is then resolved inside
	// the upsert txn as: detected ?? language already on the session ?? UI
	// locale (first turn). So a location can never flip the language; only the
	// user actually writing in a different language can.
	const uiLocale = SUPPORTED_LOCALES.includes(req.body?.locale) ? req.body.locale : 'en';
	const detectedLanguage = await detectLanguage({ message });
	let promptLanguage = detectedLanguage || uiLocale;

	// 5. Atomic session upsert + turn-doc creation under capability-URL rules
	// (plan §5 / §6 / §8). Two UID roles are explicit here:
	//   - `submitterUid` — caller of this request; goes into `participants` and
	//     rate limiting.
	//   - `creatorUid` — the session's stored `userId`, allocated on the first
	//     turn. Preserved across follow-ups (even from a different submitter)
	//     because gearHandoff resumes the shared Reasoning Engine session under
	//     the original creator UID.
	// Transactions can re-run on contention, so we capture decision signals
	// into outer-scope vars on every attempt.
	let isFirstMessage = false;
	let shouldRunIntake = false;
	let createEngineSession = false;
	let engineSessionId = defaultEngineSessionId(sessionId);
	let engineSessionGeneration = 1;
	let rotatedAfterCancel = false;
	let previousStoppedRequest = null;
	let creatorUid = submitterUid;
	let newTurnIdx = 1;
	let intakeState = null;

	try {
		await db.runTransaction(async (t) => {
			const snap = await t.get(sessionRef);
			const existing = snap.exists ? snap.data() : null;
			// Resolve the conversation language: this message's detected prose
			// language, else the language already on the chat, else the UI locale.
			// A place-name message (detected null) keeps the established language.
			promptLanguage = detectedLanguage || existing?.language || uiLocale;
			const lastTurnIndex = existing?.lastTurnIndex ?? 0;
			let previousTurn = null;
			if (existing && lastTurnIndex > 0) {
				const previousTurnRef = sessionRef
					.collection('turns')
					.doc(String(lastTurnIndex).padStart(4, '0'));
				const previousTurnSnap = await t.get(previousTurnRef);
				previousTurn = previousTurnSnap.exists ? previousTurnSnap.data() || {} : null;
			}

			// Read the submitter's user doc — lazy provision identity fields
			// only. Quota enforcement lives in the agent's research_pipeline
			// before_agent_callback (see agent/superextra_agent/quota_gate.py).
			const userRef = db.collection('users').doc(submitterUid);
			const userSnap = await t.get(userRef);
			const userDoc = userSnap.exists ? userSnap.data() || {} : null;

			// One-in-flight guard per chat (plan §6). The ownership gate is
			// intentionally gone — any signed-in visitor with the URL may
			// submit a turn.
			if (existing && (existing.status === 'queued' || existing.status === 'running')) {
				throw new AgentStreamError(409, 'previous_turn_in_flight');
			}

			isFirstMessage = !existing;
			const engineSessionStarted = existing ? existing.engineSessionStarted !== false : false;
			shouldRunIntake = !engineSessionStarted;
			const priorGeneration = Number.isInteger(existing?.engineSessionGeneration)
				? existing.engineSessionGeneration
				: 1;
			rotatedAfterCancel =
				!!previousTurn &&
				previousTurn.status === 'error' &&
				previousTurn.error === 'user_cancelled';
			previousStoppedRequest =
				rotatedAfterCancel && typeof previousTurn.userMessage === 'string'
					? previousTurn.userMessage
					: null;
			if (rotatedAfterCancel) {
				engineSessionGeneration = priorGeneration + 1;
				engineSessionId = rotatedEngineSessionId(sessionId, engineSessionGeneration);
			} else {
				engineSessionGeneration = priorGeneration;
				engineSessionId =
					typeof existing?.engineSessionId === 'string' && existing.engineSessionId
						? existing.engineSessionId
						: defaultEngineSessionId(sessionId);
			}
			createEngineSession = isFirstMessage || !engineSessionStarted || rotatedAfterCancel;
			creatorUid = existing?.userId || submitterUid;
			newTurnIdx = lastTurnIndex + 1;
			intakeState = existing?.intakeState || null;
			if (!placeContext && existing?.placeContext) {
				placeContext = validatePlaceContext(existing.placeContext);
			}

			const perTurn = {
				currentRunId: runId,
				status: 'queued',
				queuedAt: FieldValue.serverTimestamp(),
				lastHeartbeat: null,
				lastEventAt: null,
				error: null,
				lastTurnIndex: newTurnIdx,
				engineSessionId,
				engineSessionGeneration,
				// Detected per turn; the frontend localizes activity labels to it.
				language: promptLanguage,
				updatedAt: FieldValue.serverTimestamp()
			};

			if (isFirstMessage) {
				t.set(sessionRef, {
					userId: submitterUid,
					participants: [submitterUid],
					createdAt: FieldValue.serverTimestamp(),
					placeContext: placeContext || null,
					engineSessionStarted: false,
					engineSessionId,
					engineSessionGeneration,
					intakeState: null,
					title: null,
					...perTurn
				});
			} else {
				// Preserve userId / createdAt / placeContext / title.
				// `participants` arrays-union'd so shared-URL contributors pin
				// the chat to their sidebar without overwriting prior UIDs.
				t.update(sessionRef, {
					...perTurn,
					cancelledAt: FieldValue.delete(),
					participants: FieldValue.arrayUnion(submitterUid)
				});
			}

			// Create the turn doc in the same transaction so sidebar readers
			// and the Reasoning Engine plugin see a consistent
			// lastTurnIndex → turn-doc pairing.
			const turnKey = String(newTurnIdx).padStart(4, '0');
			const turnRef = sessionRef.collection('turns').doc(turnKey);
			t.set(turnRef, {
				turnIndex: newTurnIdx,
				runId,
				userMessage: message,
				language: promptLanguage,
				status: 'pending',
				reply: null,
				acknowledgement: null,
				acknowledgedAt: null,
				sources: null,
				turnSummary: null,
				turnKind: null,
				createdAt: FieldValue.serverTimestamp(),
				completedAt: null,
				error: null
			});

			// User-doc maintenance — identity fields only. Quota counters live
			// on the user doc but are owned by the agent-side quota gate
			// (agent/superextra_agent/quota_gate.py); never written here.
			const identity = {
				email: submitterClaims?.email ?? null,
				displayName: submitterClaims?.displayName ?? null,
				photoURL: submitterClaims?.photoURL ?? null
			};
			if (!userDoc) {
				t.set(userRef, {
					...identity,
					plan: 'free',
					limitOverrides: null,
					createdAt: FieldValue.serverTimestamp(),
					updatedAt: FieldValue.serverTimestamp()
				});
			} else if (isFirstMessage) {
				const update = { updatedAt: FieldValue.serverTimestamp() };
				// Refresh identity fields opportunistically when present (Google
				// photo / display name changes).
				if (identity.email) update.email = identity.email;
				if (identity.displayName) update.displayName = identity.displayName;
				if (identity.photoURL) update.photoURL = identity.photoURL;
				if (Object.keys(update).length > 1) t.update(userRef, update);
			}
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

	const intakeStartedAtMs = Date.now();
	let researchQuestion = null;
	if (shouldRunIntake) {
		try {
			const history = await readIntakeHistory(sessionRef, newTurnIdx);
			const decision = await runIntakeConversation({
				history,
				message,
				intakeState,
				selectedPlaceContext: placeContext,
				apiKey: googlePlacesKey.value(),
				language: promptLanguage
			});
			intakeState = decision.state || null;

			if (decision.action === 'reply') {
				await completeDirectIntake({
					sessionRef,
					runId,
					turnIdx: newTurnIdx,
					reply: decision.reply,
					intakeState,
					startedAtMs: now,
					title: titleFromMessage(intakeState?.originalIntent || message)
				});
				console.info('agentStream direct intake reply', {
					sessionId,
					runId,
					turnIdx: newTurnIdx,
					latencyMs: Date.now() - intakeStartedAtMs,
					reason: decision.reason
				});
				res.status(202).json({ ok: true, sessionId, runId, direct: 'intake' });
				return;
			}

			if (decision.action === 'start_research') {
				researchQuestion = decision.researchQuestion || message;
				placeContext = decision.placeContext || null;
				const acknowledgement = decision.acknowledgement || null;
				await recordResearchStart({
					sessionRef,
					runId,
					turnIdx: newTurnIdx,
					placeContext,
					acknowledgement
				});
				console.info('agentStream intake ready for research', {
					sessionId,
					runId,
					turnIdx: newTurnIdx,
					latencyMs: Date.now() - intakeStartedAtMs,
					hasAcknowledgement: !!acknowledgement,
					placeId: placeContext?.placeId || null,
					reason: decision.reason
				});
			}
		} catch (err) {
			if (await respondIfRunOwnershipLost(err, sessionRef, res, sessionId, runId)) return;
			console.warn('intake failed; falling back to Agent Engine:', err.message || err);
		}
	}

	// 6. Build the query text the pipeline receives. A fresh ADK working
	// session does not have prior hidden state, so any Firestore-visible
	// place/stopped-request context needed after rotation is injected into
	// the user-visible query text.
	// Put the user's own words FIRST so the model anchors to the prompt language,
	// then append the bracketed context. Leading English prefixes biased the
	// model toward English narration (thoughts). An ISO date avoids the English
	// month name; the [Date:]/[Context:] markers the instructions reference work
	// anywhere in the message.
	const isoDate = new Date(now).toISOString().slice(0, 10);
	const contextParts = [];
	if (createEngineSession && placeContext && placeContext.name) {
		contextParts.push(placeContextPrefix(placeContext).trim());
	}
	if (createEngineSession && previousStoppedRequest) {
		contextParts.push(
			`[Previous stopped request: ${compactForAgentState(previousStoppedRequest, 1000)}]`
		);
	}
	contextParts.push(`[Date: ${isoDate}]`);
	const queryText = `${researchQuestion || message} ${contextParts.join(' ')}`;
	const seedState = rotatedAfterCancel
		? await readRotationSeedState(sessionRef, newTurnIdx, previousStoppedRequest)
		: null;

	// 7. Direct handoff to Vertex AI Agent Engine. Cleanup on failure flips
	// session + turn to status='error' atomically inside a `currentRunId`-
	// fenced txn (mirrors watchdog.js).
	try {
		await assertRunStillCurrent(sessionRef, runId);
		await gearHandoff({
			sid: sessionId,
			engineSessionId,
			runId,
			turnIdx: newTurnIdx,
			userId: creatorUid,
			// quotaUid is the SUBMITTER's uid so the daily research counter
			// charges the user actually making the request, not the original
			// chat creator (matters for shared-URL contributors). The agent's
			// quota gate reads this from session state per turn.
			quotaUid: submitterUid,
			message: queryText,
			isEngineFirstMessage: createEngineSession,
			createEngineSession,
			seedState,
			promptLanguage
		});
		if (createEngineSession) {
			try {
				await markEngineSessionStarted({ sessionRef, runId });
			} catch (markErr) {
				console.error('engineSessionStarted marker failed:', markErr.message || markErr);
			}
		}
		res.status(202).json({ ok: true, sessionId, runId });
	} catch (err) {
		if (await respondIfRunOwnershipLost(err, sessionRef, res, sessionId, runId)) return;
		console.error('gearHandoff failed:', err.message || err);
		try {
			await gearHandoffCleanup(
				db,
				sessionId,
				runId,
				newTurnIdx,
				`gear_handoff_failed:${err.message || 'unknown'}`
			);
		} catch (cleanupErr) {
			console.error('gearHandoff cleanup write failed:', cleanupErr.message || cleanupErr);
		}
		res.status(502).json({ ok: false, error: 'handoff_failed' });
	}
});

// --- Agent cancel endpoint (participant stop for the active turn) ---

export const agentCancel = onRequest(
	{ cors: true, timeoutSeconds: 30, memory: '256MiB' },
	async (req, res) => {
		if (req.method !== 'POST') {
			res.status(405).json({ ok: false, error: 'Method not allowed' });
			return;
		}

		const decoded = await verifyAuthedRequest(req, res, 'agentCancel');
		if (!decoded) return;
		const uid = decoded.uid;

		const { sid, runId: requestedRunId, turnIndex: requestedTurnIndex } = req.body || {};
		if (!sid || typeof sid !== 'string') {
			res.status(400).json({ ok: false, error: 'sid is required' });
			return;
		}
		if (!requestedRunId || typeof requestedRunId !== 'string') {
			res.status(400).json({ ok: false, error: 'runId is required' });
			return;
		}
		if (!Number.isInteger(requestedTurnIndex)) {
			res.status(400).json({ ok: false, error: 'turnIndex is required' });
			return;
		}

		const sessionRef = db.collection('sessions').doc(sid);
		let outcome = { status: 500, body: { ok: false, error: 'cancel_failed' } };
		try {
			await db.runTransaction(async (tx) => {
				const snap = await tx.get(sessionRef);
				if (!snap.exists) {
					outcome = { status: 404, body: { ok: false, error: 'session_not_found' } };
					return;
				}
				const data = snap.data() || {};
				const participants = Array.isArray(data.participants) ? data.participants : [];
				if (!participants.includes(uid)) {
					outcome = { status: 403, body: { ok: false, error: 'not_participant' } };
					return;
				}
				if (data.status !== 'running' && data.status !== 'queued') {
					outcome = { status: 200, body: { ok: true, terminal: true } };
					return;
				}
				const runId = data.currentRunId;
				const turnIdx = data.lastTurnIndex;
				if (!runId || typeof runId !== 'string' || !Number.isInteger(turnIdx)) {
					outcome = { status: 409, body: { ok: false, error: 'cancel_not_active' } };
					return;
				}
				if (runId !== requestedRunId || turnIdx !== requestedTurnIndex) {
					outcome = { status: 409, body: { ok: false, error: 'cancel_target_mismatch' } };
					return;
				}
				if (data.status === 'queued') {
					outcome = { status: 409, body: { ok: false, error: 'cancel_not_started' } };
					return;
				}
				const turnRef = sessionRef.collection('turns').doc(String(turnIdx).padStart(4, '0'));
				const turnSnap = await tx.get(turnRef);
				if (!turnSnap.exists) {
					outcome = { status: 409, body: { ok: false, error: 'active_turn_missing' } };
					return;
				}
				const turn = turnSnap.data() || {};
				if (turn.runId !== runId || (turn.status !== 'pending' && turn.status !== 'running')) {
					outcome = { status: 409, body: { ok: false, error: 'active_turn_mismatch' } };
					return;
				}

				// Flip session + turn to error('user_cancelled'). The daily
				// usage counters are intentionally NOT refunded — the quota
				// gates in agent/superextra_agent/quota_gate.py reserve a credit
				// before the agent runs, and cancelled/failed work still counts.
				tx.update(sessionRef, {
					status: 'error',
					error: 'user_cancelled',
					currentRunId: FieldValue.delete(),
					activeAgent: FieldValue.delete(),
					activeStage: FieldValue.delete(),
					activeStageStartedAt: FieldValue.delete(),
					activeModel: FieldValue.delete(),
					activeInvocationId: FieldValue.delete(),
					cancelledAt: FieldValue.serverTimestamp(),
					updatedAt: FieldValue.serverTimestamp()
				});
				tx.update(turnRef, {
					status: 'error',
					error: 'user_cancelled',
					completedAt: FieldValue.serverTimestamp(),
					cancelledAt: FieldValue.serverTimestamp()
				});

				outcome = { status: 200, body: { ok: true } };
			});
		} catch (err) {
			console.error('agentCancel transaction failed:', sid, err.message || err);
			res.status(500).json({ ok: false, error: 'cancel_failed' });
			return;
		}
		res.status(outcome.status).json(outcome.body);
	}
);

// --- Agent feedback endpoint (per-answer thumbs + periodic value prompt) ---
//
// Two feedback shapes share one endpoint; both require the caller to be a
// session participant (same capability check as cancel/delete).
//   kind:'rating' → 👍/👎 on a single answer. Only the binary rating is stored
//     on the turn doc (`feedback.<uid>.rating`) so the existing turns listener
//     can round-trip the "you rated this" state back to the browser. The write
//     runs in a transaction that requires the turn to already exist — otherwise
//     a participant could mint a phantom turn doc that the chat would render.
//   The "why" (downvote reasons + free-text note) is NOT put on the turn doc —
//     turn docs are readable by any signed-in client (firestore.rules), so free
//     text would leak. It goes to the server-only `feedback` collection.
//   kind:'survey' → the periodic "do you find this report useful?" prompt shown
//     after a research report (useful:'yes'|'no', plus optional reasons/note on
//     a 'no'). Appended to the same `feedback` collection.
// The `feedback` collection is never read by the client (unmatched path ⇒ rules
// deny client reads; Admin SDK bypasses rules), so it is the private analytics
// surface for ratings-with-reasons, notes, and survey answers.
function cleanFeedbackNote(value) {
	if (typeof value !== 'string') return null;
	const trimmed = value.trim();
	return trimmed ? trimmed.slice(0, 1000) : null;
}

function cleanFeedbackReasons(value) {
	if (!Array.isArray(value)) return [];
	return value
		.filter((r) => typeof r === 'string' && r.trim())
		.map((r) => r.trim().slice(0, 60))
		.slice(0, 6);
}

export const agentFeedback = onRequest(
	{ cors: true, timeoutSeconds: 30, memory: '256MiB' },
	async (req, res) => {
		if (req.method !== 'POST') {
			res.status(405).json({ ok: false, error: 'Method not allowed' });
			return;
		}

		const decoded = await verifyAuthedRequest(req, res, 'agentFeedback');
		if (!decoded) return;
		const uid = decoded.uid;

		const { sid, turnIndex, kind } = req.body || {};
		if (!sid || typeof sid !== 'string') {
			res.status(400).json({ ok: false, error: 'sid is required' });
			return;
		}
		if (!Number.isInteger(turnIndex)) {
			res.status(400).json({ ok: false, error: 'turnIndex is required' });
			return;
		}
		if (kind !== 'rating' && kind !== 'survey') {
			res.status(400).json({ ok: false, error: 'unknown_kind' });
			return;
		}
		if (kind === 'rating') {
			const { rating } = req.body;
			if (rating !== 'up' && rating !== 'down') {
				res.status(400).json({ ok: false, error: 'rating is required' });
				return;
			}
		} else {
			const { useful } = req.body;
			if (useful !== 'yes' && useful !== 'no') {
				res.status(400).json({ ok: false, error: 'useful is required' });
				return;
			}
		}

		const sessionRef = db.collection('sessions').doc(sid);
		let snap;
		try {
			snap = await sessionRef.get();
		} catch (err) {
			console.error('agentFeedback session read failed:', sid, err.message || err);
			res.status(500).json({ ok: false, error: 'feedback_failed' });
			return;
		}
		if (!snap.exists) {
			res.status(404).json({ ok: false, error: 'session_not_found' });
			return;
		}
		const participants = Array.isArray(snap.data().participants) ? snap.data().participants : [];
		if (!participants.includes(uid)) {
			res.status(403).json({ ok: false, error: 'not_participant' });
			return;
		}

		const note = cleanFeedbackNote(req.body.note);

		try {
			if (kind === 'rating') {
				const { rating } = req.body;
				const reasons = rating === 'down' ? cleanFeedbackReasons(req.body.reasons) : [];
				const turnRef = sessionRef.collection('turns').doc(String(turnIndex).padStart(4, '0'));
				// Return the outcome from the transaction (it can be retried and
				// re-invoked, so don't accumulate state in an outer variable).
				const turnExists = await db.runTransaction(async (tx) => {
					const turnSnap = await tx.get(turnRef);
					if (!turnSnap.exists) return false;
					tx.set(
						turnRef,
						{ feedback: { [uid]: { rating, at: FieldValue.serverTimestamp() } } },
						{ merge: true }
					);
					if (reasons.length || note) {
						tx.set(db.collection('feedback').doc(), {
							uid,
							sid,
							turnIndex,
							kind: 'rating',
							rating,
							reasons,
							note,
							createdAt: FieldValue.serverTimestamp()
						});
					}
					return true;
				});
				if (!turnExists) {
					res.status(404).json({ ok: false, error: 'turn_not_found' });
					return;
				}
			} else {
				const { useful } = req.body;
				const reasons = useful === 'no' ? cleanFeedbackReasons(req.body.reasons) : [];
				await db.collection('feedback').doc().set({
					uid,
					sid,
					turnIndex,
					kind: 'survey',
					useful,
					reasons,
					note,
					createdAt: FieldValue.serverTimestamp()
				});
			}
		} catch (err) {
			console.error('agentFeedback write failed:', sid, err.message || err);
			res.status(500).json({ ok: false, error: 'feedback_failed' });
			return;
		}

		res.status(200).json({ ok: true });
	}
);

// --- Agent delete endpoint (hard-deletes a chat, creator-only) ---
//
// Plan §6 / §8: possession of the chat URL grants read + continue, but hard
// deletion stays creator-only. Verifies a Firebase ID token, checks that the
// caller's UID matches the session's stored `userId`, then uses
// `db.recursiveDelete(...)` to reap the session doc plus both subcollections
// (`turns/*`, `events/*`) in one server call.
//
// No soft-delete, no undo, no mid-run drain protocol. If the Reasoning Engine
// plugin is still writing when the delete lands, its next fenced write will
// hit OwnershipLost and bail; any event docs it writes before that are bounded
// by the events TTL.
export const agentDelete = onRequest(
	{ cors: true, timeoutSeconds: 120, memory: '256MiB' },
	async (req, res) => {
		if (req.method !== 'POST') {
			res.status(405).json({ ok: false, error: 'Method not allowed' });
			return;
		}

		// 1. Firebase ID token verification.
		const decoded = await verifyAuthedRequest(req, res, 'agentDelete');
		if (!decoded) return;
		const uid = decoded.uid;

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
