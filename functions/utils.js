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
	return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function row(label, value, raw = false) {
	return `<tr>
		<td style="padding:6px 12px 6px 0;color:#888;font-size:13px;white-space:nowrap">${esc(label)}</td>
		<td style="padding:6px 0;font-size:13px">${raw ? value : esc(value)}</td>
	</tr>`;
}

export function confirmationHtml(name) {
	const firstName = esc(name.split(' ')[0] || 'there');
	return `<div style="font-family:sans-serif;max-width:520px;color:#1a1a1a;font-size:14px;line-height:1.6">
<p>Hey ${firstName},</p>
<p>I'm Adam, co-founder of Superextra.</p>
<p>Thanks for requesting a Superextra demo.</p>
<p>This is an automated confirmation. I'll follow up personally with scheduling details soon.</p>
<p>In the meantime, it would help to know:</p>
<ol>
<li>What business decision should the demo focus on?</li>
<li>Which locations, formats, or competitors should we understand?</li>
<li>Which pricing, guest, delivery, or expansion signals would be most useful?</li>
</ol>
<p>Just hit reply and let me know.</p>
<p>Best,<br>Adam</p>
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
