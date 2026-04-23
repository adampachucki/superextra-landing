import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createTypewriter } from './typewriter';

describe('createTypewriter', () => {
	let rafQueue: Array<FrameRequestCallback | null> = [];

	function flushRaf() {
		while (rafQueue.some((cb) => cb !== null)) {
			const frame = rafQueue;
			rafQueue = [];
			for (const cb of frame) {
				cb?.(0);
			}
		}
	}

	beforeEach(() => {
		rafQueue = [];
		vi.stubGlobal(
			'requestAnimationFrame',
			vi.fn((cb: FrameRequestCallback) => {
				rafQueue.push(cb);
				return rafQueue.length;
			})
		);
		vi.stubGlobal(
			'cancelAnimationFrame',
			vi.fn((id: number) => {
				const index = id - 1;
				if (index >= 0 && index < rafQueue.length) {
					rafQueue[index] = null;
				}
			})
		);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('calls onDone after draining the target text', () => {
		const updates: string[] = [];
		const done = vi.fn();
		const typer = createTypewriter({
			onUpdate: (value) => {
				updates.push(value);
			},
			onDone: done,
			charsPerFrame: 2
		});

		typer.setTarget('hello');
		flushRaf();

		expect(updates.at(-1)).toBe('hello');
		expect(done).toHaveBeenCalledTimes(1);
	});
});
