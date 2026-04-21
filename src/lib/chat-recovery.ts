/**
 * Agent-session recovery polling — last-resort REST fallback when
 * Firestore's `onSnapshot` can't reach us (ad-blockers on
 * `firestore.googleapis.com`, corporate proxies blocking WebSocket
 * channels, rare auth edge cases).
 *
 * `chat-state` triggers this only on:
 *   - `onSnapshot` PERMISSION_DENIED error, OR
 *   - no first snapshot arriving within 10 s of subscribing.
 *
 * Caller owns all state mutations — they pass callbacks (onReply,
 * onError) that touch the chat store. The polling loop itself is
 * pure timing + fetch.
 */

export interface ChatSource {
	title: string;
	url: string;
	domain?: string;
}

export interface RecoveryContext {
	/** Return the (sessionId, runId) pair to recover, or null when there's
	 *  nothing to recover (e.g. the conversation has no in-flight turn).
	 *  The `runId` makes agentCheck scoped to the exact turn we're waiting
	 *  on — stale `runId`s resolve via agentCheck's own ownership logic. */
	getSession(): { sessionId: string; runId: string } | null;
	/** Return false if the user switched conversations mid-poll. */
	isCurrentSession(sessionId: string): boolean;
	/** Called once per successful recovery with the delivered reply. */
	onReply(reply: string, sources: ChatSource[] | undefined): void;
	/** Called once on terminal failure with a user-facing error string. */
	onError(message: string): void;
	/** Build the check-endpoint URL for a (sessionId, runId) pair. */
	checkUrl(sessionId: string, runId: string): string;
	/** Bearer ID token for agentCheck; resolves to null if we can't obtain
	 *  a token (no authenticated user). */
	getIdToken?(): Promise<string | null>;
	/**
	 * Inspect a received reply to decide whether it's already in the
	 * chat history — if so, skip onReply. Useful when the Firestore
	 * stream delivered the reply between subscribe-timeout and poll.
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
	timed_out: 'The request timed out. Please try again.',
	ownership_mismatch: 'This conversation belongs to a different session.',
	pipeline_error: 'The pipeline encountered an error.'
};

/**
 * Poll the recovery endpoint until we get a reply, a terminal failure,
 * or exceed maxAttempts. Returns true iff a reply was delivered via
 * onReply. Cancellation: if isCurrentSession() returns false, the loop
 * exits without calling onReply or onError.
 */
export async function recoverStream(
	ctx: RecoveryContext,
	opts: RecoveryOptions = {}
): Promise<boolean> {
	const maxAttempts = opts.maxAttempts ?? 60;
	const intervalMs = opts.intervalMs ?? 3000;
	const fetchTimeoutMs = opts.fetchTimeoutMs ?? 10_000;

	const session = ctx.getSession();
	if (!session) return false;
	const { sessionId, runId } = session;

	const url = ctx.checkUrl(sessionId, runId);

	for (let attempt = 0; attempt < maxAttempts; attempt++) {
		if (!ctx.isCurrentSession(sessionId)) return false;
		try {
			const idToken = ctx.getIdToken ? await ctx.getIdToken() : null;
			const headers: Record<string, string> = {};
			if (idToken) headers.Authorization = `Bearer ${idToken}`;
			const res = await fetch(url, {
				headers,
				signal: AbortSignal.timeout(fetchTimeoutMs)
			});
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
