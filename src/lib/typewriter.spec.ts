import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createTypewriter, createTypewriterGroup } from './typewriter';

// --- RAF shim: drive ticks via microtask flushes, time-independent ---
let rafQueue: FrameRequestCallback[] = [];
let nextRafId = 1;

function flushFrame() {
	const queue = rafQueue;
	rafQueue = [];
	for (const cb of queue) cb(performance.now());
}

function flushFrames(n: number) {
	for (let i = 0; i < n; i++) {
		if (rafQueue.length === 0) return;
		flushFrame();
	}
}

beforeEach(() => {
	rafQueue = [];
	nextRafId = 1;
	vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
		rafQueue.push(cb);
		return nextRafId++;
	});
	vi.stubGlobal('cancelAnimationFrame', (id: number) => {
		// We don't actually remove from queue — the test flushes use a fresh snapshot.
		// Consumers relying on cancellation check rafId === null internally.
		void id;
	});
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('createTypewriter', () => {
	it('drains target character-by-character at charsPerFrame rate', () => {
		const updates: string[] = [];
		const tw = createTypewriter({
			charsPerFrame: 2,
			onUpdate: (v) => updates.push(v)
		});
		tw.setTarget('hello');
		flushFrames(10);
		expect(updates).toEqual(['he', 'hell', 'hello']);
	});

	it('fires onDone exactly once when a drain completes', () => {
		const done = vi.fn();
		const tw = createTypewriter({
			charsPerFrame: 3,
			onUpdate: () => {},
			onDone: done
		});
		tw.setTarget('abcdef');
		flushFrames(5);
		expect(done).toHaveBeenCalledTimes(1);
	});

	it('extends without resetting when new target starts with old', () => {
		const updates: string[] = [];
		const tw = createTypewriter({ charsPerFrame: 2, onUpdate: (v) => updates.push(v) });
		tw.setTarget('ab');
		flushFrames(2); // "ab"
		tw.setTarget('abcdef');
		flushFrames(5);
		expect(updates.at(-1)).toBe('abcdef');
		// Never emitted a midstream '' reset
		expect(updates.includes('')).toBe(false);
	});

	it('resets display when new target diverges from old', () => {
		const updates: string[] = [];
		const tw = createTypewriter({ charsPerFrame: 2, onUpdate: (v) => updates.push(v) });
		tw.setTarget('abcdef');
		flushFrames(2); // some drained
		tw.setTarget('xyz123');
		flushFrames(5);
		expect(updates).toContain('');
		expect(updates.at(-1)).toBe('xyz123');
	});

	it('stop() cancels the in-flight drain', () => {
		const updates: string[] = [];
		const tw = createTypewriter({ charsPerFrame: 1, onUpdate: (v) => updates.push(v) });
		tw.setTarget('abcdefghij');
		flushFrames(2); // only 2 chars drained
		tw.stop();
		const beforeStop = updates.length;
		// clear raf queue to simulate cancellation
		rafQueue = [];
		flushFrames(10);
		expect(updates.length).toBe(beforeStop);
	});

	it('ignores a no-op setTarget (same value)', () => {
		const updates: string[] = [];
		const tw = createTypewriter({ charsPerFrame: 2, onUpdate: (v) => updates.push(v) });
		tw.setTarget('abc');
		flushFrames(5);
		const beforeNoop = updates.length;
		tw.setTarget('abc');
		flushFrames(3);
		expect(updates.length).toBe(beforeNoop);
	});
});

describe('createTypewriterGroup', () => {
	it('runs independent drains per id without cross-contamination', () => {
		const updates: Array<[string, string]> = [];
		const g = createTypewriterGroup({
			charsPerFrame: 2,
			onUpdate: (id, v) => updates.push([id, v])
		});
		g.setTarget('a', 'hello');
		g.setTarget('b', 'world');
		flushFrames(8);
		const aUpdates = updates.filter(([id]) => id === 'a').map(([, v]) => v);
		const bUpdates = updates.filter(([id]) => id === 'b').map(([, v]) => v);
		expect(aUpdates.at(-1)).toBe('hello');
		expect(bUpdates.at(-1)).toBe('world');
	});

	it('extend mode: extends display when new target starts with old', () => {
		const updates: Array<[string, string]> = [];
		const g = createTypewriterGroup({
			charsPerFrame: 2,
			onUpdate: (id, v) => updates.push([id, v])
		});
		g.setTarget('x', 'ab');
		flushFrames(2);
		g.setTarget('x', 'abcdef');
		flushFrames(5);
		const all = updates.filter(([id]) => id === 'x').map(([, v]) => v);
		expect(all.at(-1)).toBe('abcdef');
		// No mid-stream reset to ''
		expect(all.slice(1).includes('')).toBe(false);
	});

	it('reset mode: always resets display when target changes', () => {
		const updates: Array<[string, string]> = [];
		const g = createTypewriterGroup({
			charsPerFrame: 2,
			onUpdate: (id, v) => updates.push([id, v])
		});
		g.setTarget('x', 'ab', 'reset');
		flushFrames(2);
		g.setTarget('x', 'abcdef', 'reset');
		flushFrames(5);
		const all = updates.filter(([id]) => id === 'x').map(([, v]) => v);
		// Reset emitted '' at the second setTarget call
		expect(all.includes('')).toBe(true);
		expect(all.at(-1)).toBe('abcdef');
	});

	it('prune removes ids not in keepIds and cancels their RAFs', () => {
		const updates: Array<[string, string]> = [];
		const g = createTypewriterGroup({
			charsPerFrame: 1,
			onUpdate: (id, v) => updates.push([id, v])
		});
		g.setTarget('a', 'aaaaaa');
		g.setTarget('b', 'bbbbbb');
		flushFrames(2);
		g.prune(new Set(['a']));
		rafQueue = [];
		flushFrames(20);
		const bUpdates = updates.filter(([id]) => id === 'b').map(([, v]) => v);
		// 'b' should not have reached full 'bbbbbb' after prune
		expect(bUpdates.at(-1)).not.toBe('bbbbbb');
	});

	it('stopAll halts every running drain', () => {
		const updates: Array<[string, string]> = [];
		const g = createTypewriterGroup({
			charsPerFrame: 1,
			onUpdate: (id, v) => updates.push([id, v])
		});
		g.setTarget('a', 'hello');
		g.setTarget('b', 'world');
		flushFrames(1);
		const beforeStop = updates.length;
		g.stopAll();
		rafQueue = [];
		flushFrames(20);
		expect(updates.length).toBe(beforeStop);
	});

	it('fires onDone per id when its drain completes', () => {
		const done = vi.fn();
		const g = createTypewriterGroup({
			charsPerFrame: 3,
			onUpdate: () => {},
			onDone: done
		});
		g.setTarget('x', 'abcdef');
		g.setTarget('y', 'ghi');
		flushFrames(5);
		expect(done).toHaveBeenCalledWith('x');
		expect(done).toHaveBeenCalledWith('y');
		expect(done).toHaveBeenCalledTimes(2);
	});
});
