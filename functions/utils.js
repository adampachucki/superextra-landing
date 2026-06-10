// Pure utility functions extracted from index.js for testability.

// --- Input validation ---

/**
 * Validate and sanitize placeContext from request body.
 * Returns a sanitized object or null if invalid/missing.
 */
export function validatePlaceContext(pc) {
	if (!pc || typeof pc !== 'object' || Array.isArray(pc)) return null;
	const name = typeof pc.name === 'string' ? pc.name.slice(0, 100) : '';
	if (!name) return null;
	return {
		name,
		placeId: typeof pc.placeId === 'string' ? pc.placeId.slice(0, 100) : '',
		secondary: typeof pc.secondary === 'string' ? pc.secondary.slice(0, 200) : ''
	};
}

// --- HTML helpers (email templates) ---

export function esc(s) {
	return String(s)
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;');
}

export function row(label, value, raw = false) {
	return `<tr>
		<td style="padding:6px 12px 6px 0;color:#888;font-size:13px;white-space:nowrap">${esc(label)}</td>
		<td style="padding:6px 0;font-size:13px">${raw ? value : esc(value)}</td>
	</tr>`;
}

// Per-locale copy for the personal confirmation email. The internal demo
// notification (to the team) stays English and is not localized.
const CONFIRMATION_COPY = {
	en: {
		subject: 'Superextra demo request received',
		fallbackName: 'there',
		greeting: (n) => `Hey ${n},`,
		intro: "I'm Adam, co-founder of Superextra.",
		thanks: 'Thanks for requesting a Superextra demo.',
		auto: "This is an automated confirmation. I'll follow up personally with scheduling details soon.",
		ask: 'In the meantime, it would help to know:',
		q1: 'What business decision should the demo focus on?',
		q2: 'Which locations, formats, or competitors should we understand?',
		q3: 'Which pricing, guest, delivery, or expansion signals would be most useful?',
		reply: 'Just hit reply and let me know.',
		sign: 'Best,<br>Adam'
	},
	de: {
		subject: 'Superextra Demo-Anfrage erhalten',
		fallbackName: 'zusammen',
		greeting: (n) => `Hallo ${n},`,
		intro: 'ich bin Adam, Mitgründer von Superextra.',
		thanks: 'Danke für deine Anfrage einer Superextra-Demo.',
		auto: 'Das ist eine automatische Bestätigung. Ich melde mich persönlich mit Terminvorschlägen.',
		ask: 'Bis dahin hilft es zu wissen:',
		q1: 'Auf welche Geschäftsentscheidung soll sich die Demo konzentrieren?',
		q2: 'Welche Standorte, Formate oder Wettbewerber sollten wir verstehen?',
		q3: 'Welche Signale zu Preisen, Gästen, Lieferung oder Expansion wären am nützlichsten?',
		reply: 'Antworte einfach auf diese E-Mail.',
		sign: 'Beste Grüße,<br>Adam'
	},
	pl: {
		subject: 'Prośba o demo Superextra otrzymana',
		fallbackName: 'Tam',
		greeting: (n) => `Cześć ${n},`,
		intro: 'nazywam się Adam, jestem współzałożycielem Superextra.',
		thanks: 'Dziękujemy za prośbę o demo Superextra.',
		auto: 'To automatyczne potwierdzenie. Wkrótce odezwę się osobiście z propozycjami terminów.',
		ask: 'W międzyczasie pomocne będzie:',
		q1: 'Na jakiej decyzji biznesowej ma się skupić demo?',
		q2: 'Jakie lokalizacje, formaty lub konkurentów powinniśmy zrozumieć?',
		q3: 'Które sygnały o cenach, gościach, dostawach lub ekspansji byłyby najbardziej przydatne?',
		reply: 'Po prostu odpisz na tę wiadomość.',
		sign: 'Pozdrawiam,<br>Adam'
	}
};

function confirmationLocale(value) {
	return Object.hasOwn(CONFIRMATION_COPY, value) ? value : 'en';
}

export function confirmationSubject(locale) {
	return CONFIRMATION_COPY[confirmationLocale(locale)].subject;
}

export function confirmationHtml(name, locale = 'en') {
	const t = CONFIRMATION_COPY[confirmationLocale(locale)];
	const firstName = esc(name.split(' ')[0] || t.fallbackName);
	return `<div style="font-family:sans-serif;max-width:520px;color:#1a1a1a;font-size:14px;line-height:1.6">
<p>${t.greeting(firstName)}</p>
<p>${t.intro}</p>
<p>${t.thanks}</p>
<p>${t.auto}</p>
<p>${t.ask}</p>
<ol>
<li>${t.q1}</li>
<li>${t.q2}</li>
<li>${t.q3}</li>
</ol>
<p>${t.reply}</p>
<p>${t.sign}</p>
</div>`;
}

// --- Markdown helper (kept for shared rendering paths) ---

export function stripMarkdown(text) {
	return text
		.replace(/^#{1,6}\s+/gm, '') // headings
		.replace(/\*\*(.+?)\*\*/g, '$1') // bold
		.replace(/\*(.+?)\*/g, '$1') // italic
		.replace(/~~(.+?)~~/g, '$1') // strikethrough
		.replace(/`{1,3}[^`]*`{1,3}/g, '') // inline/block code
		.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // links → text only
		.replace(/^[-*+]\s+/gm, '') // unordered list markers
		.replace(/^\d+\.\s+/gm, '') // ordered list markers
		.replace(/^>\s+/gm, '') // blockquotes
		.replace(/\n{3,}/g, '\n\n') // collapse excess newlines
		.trim();
}

// --- Rate limiting ---

/**
 * Check and update rate limit for an IP.
 * @returns {boolean} true if request is allowed, false if rate limited
 */
export function checkRateLimit(map, ip, now, windowMs, maxRequests) {
	const entry = map.get(ip);
	if (entry && now - entry.start < windowMs) {
		if (entry.count >= maxRequests) return false;
		entry.count++;
	} else {
		map.set(ip, { start: now, count: 1 });
	}
	return true;
}
