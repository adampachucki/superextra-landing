import { RELAY_KEY } from '$env/static/private';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

const DEST = 'hello@superextra.ai';

export const POST: RequestHandler = async ({ request }) => {
	const data = await request.json();

	const html = `
		<div style="font-family:sans-serif;max-width:520px">
			<h2 style="margin:0 0 16px">New access request</h2>
			<table style="border-collapse:collapse;width:100%">
				${row('Category', data.type)}
				${row('Country', data.country)}
				${row('Name', data.businessName)}
				${data.locations ? row('Locations', data.locations) : ''}
				${data.webUrl ? row('URL', data.webUrl) : ''}
				${row('Contact', data.fullName)}
				${row('Email', data.email)}
				${data.phone ? row('Phone', data.phone) : ''}
			</table>
		</div>
	`;

	const res = await fetch('https://api.resend.com/emails', {
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

	if (!res.ok) {
		return json({ ok: false }, { status: 500 });
	}

	return json({ ok: true });
};

function row(label: string, value: string) {
	return `<tr>
		<td style="padding:6px 12px 6px 0;color:#888;font-size:13px;white-space:nowrap">${label}</td>
		<td style="padding:6px 0;font-size:13px">${esc(value)}</td>
	</tr>`;
}

function esc(s: string) {
	return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
