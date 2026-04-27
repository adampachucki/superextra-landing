/**
 * Round-2 R2.7 — Node-side recipe for calling Agent Runtime :streamQuery.
 *
 * Verifies that Cloud Functions Node 22 can: (a) get a service-account
 * bearer token via google-auth-library, (b) POST to :streamQuery?alt=sse,
 * (c) parse the SSE response, (d) detect terminal events.
 *
 * Run from this directory:
 *   node probe-stream-query.js <resource-name> <user-id> <session-id> "<message>"
 *
 * Resource names from agent/probe/deployed_resources.json.
 */

import { GoogleAuth } from 'google-auth-library';

const PROJECT = 'superextra-site';
const LOCATION = 'us-central1';

async function getToken() {
	const auth = new GoogleAuth({
		scopes: ['https://www.googleapis.com/auth/cloud-platform']
	});
	const client = await auth.getClient();
	const { token } = await client.getAccessToken();
	if (!token) throw new Error('failed to get access token');
	return token;
}

async function main() {
	const [, , resourceName, userId, sessionId, ...msgParts] = process.argv;
	if (!resourceName || !userId || !sessionId) {
		console.error(
			'usage: node probe-stream-query.js <resource-name> <user-id> <session-id> "<message>"'
		);
		process.exit(2);
	}
	const message = msgParts.join(' ') || 'go';
	const token = await getToken();
	const url = `https://${LOCATION}-aiplatform.googleapis.com/v1/${resourceName}:streamQuery?alt=sse`;

	console.log(`[node-probe] POST ${url}`);
	const t0 = Date.now();
	const res = await fetch(url, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${token}`,
			'Content-Type': 'application/json',
			Accept: 'text/event-stream'
		},
		body: JSON.stringify({
			class_method: 'async_stream_query',
			input: { user_id: userId, session_id: sessionId, message }
		})
	});

	console.log(`[node-probe] status=${res.status} (in ${Date.now() - t0}ms)`);
	if (!res.ok) {
		const body = await res.text();
		console.error(`[node-probe] body: ${body.slice(0, 1000)}`);
		process.exit(1);
	}
	if (!res.body) {
		console.error('[node-probe] no response body');
		process.exit(1);
	}

	// Empirical finding 2026-04-26: Vertex AI :streamQuery returns
	// newline-delimited JSON (NDJSON), NOT standard SSE `data: ...\n\n`
	// frames, even with `?alt=sse`. Parse line-by-line as raw JSON.
	const reader = res.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';
	let eventCount = 0;
	while (true) {
		const { value, done } = await reader.read();
		if (done) break;
		buffer += decoder.decode(value, { stream: true });
		const lines = buffer.split('\n');
		buffer = lines.pop() ?? '';
		for (const line of lines) {
			const trimmed = line.trim();
			if (!trimmed) continue;
			eventCount++;
			try {
				const ev = JSON.parse(trimmed);
				const author = ev.author ?? '?';
				const parts = ev.content?.parts ?? [];
				const partKinds = parts.map((p) =>
					p.function_call ? 'fc' : p.function_response ? 'fr' : p.text != null ? 'text' : '?'
				);
				const firstText = parts[0]?.text?.slice(0, 80) ?? '';
				console.log(
					`[node-probe] event ${eventCount} (+${Date.now() - t0}ms) author=${author} parts=[${partKinds.join(',')}] text=${JSON.stringify(firstText)}`
				);
			} catch (e) {
				console.log(
					`[node-probe] event ${eventCount} (raw, parse failed): ${trimmed.slice(0, 200)}`
				);
			}
		}
	}
	if (buffer.trim()) {
		// Trailing fragment without newline — try to parse it too
		try {
			const ev = JSON.parse(buffer.trim());
			eventCount++;
			console.log(`[node-probe] event ${eventCount} (trailing) author=${ev.author ?? '?'}`);
		} catch {
			// Trailing fragment isn't valid JSON — drop it silently.
		}
	}
	console.log(
		`[node-probe] stream closed; total events=${eventCount} elapsed=${Date.now() - t0}ms`
	);
}

main().catch((e) => {
	console.error('[node-probe] FAILED:', e);
	process.exit(1);
});
