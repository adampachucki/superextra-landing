/**
 * iOS Safari SSE-resume helper.
 *
 * iOS Safari fully suspends the WebContent process when the tab is
 * backgrounded, killing TCP connections
 * (webkit.org/blog/8970/how-web-content-can-get-unloaded/). When the
 * tab returns, the pending reader.read() rejects or resolves with
 * done=true — the SSE stream is dead and the last user message never
 * got its reply.
 *
 * Desktop browsers keep connections alive during brief tab switches,
 * so we only abort + recover if the tab was hidden long enough for
 * the connection to be dead (>30s, i.e. two missed server keepalives
 * at 15s intervals).
 *
 * Caller owns all chat-store state; they pass callbacks.
 */

export interface IosVisibilityContext {
	isLoading(): boolean;
	setLoading(v: boolean): void;
	abortStream(): void;
	recover(): void;
	/** True if the last message is from the user (i.e. an agent reply is pending). */
	hasPendingUserMessage(): boolean;
	/** Null if no active session — caller skips the whole flow. */
	getSessionId(): string | null;
}

export interface IosVisibilityOptions {
	/** Minimum hidden duration that justifies abort + recover. Default 30_000. */
	hiddenThresholdMs?: number;
	/** Poll interval while waiting for send()'s finally to clear loading. Default 100. */
	pollIntervalMs?: number;
	/** Safety timeout after which we force loading=false and recover anyway. Default 2000. */
	safetyTimeoutMs?: number;
	/** Delay before recovery when stream already ended (iOS 18 networking stack). Default 300. */
	postEndDelayMs?: number;
}

export interface IosVisibilityHandle {
	/** Clear any pending poll/timeout (e.g. on session change or unmount). */
	cancel(): void;
}

/**
 * Respond to a visibilitychange → visible event after the tab was
 * hidden for `hiddenMs` milliseconds. Returns a handle that lets the
 * caller cancel any scheduled poll/timeout before it fires.
 */
export function handleReturnFromHidden(
	ctx: IosVisibilityContext,
	hiddenMs: number,
	opts: IosVisibilityOptions = {}
): IosVisibilityHandle {
	const hiddenThresholdMs = opts.hiddenThresholdMs ?? 30_000;
	const pollIntervalMs = opts.pollIntervalMs ?? 100;
	const safetyTimeoutMs = opts.safetyTimeoutMs ?? 2000;
	const postEndDelayMs = opts.postEndDelayMs ?? 300;

	let poll: ReturnType<typeof setInterval> | null = null;
	let timeout: ReturnType<typeof setTimeout> | null = null;

	function cancel() {
		if (poll) {
			clearInterval(poll);
			poll = null;
		}
		if (timeout) {
			clearTimeout(timeout);
			timeout = null;
		}
	}

	if (!ctx.getSessionId()) return { cancel };
	if (!ctx.hasPendingUserMessage()) return { cancel };

	if (ctx.isLoading()) {
		// Hidden briefly — stream likely still alive.
		if (hiddenMs < hiddenThresholdMs) return { cancel };

		// Stream was in-flight when the tab was backgrounded — connection is dead.
		ctx.abortStream();
		// Poll until send()'s finally block clears loading, then recover.
		// A fixed delay isn't enough — iOS process resumption can be slow.
		poll = setInterval(() => {
			if (!ctx.isLoading()) {
				cancel();
				ctx.recover();
			}
		}, pollIntervalMs);
		// Safety: if loading never clears, force it and recover anyway.
		timeout = setTimeout(() => {
			cancel();
			if (ctx.isLoading()) ctx.setLoading(false);
			ctx.recover();
		}, safetyTimeoutMs);
	} else {
		// Stream already ended (with error or silently) — try to recover the response.
		// Delay for iOS 18 networking stack reinitialization (WebKit Bug 284946).
		timeout = setTimeout(() => {
			timeout = null;
			ctx.recover();
		}, postEndDelayMs);
	}

	return { cancel };
}
