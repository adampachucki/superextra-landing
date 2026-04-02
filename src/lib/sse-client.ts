interface ChatSource {
	title: string;
	url: string;
}

export interface SSECallbacks {
	onProgress: (
		stage: string,
		status: string,
		label: string,
		previews?: Array<{ name: string; preview: string }>
	) => void;
	onToken: (text: string) => void;
	onComplete: (reply: string, sources: ChatSource[], title?: string) => void;
	onError: (error: string) => void;
}

/**
 * Stream agent responses via SSE from a POST endpoint.
 * Can't use EventSource (GET-only), so we use fetch + ReadableStream.
 */
export async function streamAgent(
	url: string,
	body: Record<string, unknown>,
	callbacks: SSECallbacks,
	signal?: AbortSignal
): Promise<void> {
	return streamAgentOnce(url, body, callbacks, signal, true);
}

async function streamAgentOnce(
	url: string,
	body: Record<string, unknown>,
	callbacks: SSECallbacks,
	signal: AbortSignal | undefined,
	canRetry: boolean
): Promise<void> {
	const t0 = Date.now();
	const log = (msg: string) =>
		console.log(`[sse +${((Date.now() - t0) / 1000).toFixed(1)}s] ${msg}`);

	log('fetch start');
	const res = await fetch(url, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body),
		signal
	});
	log(`fetch resolved: ${res.status}`);

	if (!res.ok) {
		const data = await res.json().catch(() => null);
		callbacks.onError(data?.error || 'Agent unavailable. Please try again.');
		return;
	}

	if (!res.body) {
		callbacks.onError('Streaming not supported.');
		return;
	}

	const reader = res.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';
	let currentEvent = '';
	let currentData = '';
	let completed = false;
	let receivedAnyEvent = false;
	const startTime = Date.now();
	let chunkCount = 0;

	// Inactivity timeout — reset on any data or keepalive
	let inactivityTimer: ReturnType<typeof setTimeout> | null = null;
	const INACTIVITY_MS = 90_000;

	function resetInactivity() {
		if (inactivityTimer) clearTimeout(inactivityTimer);
		inactivityTimer = setTimeout(() => {
			if (!completed) {
				callbacks.onError('Connection timed out. Please try again.');
				reader.cancel();
			}
		}, INACTIVITY_MS);
	}

	resetInactivity();

	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) {
				log(
					`stream done after ${chunkCount} chunks, completed=${completed}, events=${receivedAnyEvent}`
				);
				break;
			}

			chunkCount++;
			if (chunkCount <= 3) log(`chunk #${chunkCount}: ${value.byteLength}B`);
			resetInactivity();
			buffer += decoder.decode(value, { stream: true });

			// Process complete lines from the buffer
			let newlineIdx: number;
			while ((newlineIdx = buffer.indexOf('\n')) !== -1) {
				const line = buffer.slice(0, newlineIdx);
				buffer = buffer.slice(newlineIdx + 1);

				if (line === '') {
					// Empty line = end of SSE event
					if (currentData) {
						receivedAnyEvent = true;
						dispatchEvent(currentEvent, currentData, callbacks);
						if (currentEvent === 'complete' || currentEvent === 'error') {
							completed = true;
						}
					}
					currentEvent = '';
					currentData = '';
				} else if (line.startsWith('event: ')) {
					currentEvent = line.slice(7);
				} else if (line.startsWith('data: ')) {
					currentData = line.slice(6);
				}
				// Comment lines (: keepalive) — inactivity already reset above
			}
		}

		// Handle any remaining buffered event
		if (currentData && !completed) {
			receivedAnyEvent = true;
			dispatchEvent(currentEvent, currentData, callbacks);
			if (currentEvent === 'complete' || currentEvent === 'error') {
				completed = true;
			}
		}

		if (!completed) {
			const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
			log(
				`stream closed incomplete: elapsed=${elapsed}s, events=${receivedAnyEvent}, chunks=${chunkCount}`
			);
			// Stream closed with zero events within 5s — transient infra failure, retry once
			if (canRetry && !receivedAnyEvent && Date.now() - startTime < 5_000) {
				log('retrying (early close with no events)');
				return streamAgentOnce(url, body, callbacks, signal, false);
			}
			callbacks.onError('Connection closed before response completed.');
		}
	} catch (err) {
		const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
		log(`error at +${elapsed}s: ${err instanceof Error ? err.message : err}`);
		throw err;
	} finally {
		if (inactivityTimer) clearTimeout(inactivityTimer);
	}
}

function dispatchEvent(event: string, data: string, callbacks: SSECallbacks) {
	try {
		const parsed = JSON.parse(data);
		switch (event) {
			case 'progress':
				callbacks.onProgress(parsed.stage, parsed.status, parsed.label, parsed.previews);
				break;
			case 'token':
				callbacks.onToken(parsed.text);
				break;
			case 'complete':
				callbacks.onComplete(parsed.reply, parsed.sources || [], parsed.title);
				break;
			case 'error':
				callbacks.onError(parsed.error || 'Unknown error');
				break;
		}
	} catch {
		// Skip malformed events
	}
}
