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
 * Detect the ISO-639-1 language the user is writing in. Judges only ordinary
 * prose and ignores proper nouns, so a place/venue name does not register as a
 * language. Returns `null` when undetermined (only a place name, etc.), empty,
 * or on any error — the caller resolves the fallback (established chat language,
 * then UI locale). Best-effort and fail-open so detection never blocks a run.
 *
 * Runs on the raw user message — NOT the agentStream query text, which carries
 * an English `[Date: …]` / place-context prefix that would bias the result.
 */
const DETECT_TIMEOUT_MS = 4000;

export async function detectLanguage({
	message,
	generate = generateGeminiJson,
	timeoutMs = DETECT_TIMEOUT_MS
}) {
	const text = String(message || '').trim();
	if (!text) return null;
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
					'Determine the language the user is WRITING IN, judging only ordinary words',
					'(verbs, pronouns, articles, connectors, everyday nouns).',
					'IGNORE proper nouns — place names, neighborhoods, cities, streets, addresses,',
					'brand and venue names. A location the user mentions is NOT evidence of the',
					'language they write in (e.g. "openings near Garnizon in Gdańsk" is English).',
					'Reply with ONLY the ISO 639-1 two-letter code in lowercase (e.g. en, de, pl, fr).',
					'If there is no ordinary prose to judge — only a place/proper name, a number, an',
					"address, or symbols — reply with 'und'.",
					'',
					`Message: ${JSON.stringify(text.slice(0, 600))}`
				].join('\n'),
				responseSchema: LANGUAGE_SCHEMA,
				maxOutputTokens: 16,
				errorName: 'detect_language'
			}),
			timeout
		]);
		return normalizeCode(result?.language);
	} catch {
		return null;
	} finally {
		clearTimeout(timer);
	}
}
