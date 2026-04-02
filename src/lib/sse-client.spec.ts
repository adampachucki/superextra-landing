import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { streamAgent, type SSECallbacks } from './sse-client';

const TEST_URL = 'https://test.example.com/stream';

function sseStream(events: Array<{ event: string; data: unknown }>) {
	const encoder = new TextEncoder();
	return new ReadableStream({
		start(controller) {
			for (const e of events) {
				controller.enqueue(
					encoder.encode(`event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)
				);
			}
			controller.close();
		}
	});
}

function makeCallbacks(): SSECallbacks & {
	calls: Array<{ method: string; args: unknown[] }>;
} {
	const calls: Array<{ method: string; args: unknown[] }> = [];
	return {
		calls,
		onProgress: vi.fn((...args: unknown[]) => calls.push({ method: 'onProgress', args })),
		onToken: vi.fn((...args: unknown[]) => calls.push({ method: 'onToken', args })),
		onComplete: vi.fn((...args: unknown[]) => calls.push({ method: 'onComplete', args })),
		onError: vi.fn((...args: unknown[]) => calls.push({ method: 'onError', args }))
	};
}

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('streamAgent', () => {
	it('happy path: progress -> token -> complete fires callbacks in order', async () => {
		const sources = [{ title: 'Src', url: 'https://example.com' }];
		server.use(
			http.post(TEST_URL, () => {
				return new HttpResponse(
					sseStream([
						{
							event: 'progress',
							data: {
								stage: 'research',
								status: 'running',
								label: 'Analyzing...',
								previews: [{ name: 'p1', preview: 'text' }]
							}
						},
						{ event: 'token', data: { text: 'Hello' } },
						{ event: 'token', data: { text: ' world' } },
						{
							event: 'complete',
							data: { reply: 'Hello world', sources, title: 'My Title' }
						}
					]),
					{ headers: { 'Content-Type': 'text/event-stream' } }
				);
			})
		);

		const cb = makeCallbacks();
		await streamAgent(TEST_URL, { message: 'hi' }, cb);

		expect(cb.calls).toHaveLength(4);
		expect(cb.calls[0].method).toBe('onProgress');
		expect(cb.onProgress).toHaveBeenCalledWith('research', 'running', 'Analyzing...', [
			{ name: 'p1', preview: 'text' }
		]);
		expect(cb.calls[1].method).toBe('onToken');
		expect(cb.calls[2].method).toBe('onToken');
		expect(cb.onToken).toHaveBeenCalledWith('Hello');
		expect(cb.onToken).toHaveBeenCalledWith(' world');
		expect(cb.calls[3].method).toBe('onComplete');
		expect(cb.onComplete).toHaveBeenCalledWith('Hello world', sources, 'My Title');
		expect(cb.onError).not.toHaveBeenCalled();
	});

	it('error event calls onError with message', async () => {
		server.use(
			http.post(TEST_URL, () => {
				return new HttpResponse(
					sseStream([{ event: 'error', data: { error: 'Something went wrong' } }]),
					{ headers: { 'Content-Type': 'text/event-stream' } }
				);
			})
		);

		const cb = makeCallbacks();
		await streamAgent(TEST_URL, { message: 'hi' }, cb);

		expect(cb.onError).toHaveBeenCalledWith('Something went wrong');
		expect(cb.onComplete).not.toHaveBeenCalled();
	});

	it('HTTP 500 calls onError with default message', async () => {
		server.use(
			http.post(TEST_URL, () => {
				return new HttpResponse('Internal Server Error', { status: 500 });
			})
		);

		const cb = makeCallbacks();
		await streamAgent(TEST_URL, { message: 'hi' }, cb);

		expect(cb.onError).toHaveBeenCalledWith('Agent unavailable. Please try again.');
	});

	it('HTTP 500 with JSON body uses custom error message', async () => {
		server.use(
			http.post(TEST_URL, () => {
				return HttpResponse.json({ error: 'custom error' }, { status: 500 });
			})
		);

		const cb = makeCallbacks();
		await streamAgent(TEST_URL, { message: 'hi' }, cb);

		expect(cb.onError).toHaveBeenCalledWith('custom error');
	});

	it('no response body calls onError with streaming not supported', async () => {
		const originalFetch = globalThis.fetch;
		globalThis.fetch = vi.fn().mockResolvedValue({
			ok: true,
			body: null,
			status: 200,
			json: () => Promise.resolve(null)
		});

		try {
			const cb = makeCallbacks();
			await streamAgent(TEST_URL, { message: 'hi' }, cb);

			expect(cb.onError).toHaveBeenCalledWith('Streaming not supported.');
		} finally {
			globalThis.fetch = originalFetch;
		}
	});

	it('malformed JSON in non-complete event logs warning, no crash', async () => {
		const encoder = new TextEncoder();
		const stream = new ReadableStream({
			start(controller) {
				controller.enqueue(encoder.encode('event: token\ndata: {broken json\n\n'));
				controller.enqueue(
					encoder.encode(
						`event: complete\ndata: ${JSON.stringify({ reply: 'ok', sources: [] })}\n\n`
					)
				);
				controller.close();
			}
		});

		server.use(
			http.post(TEST_URL, () => {
				return new HttpResponse(stream, {
					headers: { 'Content-Type': 'text/event-stream' }
				});
			})
		);

		const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
		const cb = makeCallbacks();
		await streamAgent(TEST_URL, { message: 'hi' }, cb);

		expect(warnSpy).toHaveBeenCalled();
		expect(cb.onError).not.toHaveBeenCalled();
		expect(cb.onComplete).toHaveBeenCalledWith('ok', [], undefined);

		warnSpy.mockRestore();
	});

	it('malformed JSON in complete event calls onError', async () => {
		const encoder = new TextEncoder();
		const stream = new ReadableStream({
			start(controller) {
				controller.enqueue(encoder.encode('event: complete\ndata: {not valid\n\n'));
				controller.close();
			}
		});

		server.use(
			http.post(TEST_URL, () => {
				return new HttpResponse(stream, {
					headers: { 'Content-Type': 'text/event-stream' }
				});
			})
		);

		vi.spyOn(console, 'warn').mockImplementation(() => {});
		const cb = makeCallbacks();
		await streamAgent(TEST_URL, { message: 'hi' }, cb);

		expect(cb.onError).toHaveBeenCalledWith('Received malformed response. Please try again.');

		vi.restoreAllMocks();
	});

	it('empty stream closes in <5s retries once (fetch called twice)', async () => {
		let fetchCount = 0;

		server.use(
			http.post(TEST_URL, () => {
				fetchCount++;
				// Return an empty stream that closes immediately
				const stream = new ReadableStream({
					start(controller) {
						controller.close();
					}
				});
				return new HttpResponse(stream, {
					headers: { 'Content-Type': 'text/event-stream' }
				});
			})
		);

		const cb = makeCallbacks();
		await streamAgent(TEST_URL, { message: 'hi' }, cb);

		// First attempt: empty, fast close -> retries
		// Second attempt: empty, fast close -> gives up with error
		expect(fetchCount).toBe(2);
		expect(cb.onError).toHaveBeenCalledWith('Connection closed before response completed.');
	});

	it('empty stream on retry calls onError, exactly 2 fetch calls', async () => {
		let fetchCount = 0;

		server.use(
			http.post(TEST_URL, () => {
				fetchCount++;
				return new HttpResponse(
					new ReadableStream({
						start(controller) {
							controller.close();
						}
					}),
					{ headers: { 'Content-Type': 'text/event-stream' } }
				);
			})
		);

		const cb = makeCallbacks();
		await streamAgent(TEST_URL, { message: 'hi' }, cb);

		expect(fetchCount).toBe(2);
		expect(cb.onError).toHaveBeenCalledOnce();
		expect(cb.onError).toHaveBeenCalledWith('Connection closed before response completed.');
	});

	it('stream closes after receiving events: no retry, 1 fetch call', async () => {
		let fetchCount = 0;

		server.use(
			http.post(TEST_URL, () => {
				fetchCount++;
				return new HttpResponse(sseStream([{ event: 'token', data: { text: 'partial' } }]), {
					headers: { 'Content-Type': 'text/event-stream' }
				});
			})
		);

		const cb = makeCallbacks();
		await streamAgent(TEST_URL, { message: 'hi' }, cb);

		expect(fetchCount).toBe(1);
		expect(cb.onToken).toHaveBeenCalledWith('partial');
		expect(cb.onError).toHaveBeenCalledWith('Connection closed before response completed.');
	});

	it('inactivity timeout fires onError after 90s', async () => {
		vi.useFakeTimers();

		// We need a stream where reader.read() returns a pending promise that
		// never resolves on its own, but reader.cancel() makes it resolve { done: true }.
		// A ReadableStream with an empty start() does exactly this.
		const neverEndingStream = new ReadableStream({
			start() {
				// Don't enqueue or close — stream stays open, read() will pend
			}
		});

		server.use(
			http.post(TEST_URL, () => {
				return new HttpResponse(neverEndingStream, {
					headers: { 'Content-Type': 'text/event-stream' }
				});
			})
		);

		const cb = makeCallbacks();

		// Start the stream — it will hang on reader.read()
		const promise = streamAgent(TEST_URL, { message: 'hi' }, cb);

		// Flush microtasks so the async function proceeds through fetch to reader.read()
		await vi.advanceTimersByTimeAsync(100);

		// Advance past the 90s inactivity timeout
		await vi.advanceTimersByTimeAsync(90_000);

		// The timeout callback fires onError and calls reader.cancel(),
		// which resolves the pending read() with { done: true }.
		// Flush microtasks so the while loop exits and the function completes.
		await vi.advanceTimersByTimeAsync(100);

		await promise;

		// The timeout error is the one we care about
		expect(cb.onError).toHaveBeenCalledWith('Connection timed out. Please try again.');

		vi.useRealTimers();
	});

	it('AbortSignal aborted causes clean exit, no error callback', async () => {
		const abortController = new AbortController();

		// Abort before calling streamAgent so fetch rejects immediately with AbortError
		abortController.abort();

		// We still need a handler registered so MSW doesn't complain about unhandled requests,
		// but fetch will reject before MSW processes it. Use a passthrough-like handler.
		server.use(
			http.post(TEST_URL, () => {
				return new HttpResponse(sseStream([]), {
					headers: { 'Content-Type': 'text/event-stream' }
				});
			})
		);

		const cb = makeCallbacks();

		// streamAgent re-throws the AbortError from fetch
		await expect(
			streamAgent(TEST_URL, { message: 'hi' }, cb, abortController.signal)
		).rejects.toThrow();

		// The key assertion: onError should NOT be called for user-initiated abort
		expect(cb.onError).not.toHaveBeenCalled();
	});

	it('chunked SSE data split across multiple ReadableStream chunks reassembles correctly', async () => {
		const encoder = new TextEncoder();
		const fullEvent = `event: complete\ndata: ${JSON.stringify({ reply: 'assembled', sources: [{ title: 'S', url: 'https://s.com' }], title: 'T' })}\n\n`;

		// Split the event at arbitrary points across 3 chunks
		const chunk1 = fullEvent.slice(0, 15);
		const chunk2 = fullEvent.slice(15, 40);
		const chunk3 = fullEvent.slice(40);

		const stream = new ReadableStream({
			start(controller) {
				controller.enqueue(encoder.encode(chunk1));
				controller.enqueue(encoder.encode(chunk2));
				controller.enqueue(encoder.encode(chunk3));
				controller.close();
			}
		});

		server.use(
			http.post(TEST_URL, () => {
				return new HttpResponse(stream, {
					headers: { 'Content-Type': 'text/event-stream' }
				});
			})
		);

		const cb = makeCallbacks();
		await streamAgent(TEST_URL, { message: 'hi' }, cb);

		expect(cb.onComplete).toHaveBeenCalledWith(
			'assembled',
			[{ title: 'S', url: 'https://s.com' }],
			'T'
		);
		expect(cb.onError).not.toHaveBeenCalled();
	});
});
