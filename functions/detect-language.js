import { generateGeminiJson } from './gemini-json.js';

// Locales we ship UI label translations for. Detection may return any
// ISO-639-1 code (the agent answers in it), but frontend label localization
// falls back to English for anything outside this set.
export const SUPPORTED_LOCALES = ['en', 'de', 'pl'];

const LANGUAGE_SCHEMA = {
	type: 'OBJECT',
	properties: { language: { type: 'STRING' } },
	required: ['language']
};

/** Coerce a model/UI value to a clean ISO-639-1 code, or null. */
function normalizeCode(value) {
	if (typeof value !== 'string') return null;
	const raw = value.trim().toLowerCase();
	if (!raw || raw === 'und' || raw === 'unknown') return null;
	const code = raw.slice(0, 2);
	return /^[a-z]{2}$/.test(code) ? code : null;
}

/**
 * Detect the primary ISO-639-1 language of `message`. Best-effort and
 * fail-open: returns `fallback` (then 'en') on any error, empty input, or an
 * undetermined result, so language detection never blocks a run.
 *
 * Detection runs on the raw user message — NOT the agentStream query text,
 * which carries an English `[Date: …]` / place-context prefix that would bias
 * the result toward English.
 */
const DETECT_TIMEOUT_MS = 4000;

export async function detectLanguage({
	message,
	fallback = 'en',
	generate = generateGeminiJson,
	timeoutMs = DETECT_TIMEOUT_MS
}) {
	const fb = normalizeCode(fallback) || 'en';
	const text = String(message || '').trim();
	if (!text) return fb;
	// Fail open on a hung call as well as a thrown one: detection sits on the
	// agentStream hot path before the session transaction and must not stall the
	// run. `generateGeminiJson` has no abort, so bound it with a race.
	let timer;
	try {
		const timeout = new Promise((resolve) => {
			timer = setTimeout(() => resolve(null), timeoutMs);
		});
		const result = await Promise.race([
			generate({
				prompt: [
					'Identify the primary natural language of the user message below.',
					'Reply with ONLY its ISO 639-1 two-letter code in lowercase (e.g. en, de, pl, fr, es).',
					"If the message is only a name, number, URL, or symbols with no clear language, reply with 'und'.",
					'',
					`Message: ${JSON.stringify(text.slice(0, 600))}`
				].join('\n'),
				responseSchema: LANGUAGE_SCHEMA,
				maxOutputTokens: 16,
				errorName: 'detect_language'
			}),
			timeout
		]);
		return normalizeCode(result?.language) || fb;
	} catch {
		return fb;
	} finally {
		clearTimeout(timer);
	}
}
