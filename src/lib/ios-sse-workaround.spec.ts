import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { handleReturnFromHidden, type IosVisibilityContext } from './ios-sse-workaround';

function makeCtx(overrides: Partial<IosVisibilityContext> = {}): {
	ctx: IosVisibilityContext;
	calls: { abortStream: number; recover: number; setLoading: boolean[] };
	state: { loading: boolean };
} {
	const state = { loading: true };
	const calls = { abortStream: 0, recover: 0, setLoading: [] as boolean[] };
	const ctx: IosVisibilityContext = {
		isLoading: () => state.loading,
		setLoading: (v) => {
			state.loading = v;
			calls.setLoading.push(v);
		},
		abortStream: () => calls.abortStream++,
		recover: () => calls.recover++,
		hasPendingUserMessage: () => true,
		getSessionId: () => 'sid-1',
		...overrides
	};
	return { ctx, calls, state };
}

beforeEach(() => {
	vi.useFakeTimers();
});

afterEach(() => {
	vi.useRealTimers();
});

describe('handleReturnFromHidden', () => {
	it('no-ops when no session', () => {
		const { ctx, calls } = makeCtx({ getSessionId: () => null });
		handleReturnFromHidden(ctx, 60_000);
		expect(calls.abortStream).toBe(0);
		expect(calls.recover).toBe(0);
	});

	it('no-ops when no pending user message', () => {
		const { ctx, calls } = makeCtx({ hasPendingUserMessage: () => false });
		handleReturnFromHidden(ctx, 60_000);
		expect(calls.abortStream).toBe(0);
		expect(calls.recover).toBe(0);
	});

	it('no-ops when hidden briefly while loading (below threshold)', () => {
		const { ctx, calls } = makeCtx();
		handleReturnFromHidden(ctx, 5_000);
		expect(calls.abortStream).toBe(0);
		expect(calls.recover).toBe(0);
	});

	it('aborts + polls + recovers when loading past threshold', () => {
		const { ctx, calls, state } = makeCtx();
		handleReturnFromHidden(ctx, 45_000, { pollIntervalMs: 50, safetyTimeoutMs: 2000 });
		expect(calls.abortStream).toBe(1);
		expect(calls.recover).toBe(0);
		// Simulate send()'s finally clearing loading
		state.loading = false;
		vi.advanceTimersByTime(60);
		expect(calls.recover).toBe(1);
	});

	it('safety timeout forces loading=false and recovers when poll never fires', () => {
		const { ctx, calls } = makeCtx();
		handleReturnFromHidden(ctx, 45_000, { pollIntervalMs: 100, safetyTimeoutMs: 200 });
		// Don't clear loading. Let safety timeout fire.
		vi.advanceTimersByTime(250);
		expect(calls.setLoading).toContain(false);
		expect(calls.recover).toBe(1);
	});

	it('schedules post-end recover when not loading', () => {
		const { ctx, calls } = makeCtx({ isLoading: () => false });
		handleReturnFromHidden(ctx, 60_000, { postEndDelayMs: 100 });
		expect(calls.recover).toBe(0);
		vi.advanceTimersByTime(150);
		expect(calls.recover).toBe(1);
	});

	it('cancel() prevents recover from firing', () => {
		const { ctx, calls } = makeCtx({ isLoading: () => false });
		const handle = handleReturnFromHidden(ctx, 60_000, { postEndDelayMs: 100 });
		handle.cancel();
		vi.advanceTimersByTime(150);
		expect(calls.recover).toBe(0);
	});
});
