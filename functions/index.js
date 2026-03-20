import { onRequest } from 'firebase-functions/v2/https';
import { defineSecret } from 'firebase-functions/params';

const relayKey = defineSecret('RELAY_KEY');
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

function row(label, value, raw = false) {
	return `<tr>
		<td style="padding:6px 12px 6px 0;color:#888;font-size:13px;white-space:nowrap">${esc(label)}</td>
		<td style="padding:6px 0;font-size:13px">${raw ? value : esc(value)}</td>
	</tr>`;
}

function esc(s) {
	return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function confirmationHtml(name) {
	const firstName = esc(name.split(' ')[0] || 'there');
	return `<div style="font-family:sans-serif;max-width:520px;color:#1a1a1a;font-size:14px;line-height:1.6">
<p>Hey ${firstName},</p>
<p>I'm Adam, co-founder of Superextra.</p>
<p>We believe the restaurant industry deserves better access to reliable information, and we're building Superextra to make that happen.</p>
<p>This is an automated message, but I'll follow up personally soon.</p>
<p>In the meantime, it would help to know:</p>
<ol>
<li>What challenges can we help you solve?</li>
<li>What information would make the biggest difference?</li>
<li>How did you find us?</li>
</ol>
<p>Just hit reply and let me know.</p>
<p>Best,<br>Adam</p>
</div>`;
}
