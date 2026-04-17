/**
 * Agent-session recovery polling.
 *
 * When an SSE stream drops (user backgrounded the tab on iOS, network
 * flap, etc.), the agent continues running on the server. This polls
 * the `agentCheck` endpoint until it returns a reply, a terminal
 * failure, or we exceed MAX_ATTEMPTS.
 *
 * Caller owns all state mutations — they pass callbacks (onReply,
 * onError, onComplete) that touch the chat store. The polling loop
 * itself is pure timing + fetch.
 */

export interface ChatSource {
	title: string;
	url: string;
	domain?: string;
}

export interface RecoveryContext {
	/** Return the session id the caller expects to recover. */
	getSessionId(): string | null;
	/** Return false if the user switched conversations mid-poll — terminates cleanly. */
	isCurrentSession(sessionId: string): boolean;
	/** Called once per successful recovery with the delivered reply. */
	onReply(reply: string, sources: ChatSource[] | undefined): void;
	/** Called once on terminal failure with a user-facing error string. */
	onError(message: string): void;
	/** Build the check-endpoint URL for a session. Varies by dev/prod. */
	checkUrl(sessionId: string): string;
	/**
	 * Inspect a received reply to decide whether it's already in the
	 * chat history (SSE delivered it before the poll) — if so, skip onReply.
	 */
	isDuplicateReply?(reply: string): boolean;
}

export interface RecoveryOptions {
	/** Default 60. */
	maxAttempts?: number;
	/** Default 3000. */
	intervalMs?: number;
	/** Per-request abort timeout. Default 10_000. */
	fetchTimeoutMs?: number;
}

const TERMINAL_REASONS: Record<string, string> = {
	session_not_found: 'Session not found. Please start a new conversation.',
	agent_unavailable: 'Agent unavailable. Please try again.',
	timed_out: 'The request timed out. Please try again.'
};

/**
 * Poll the recovery endpoint until we get a reply, a terminal failure,
 * or exceed MAX_ATTEMPTS. Returns true iff a reply was delivered via
 * onReply. Cancellation: if isCurrentSession() ever returns false, the
 * loop exits without calling onReply or onError.
 */
export async function recoverStream(
	ctx: RecoveryContext,
	opts: RecoveryOptions = {}
): Promise<boolean> {
	const maxAttempts = opts.maxAttempts ?? 60;
	const intervalMs = opts.intervalMs ?? 3000;
	const fetchTimeoutMs = opts.fetchTimeoutMs ?? 10_000;

	const sessionId = ctx.getSessionId();
	if (!sessionId) return false;

	const url = ctx.checkUrl(sessionId);

	for (let attempt = 0; attempt < maxAttempts; attempt++) {
		if (!ctx.isCurrentSession(sessionId)) return false;
		try {
			const res = await fetch(url, { signal: AbortSignal.timeout(fetchTimeoutMs) });
			const data = await res.json();

			if (!data.ok && data.reason && TERMINAL_REASONS[data.reason]) {
				ctx.onError(TERMINAL_REASONS[data.reason]);
				return false;
			}

			if (data.ok && data.reply) {
				if (!ctx.isDuplicateReply?.(data.reply)) {
					const sources: ChatSource[] | undefined = data.sources?.length ? data.sources : undefined;
					ctx.onReply(data.reply, sources);
				}
				return true;
			}

			if (attempt < maxAttempts - 1) {
				await new Promise((r) => setTimeout(r, intervalMs));
			}
		} catch {
			break;
		}
	}

	ctx.onError('Could not retrieve the response. Please try again.');
	return false;
}
