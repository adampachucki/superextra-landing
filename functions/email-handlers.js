// Email endpoints: `intake` (demo-request relay + confirmation via Resend)
// and `sendMagicLink` (branded passwordless sign-in email).
import { onRequest } from 'firebase-functions/v2/https';
import { defineSecret } from 'firebase-functions/params';
import { getAuth } from 'firebase-admin/auth';
import './firebase.js';
import { checkRateLimit, confirmationHtml, confirmationSubject, esc, row } from './utils.js';

const relayKey = defineSecret('RELAY_KEY');
const DEST = 'hello@superextra.ai';

const magicLinkRateLimitMap = new Map();

// Test-only — bypass abuse limits so each test starts from a clean slate.
export function _resetRateLimits() {
	magicLinkRateLimitMap.clear();
}

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
				subject: confirmationSubject(data.locale),
				html: confirmationHtml(data.fullName, data.locale)
			})
		});
	} catch (err) {
		console.error('Confirmation email failed:', err);
	}

	res.json({ ok: true });
});

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

const MAGIC_LINK_COPY = {
	en: {
		subject: 'Sign in to Superextra',
		heading: 'Sign in to Superextra',
		body: 'Click the button below to sign in. The link expires in one hour.',
		button: 'Sign in to Superextra',
		ignore: 'If you didn’t request this, you can safely ignore this email.',
		paste: 'Or paste this link into your browser:',
		textBody: 'Click this link to sign in. It expires in one hour:'
	},
	de: {
		subject: 'Bei Superextra anmelden',
		heading: 'Bei Superextra anmelden',
		body: 'Klicke auf den Button unten, um dich anzumelden. Der Link läuft in einer Stunde ab.',
		button: 'Bei Superextra anmelden',
		ignore: 'Wenn du das nicht angefordert hast, kannst du diese E-Mail ignorieren.',
		paste: 'Oder füge diesen Link in deinen Browser ein:',
		textBody: 'Klicke auf diesen Link, um dich anzumelden. Er läuft in einer Stunde ab:'
	},
	pl: {
		subject: 'Zaloguj się do Superextra',
		heading: 'Zaloguj się do Superextra',
		body: 'Kliknij przycisk poniżej, aby się zalogować. Link wygasa za godzinę.',
		button: 'Zaloguj się do Superextra',
		ignore: 'Jeśli to nie Ty, możesz zignorować tę wiadomość.',
		paste: 'Lub wklej ten link do przeglądarki:',
		textBody: 'Kliknij ten link, aby się zalogować. Wygasa za godzinę:'
	}
};

function magicLinkLocale(value) {
	return Object.hasOwn(MAGIC_LINK_COPY, value) ? value : 'en';
}

function magicLinkEmailHtml(link, locale = 'en') {
	const t = MAGIC_LINK_COPY[magicLinkLocale(locale)];
	return `<div style="font-family: -apple-system, system-ui, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 24px; color: #1a1a1a; line-height: 1.5;">
  <h1 style="font-size: 22px; margin: 0 0 8px; font-weight: 300;">${t.heading}</h1>
  <p style="font-size: 15px; margin: 0 0 24px; color: #555;">${t.body}</p>
  <a href="${esc(link)}" style="display: inline-block; background: #000; color: #fff; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-size: 15px;">${t.button}</a>
  <p style="font-size: 13px; margin: 24px 0 0; color: #888;">${t.ignore}</p>
  <p style="font-size: 13px; margin: 24px 0 0; color: #888;">${t.paste}<br><span style="color: #555; word-break: break-all;">${esc(link)}</span></p>
</div>`;
}

function magicLinkEmailText(link, locale = 'en') {
	const t = MAGIC_LINK_COPY[magicLinkLocale(locale)];
	return `${t.heading}\n\n${t.textBody}\n\n${link}\n\n${t.ignore}\n`;
}

function magicLinkSubject(locale) {
	return MAGIC_LINK_COPY[magicLinkLocale(locale)].subject;
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
		const locale = magicLinkLocale(req.body?.locale);
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
					subject: magicLinkSubject(locale),
					html: magicLinkEmailHtml(link, locale),
					text: magicLinkEmailText(link, locale)
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
