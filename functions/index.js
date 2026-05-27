import crypto from 'node:crypto';
import { onRequest } from 'firebase-functions/v2/https';
import { defineSecret } from 'firebase-functions/params';
import { initializeApp } from 'firebase-admin/app';
import { getAuth } from 'firebase-admin/auth';
import { getFirestore, FieldValue } from 'firebase-admin/firestore';
import { gearHandoff, gearHandoffCleanup } from './gear-handoff.js';
import { runIntakeConversation } from './intake-agent.js';
import {
	esc,
	row,
	confirmationHtml,
	stripMarkdown,
	checkRateLimit,
	validatePlaceContext
} from './utils.js';
import {
	getLimitsConfig,
	resolveLimits,
	checkChatLimit,
	checkTurnLimit,
	todayUtc
} from './limits.js';
export { watchdog } from './watchdog.js';

initializeApp();
const db = getFirestore();

const relayKey = defineSecret('RELAY_KEY');
const elevenlabsKey = defineSecret('ELEVENLABS_API_KEY');
const googlePlacesKey = defineSecret('GOOGLE_PLACES_API_KEY');
const DEST = 'hello@superextra.ai';

export const intake = onRequest({ cors: true, secrets: [relayKey] }, async (req, res) => {
	const RELAY_KEY = relayKey.value();
	if (req.method !== 'POST') {
		res.status(405).json({ ok: false, error: 'Method not allowed' });
		return;
	}

	const data = req.body;

	const html = `
		<div style="font-family:sans-serif;max-width:520px">
			<h2 style="margin:0 0 16px">New demo request</h2>
			<table style="border-collapse:collapse;width:100%">
				${row('Business type', data.type)}
				${row('Country', data.country)}
				${row('Business / venue', data.businessName)}
				${data.placeId ? row('Google Maps', `<a href="https://www.google.com/maps/place/?q=place_id:${esc(data.placeId)}">View on Maps</a>`, true) : ''}
				${data.locations ? row('Locations', data.locations) : ''}
				${data.webUrl ? row('URL', data.webUrl) : ''}
				${row('Demo contact', data.fullName)}
				${row('Work email', data.email)}
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
				subject: `Demo request - ${data.businessName || data.type}`,
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
				subject: 'Superextra demo request received',
				html: confirmationHtml(data.fullName)
			})
		});
	} catch (err) {
		console.error('Confirmation email failed:', err);
	}

	res.json({ ok: true });
});

// row, esc, confirmationHtml imported from ./utils.js

// --- Agent chat endpoint (hands off directly to Vertex AI Agent Engine) ---

const rateLimitMap = new Map();
const uidRateLimitMap = new Map();
const magicLinkRateLimitMap = new Map();

// Test-only — bypass abuse limits so each test starts from a clean slate.
export function _resetRateLimits() {
	rateLimitMap.clear();
	uidRateLimitMap.clear();
	magicLinkRateLimitMap.clear();
}
// Hourly per-UID pipeline rate limit. Bounds cancel-retry abuse on top of the
// product-level per-day/per-chat limits in `config/limits`.
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

const agentStreamOptions = { cors: true, timeoutSeconds: 90, secrets: [googlePlacesKey] };

export const agentStream = onRequest(agentStreamOptions, async (req, res) => {
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
	let submitterClaims = null;
	try {
		const decoded = await getAuth().verifyIdToken(tokenMatch[1]);
		if (decoded?.firebase?.sign_in_provider === 'anonymous') {
			res.status(401).json({ ok: false, error: 'AUTH_REQUIRED' });
			return;
		}
		submitterUid = decoded.uid;
		submitterClaims = {
			email: typeof decoded.email === 'string' ? decoded.email : null,
			displayName: typeof decoded.name === 'string' ? decoded.name : null,
			photoURL: typeof decoded.picture === 'string' ? decoded.picture : null
		};
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

	// Resolve plan limits outside the transaction (cached, best-effort 60s TTL).
	// All transaction reads must precede writes; the config snapshot is stable
	// for the duration of the transaction.
	const limitsConfig = await getLimitsConfig(db);
	const today = todayUtc();
	try {
		await db.runTransaction(async (t) => {
			const snap = await t.get(sessionRef);
			const existing = snap.exists ? snap.data() : null;
			const lastTurnIndex = existing?.lastTurnIndex ?? 0;
			let previousTurn = null;
			if (existing && lastTurnIndex > 0) {
				const previousTurnRef = sessionRef
					.collection('turns')
					.doc(String(lastTurnIndex).padStart(4, '0'));
				const previousTurnSnap = await t.get(previousTurnRef);
				previousTurn = previousTurnSnap.exists ? previousTurnSnap.data() || {} : null;
			}

			// Read the submitter's user doc — drives per-account limit checks
			// and lazy provisioning. Inside the transaction so the chats-per-day
			// counter increments atomically with the session create.
			const userRef = db.collection('users').doc(submitterUid);
			const userSnap = await t.get(userRef);
			const userDoc = userSnap.exists ? userSnap.data() || {} : null;

			// One-in-flight guard per chat (plan §6). The ownership gate is
			// intentionally gone — any signed-in visitor with the URL may
			// submit a turn.
			if (existing && (existing.status === 'queued' || existing.status === 'running')) {
				throw new AgentStreamError(409, 'previous_turn_in_flight');
			}

			const effectiveLimits = resolveLimits(userDoc, limitsConfig);
			isFirstMessage = !existing;
			// "Retry after refunded cancel" — when every prior turn was
			// cancelled, the daily counter was refunded on the cancellation.
			// Submitting again on the same session is the user picking the
			// chat back up; gate it against `chatsPerDay` just like a new chat
			// to close the bypass (refund → spend daily on chat B → come back
			// to chat A → second usable chat).
			const allPriorCancelled =
				!isFirstMessage &&
				(existing.lastTurnIndex || 0) > 0 &&
				(existing.cancelledTurns || 0) >= (existing.lastTurnIndex || 0);
			const treatAsChatCreation =
				isFirstMessage || (allPriorCancelled && existing.userId === submitterUid);
			if (treatAsChatCreation) {
				const chatCheck = checkChatLimit(userDoc, effectiveLimits, today);
				if (!chatCheck.allow) {
					const err = new AgentStreamError(429, chatCheck.code);
					if (chatCheck.resetAt) err.resetAt = chatCheck.resetAt;
					throw err;
				}
			}
			if (!isFirstMessage) {
				const turnCheck = checkTurnLimit(existing, effectiveLimits);
				if (!turnCheck.allow) {
					throw new AgentStreamError(429, turnCheck.code);
				}
			}
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
					cancelledTurns: 0,
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
				authorUid: submitterUid,
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

			// User-doc maintenance (lazy provision + chatsCreatedToday counter).
			// Counter ticks ONLY on session creation (chatsPerDay limit); follow-
			// ups never increment the daily counter.
			const dayRolled = userDoc?.lastChatDateUtc !== today;
			const currentCount = dayRolled ? 0 : userDoc?.chatsCreatedToday || 0;
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
					lastChatDateUtc: isFirstMessage ? today : null,
					chatsCreatedToday: isFirstMessage ? 1 : 0,
					createdAt: FieldValue.serverTimestamp(),
					updatedAt: FieldValue.serverTimestamp()
				});
			} else if (isFirstMessage) {
				const update = {
					lastChatDateUtc: today,
					chatsCreatedToday: currentCount + 1,
					updatedAt: FieldValue.serverTimestamp()
				};
				// Refresh identity fields opportunistically when present (Google
				// photo / display name changes).
				if (identity.email) update.email = identity.email;
				if (identity.displayName) update.displayName = identity.displayName;
				if (identity.photoURL) update.photoURL = identity.photoURL;
				t.update(userRef, update);
			} else if (treatAsChatCreation) {
				// Same-user retry of a previously-refunded chat — re-charge the
				// daily counter. The check above already gated this against
				// `chatsPerDay`, so we only need to record the spend here.
				t.update(userRef, {
					lastChatDateUtc: today,
					chatsCreatedToday: currentCount + 1,
					updatedAt: FieldValue.serverTimestamp()
				});
			}
		});
	} catch (err) {
		if (err instanceof AgentStreamError) {
			const body = { ok: false, error: err.code };
			if (err.resetAt) body.resetAt = err.resetAt;
			res.status(err.status).json(body);
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
				apiKey: googlePlacesKey.value()
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
			if (err instanceof RunOwnershipLost) {
				finishAfterRunOwnershipLost(res, sessionId, runId);
				return;
			}
			try {
				await assertRunStillCurrent(sessionRef, runId);
			} catch (ownershipErr) {
				if (ownershipErr instanceof RunOwnershipLost) {
					finishAfterRunOwnershipLost(res, sessionId, runId);
					return;
				}
				console.error('agentStream ownership check failed:', ownershipErr.message || ownershipErr);
				res.status(500).json({ ok: false, error: 'session_ownership_check_failed' });
				return;
			}
			console.warn('intake failed; falling back to Agent Engine:', err.message || err);
		}
	}

	// 6. Build the query text the pipeline receives. A fresh ADK working
	// session does not have prior hidden state, so any Firestore-visible
	// place/stopped-request context needed after rotation is injected into
	// the user-visible query text.
	const todayLabel = new Date(now).toLocaleDateString('en-US', {
		year: 'numeric',
		month: 'long',
		day: 'numeric'
	});
	let queryText = `[Date: ${todayLabel}] ${researchQuestion || message}`;
	if (createEngineSession && previousStoppedRequest) {
		queryText = `[Previous stopped request: ${compactForAgentState(previousStoppedRequest, 1000)}] ${queryText}`;
	}
	if (createEngineSession && placeContext && placeContext.name) {
		queryText = `${placeContextPrefix(placeContext)}${queryText}`;
	}
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
			message: queryText,
			isEngineFirstMessage: createEngineSession,
			createEngineSession,
			seedState
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
		if (err instanceof RunOwnershipLost) {
			finishAfterRunOwnershipLost(res, sessionId, runId);
			return;
		}
		try {
			await assertRunStillCurrent(sessionRef, runId);
		} catch (ownershipErr) {
			if (ownershipErr instanceof RunOwnershipLost) {
				finishAfterRunOwnershipLost(res, sessionId, runId);
				return;
			}
			console.error('agentStream ownership check failed:', ownershipErr.message || ownershipErr);
			res.status(500).json({ ok: false, error: 'session_ownership_check_failed' });
			return;
		}
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

// --- Agent cancel endpoint (participant stop for the active turn) ---

export const agentCancel = onRequest(
	{ cors: true, timeoutSeconds: 30, memory: '256MiB' },
	async (req, res) => {
		if (req.method !== 'POST') {
			res.status(405).json({ ok: false, error: 'Method not allowed' });
			return;
		}

		const authHeader = req.headers.authorization || '';
		const tokenMatch = /^Bearer\s+(.+)$/i.exec(authHeader);
		if (!tokenMatch) {
			res.status(401).json({ ok: false, error: 'Authorization header required' });
			return;
		}
		let uid;
		try {
			const decoded = await getAuth().verifyIdToken(tokenMatch[1]);
			if (decoded?.firebase?.sign_in_provider === 'anonymous') {
				res.status(401).json({ ok: false, error: 'AUTH_REQUIRED' });
				return;
			}
			uid = decoded.uid;
		} catch (e) {
			console.warn('agentCancel verifyIdToken rejected:', e.code || e.message);
			res.status(401).json({ ok: false, error: 'Invalid auth token' });
			return;
		}

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
		const today = todayUtc();
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

				// Cancellation refunds work that didn't produce a result. Two
				// counters are touched, both inside the transaction:
				//
				//   1. session.cancelledTurns +1 — the turn-limit check uses
				//      `lastTurnIndex - cancelledTurns` so retries reclaim the slot.
				//      `lastTurnIndex` itself stays put so the next turn writes to
				//      a fresh doc id and doesn't collide with the cancelled doc.
				//
				//   2. users/{creator}.chatsCreatedToday -1 when this cancel
				//      leaves the session with no productive turns — i.e.
				//      every turn so far is cancelled. Catches both:
				//        - First-turn cancel (`lastTurnIndex === 1`).
				//        - Cancel after a refund+retry sequence (where this
				//          turn was the re-charged retry that's now being
				//          cancelled too).
				//      Only refund if `lastChatDateUtc` still matches today
				//      (otherwise the day already rolled and the counter
				//      naturally resets).
				const creatorUid = typeof data.userId === 'string' ? data.userId : null;
				const cancelledTurnsAfter = (data.cancelledTurns || 0) + 1;
				const sessionFullyCancelledAfter =
					turnIdx === data.lastTurnIndex && cancelledTurnsAfter >= (data.lastTurnIndex || 0);
				const shouldRefundChat = sessionFullyCancelledAfter && creatorUid;
				let creatorRef = null;
				let creatorSnap = null;
				if (shouldRefundChat) {
					creatorRef = db.collection('users').doc(creatorUid);
					creatorSnap = await tx.get(creatorRef);
				}

				tx.update(sessionRef, {
					status: 'error',
					error: 'user_cancelled',
					currentRunId: FieldValue.delete(),
					activeAgent: FieldValue.delete(),
					activeStage: FieldValue.delete(),
					activeStageStartedAt: FieldValue.delete(),
					activeModel: FieldValue.delete(),
					activeInvocationId: FieldValue.delete(),
					cancelledTurns: FieldValue.increment(1),
					cancelledAt: FieldValue.serverTimestamp(),
					updatedAt: FieldValue.serverTimestamp()
				});
				tx.update(turnRef, {
					status: 'error',
					error: 'user_cancelled',
					completedAt: FieldValue.serverTimestamp(),
					cancelledAt: FieldValue.serverTimestamp()
				});

				if (shouldRefundChat && creatorSnap?.exists) {
					const creatorData = creatorSnap.data() || {};
					if (creatorData.lastChatDateUtc === today) {
						const next = Math.max(0, (creatorData.chatsCreatedToday || 0) - 1);
						tx.update(creatorRef, {
							chatsCreatedToday: next,
							updatedAt: FieldValue.serverTimestamp()
						});
					}
				}

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
		const authHeader = req.headers.authorization || '';
		const tokenMatch = /^Bearer\s+(.+)$/i.exec(authHeader);
		if (!tokenMatch) {
			res.status(401).json({ ok: false, error: 'Authorization header required' });
			return;
		}
		let uid;
		try {
			const decoded = await getAuth().verifyIdToken(tokenMatch[1]);
			if (decoded?.firebase?.sign_in_provider === 'anonymous') {
				res.status(401).json({ ok: false, error: 'AUTH_REQUIRED' });
				return;
			}
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

// --- Magic-link send endpoint (passwordless email sign-in) ---
//
// Wraps Firebase Admin's `generateSignInWithEmailLink` so the email body is
// our own branded template, delivered via Resend (same provider used for
// /api/intake). The Firebase default mailer would otherwise send from
// `noreply@<project>.firebaseapp.com` with a generic template.
//
// `returnTo` is an optional same-origin path the callback route honours after
// sign-in completes (used for shared-URL redirects).

const MAGIC_LINK_BASE_URL = process.env.MAGIC_LINK_BASE_URL || 'https://agent.superextra.ai/login';

function magicLinkEmailHtml(link) {
	return `<div style="font-family: -apple-system, system-ui, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 24px; color: #1a1a1a; line-height: 1.5;">
  <h1 style="font-size: 22px; margin: 0 0 8px; font-weight: 300;">Sign in to Superextra</h1>
  <p style="font-size: 15px; margin: 0 0 24px; color: #555;">Click the button below to sign in. The link expires in one hour.</p>
  <a href="${esc(link)}" style="display: inline-block; background: #000; color: #fff; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-size: 15px;">Sign in to Superextra</a>
  <p style="font-size: 13px; margin: 24px 0 0; color: #888;">If you didn’t request this, you can safely ignore this email.</p>
  <p style="font-size: 13px; margin: 8px 0 0; color: #888;">Or paste this link into your browser:<br><span style="color: #555; word-break: break-all;">${esc(link)}</span></p>
</div>`;
}

function magicLinkEmailText(link) {
	return `Sign in to Superextra\n\nClick this link to sign in. It expires in one hour:\n\n${link}\n\nIf you didn't request this, you can safely ignore this email.\n`;
}

function safeReturnTo(value) {
	if (typeof value !== 'string') return null;
	if (!value.startsWith('/')) return null;
	if (value.startsWith('//')) return null;
	if (value.length > 512) return null;
	return value;
}

export const sendMagicLink = onRequest(
	{ cors: true, timeoutSeconds: 30, memory: '256MiB', secrets: [relayKey] },
	async (req, res) => {
		if (req.method !== 'POST') {
			res.status(405).json({ ok: false, error: 'Method not allowed' });
			return;
		}

		const RELAY_KEY = relayKey.value();
		if (!RELAY_KEY) {
			console.error('RELAY_KEY env var is not set');
			res.status(500).json({ ok: false, error: 'Email service not configured' });
			return;
		}

		const ip = req.ip || req.headers['x-forwarded-for'] || 'unknown';
		if (!checkRateLimit(magicLinkRateLimitMap, ip, Date.now(), 10 * 60 * 1000, 10)) {
			res.status(429).json({ ok: false, error: 'Too many requests. Please wait a few minutes.' });
			return;
		}

		const { email, returnTo } = req.body || {};
		if (
			!email ||
			typeof email !== 'string' ||
			email.length > 320 ||
			!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
		) {
			res.status(400).json({ ok: false, error: 'Valid email is required' });
			return;
		}

		const sanitizedReturn = safeReturnTo(returnTo);
		const continueUrl = sanitizedReturn
			? `${MAGIC_LINK_BASE_URL}?returnTo=${encodeURIComponent(sanitizedReturn)}`
			: MAGIC_LINK_BASE_URL;

		let link;
		try {
			link = await getAuth().generateSignInWithEmailLink(email, {
				url: continueUrl,
				handleCodeInApp: true
			});
		} catch (err) {
			console.error('generateSignInWithEmailLink failed:', err.message || err);
			res.status(500).json({ ok: false, error: 'Magic link generation failed' });
			return;
		}

		// Rewrite the link so the click lands directly on our /login route,
		// skipping the `firebaseapp.com/__/auth/action` intermediate handler
		// (the white loading page that briefly appears before redirecting).
		// `isSignInWithEmailLink()` only checks for `mode=signIn` + `oobCode`
		// in the URL — host and path are not validated. We carry forward the
		// Firebase-supplied query params (mode, oobCode, apiKey, lang) onto
		// the continueUrl directly.
		try {
			const fbLink = new URL(link);
			const direct = new URL(continueUrl);
			for (const [k, v] of fbLink.searchParams) {
				if (k === 'continueUrl') continue;
				direct.searchParams.set(k, v);
			}
			link = direct.toString();
		} catch (err) {
			console.warn('magic link rewrite failed; falling back to default:', err.message || err);
		}

		try {
			const r = await fetch('https://api.resend.com/emails', {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${RELAY_KEY}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					from: 'Superextra <hello@superextra.ai>',
					to: email,
					subject: 'Sign in to Superextra',
					html: magicLinkEmailHtml(link),
					text: magicLinkEmailText(link)
				})
			});
			if (!r.ok) {
				const body = await r.text().catch(() => '');
				console.error('Resend magic link error:', r.status, body);
				res.status(502).json({ ok: false, error: 'Email send failed' });
				return;
			}
		} catch (err) {
			console.error('Resend magic link fetch failed:', err.message || err);
			res.status(503).json({ ok: false, error: 'Email service unreachable' });
			return;
		}

		res.json({ ok: true });
	}
);
