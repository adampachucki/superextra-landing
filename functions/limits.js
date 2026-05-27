// Pure limit-resolution helpers + a tiny config cache.
// No hidden Firestore reads inside helpers — fetch `config/limits` via
// `getLimitsConfig(db)` once before opening any transaction; pass the
// resolved config into the pure helpers.

const LIMITS_CACHE_TTL_MS = 60 * 1000;

const DEFAULT_LIMITS = {
	free: { chatsPerDay: 1, turnsPerChat: 1 },
	paid: { chatsPerDay: 50, turnsPerChat: 20 }
};

let cachedConfig = null;
let cachedAt = 0;

export async function getLimitsConfig(db) {
	const now = Date.now();
	if (cachedConfig && now - cachedAt < LIMITS_CACHE_TTL_MS) return cachedConfig;
	// Fail-closed on read errors — silently defaulting to DEFAULT_LIMITS
	// would bypass any tighter caps an operator set. Missing config doc IS
	// a normal case (e.g. fresh project) and we fall back to defaults.
	const snap = await db.collection('config').doc('limits').get();
	const raw = snap.exists ? snap.data() || {} : {};
	cachedConfig = {
		free: { ...DEFAULT_LIMITS.free, ...(raw.free || {}) },
		paid: { ...DEFAULT_LIMITS.paid, ...(raw.paid || {}) }
	};
	cachedAt = now;
	return cachedConfig;
}

function sanitizeLimit(value, fallback) {
	// `config/limits` is editable from Firebase Console — bad values (strings,
	// negatives, NaN) must not bypass the gate by making comparisons fail open.
	// Clamp to the plan default when the input isn't a non-negative integer.
	if (typeof value === 'number' && Number.isInteger(value) && value >= 0) return value;
	return fallback;
}

export function resolveLimits(user, config) {
	const plan = user?.plan === 'paid' ? 'paid' : 'free';
	const baseRaw = (config && config[plan]) || DEFAULT_LIMITS[plan];
	const defaults = DEFAULT_LIMITS[plan];
	const base = {
		chatsPerDay: sanitizeLimit(baseRaw.chatsPerDay, defaults.chatsPerDay),
		turnsPerChat: sanitizeLimit(baseRaw.turnsPerChat, defaults.turnsPerChat)
	};
	const overrides = (user && user.limitOverrides) || {};
	return {
		chatsPerDay: sanitizeLimit(overrides.chatsPerDay, base.chatsPerDay),
		turnsPerChat: sanitizeLimit(overrides.turnsPerChat, base.turnsPerChat)
	};
}

export function todayUtc(now = new Date()) {
	return now.toISOString().slice(0, 10);
}

export function nextUtcMidnightIso(now = new Date()) {
	const d = new Date(now);
	d.setUTCHours(24, 0, 0, 0);
	return d.toISOString();
}

export function checkChatLimit(user, limits, today) {
	const isToday = user?.lastChatDateUtc === today;
	const usedToday = isToday ? user?.chatsCreatedToday || 0 : 0;
	if (usedToday >= limits.chatsPerDay) {
		return { allow: false, code: 'CHAT_LIMIT_REACHED', resetAt: nextUtcMidnightIso() };
	}
	return { allow: true };
}

export function checkTurnLimit(session, limits) {
	const lastTurnIndex = session?.lastTurnIndex || 0;
	const cancelledTurns = session?.cancelledTurns || 0;
	const effective = Math.max(0, lastTurnIndex - cancelledTurns);
	if (effective >= limits.turnsPerChat) {
		return { allow: false, code: 'TURN_LIMIT_REACHED' };
	}
	return { allow: true };
}

// Test-only — bypass the cache so tests can stub the config doc cleanly.
export function _resetLimitsCache() {
	cachedConfig = null;
	cachedAt = 0;
}

export { DEFAULT_LIMITS };
