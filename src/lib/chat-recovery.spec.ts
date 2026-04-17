import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { recoverStream, type RecoveryContext } from './chat-recovery';

function makeCtx(overrides: Partial<RecoveryContext> = {}): {
	ctx: RecoveryContext;
	calls: { reply: Array<[string, unknown]>; error: string[] };
} {
	const calls = { reply: [] as Array<[string, unknown]>, error: [] as string[] };
	const ctx: RecoveryContext = {
		getSessionId: () => 'sid-1',
		isCurrentSession: () => true,
		onReply: (reply, sources) => calls.reply.push([reply, sources]),
		onError: (msg) => calls.error.push(msg),
		checkUrl: (sid) => `https://example.test/check?sid=${sid}`,
		...overrides
	};
	return { ctx, calls };
}

beforeEach(() => {
	vi.useFakeTimers();
});

afterEach(() => {
	vi.useRealTimers();
	vi.restoreAllMocks();
});

describe('recoverStream', () => {
	it('delivers reply on first poll and returns true', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => ({
				json: async () => ({ ok: true, reply: 'Hello', sources: [{ url: 'u', title: 't' }] })
			}))
		);
		const { ctx, calls } = makeCtx();
		const result = await recoverStream(ctx);
		expect(result).toBe(true);
		expect(calls.reply).toEqual([['Hello', [{ url: 'u', title: 't' }]]]);
	});

	it('treats session_not_found as terminal failure', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => ({
				json: async () => ({ ok: false, reason: 'session_not_found' })
			}))
		);
		const { ctx, calls } = makeCtx();
		const result = await recoverStream(ctx);
		expect(result).toBe(false);
		expect(calls.error[0]).toMatch(/Session not found/);
	});

	it('treats agent_unavailable as terminal failure', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => ({
				json: async () => ({ ok: false, reason: 'agent_unavailable' })
			}))
		);
		const { ctx, calls } = makeCtx();
		const result = await recoverStream(ctx);
		expect(result).toBe(false);
		expect(calls.error[0]).toMatch(/Agent unavailable/);
	});

	it('polls while status is still-processing, then delivers reply', async () => {
		let call = 0;
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => {
				call++;
				if (call < 3) return { json: async () => ({ ok: true }) }; // still processing
				return { json: async () => ({ ok: true, reply: 'Done' }) };
			})
		);
		const { ctx, calls } = makeCtx();
		const p = recoverStream(ctx, { intervalMs: 100 });
		// Let polling loop run: advance timers + flush microtasks repeatedly
		for (let i = 0; i < 6; i++) {
			await vi.advanceTimersByTimeAsync(200);
		}
		const result = await p;
		expect(result).toBe(true);
		expect(call).toBeGreaterThanOrEqual(3);
		expect(calls.reply).toEqual([['Done', undefined]]);
	});

	it('returns false without calling onReply/onError when session changes', async () => {
		let current = 'sid-1';
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => ({ json: async () => ({ ok: true }) }))
		);
		const { ctx, calls } = makeCtx({
			isCurrentSession: (sid) => sid === current
		});
		const p = recoverStream(ctx, { intervalMs: 50 });
		await vi.advanceTimersByTimeAsync(60);
		current = 'sid-2'; // user switched conversations
		await vi.advanceTimersByTimeAsync(500);
		const result = await p;
		expect(result).toBe(false);
		expect(calls.reply).toEqual([]);
		expect(calls.error).toEqual([]);
	});

	it('skips onReply when isDuplicateReply returns true', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => ({
				json: async () => ({ ok: true, reply: 'already-delivered' })
			}))
		);
		const { ctx, calls } = makeCtx({
			isDuplicateReply: () => true
		});
		const result = await recoverStream(ctx);
		expect(result).toBe(true);
		expect(calls.reply).toEqual([]);
	});

	it('exhausts maxAttempts with generic error when no terminal reason', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => ({ json: async () => ({ ok: true }) })) // never has reply
		);
		const { ctx, calls } = makeCtx();
		const p = recoverStream(ctx, { maxAttempts: 3, intervalMs: 10 });
		await vi.advanceTimersByTimeAsync(100);
		const result = await p;
		expect(result).toBe(false);
		expect(calls.error[0]).toMatch(/Could not retrieve/);
	});

	it('breaks loop on fetch throw with generic error', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => {
				throw new Error('network');
			})
		);
		const { ctx, calls } = makeCtx();
		const result = await recoverStream(ctx);
		expect(result).toBe(false);
		expect(calls.error[0]).toMatch(/Could not retrieve/);
	});
});
