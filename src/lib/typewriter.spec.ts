import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createTypewriter } from './typewriter';

let frames: Map<number, FrameRequestCallback>;
let nextFrameId: number;

function runNextFrame() {
	const [id, callback] = frames.entries().next().value as [number, FrameRequestCallback];
	frames.delete(id);
	callback(0);
}

describe('createTypewriter', () => {
	beforeEach(() => {
		frames = new Map();
		nextFrameId = 1;
		vi.stubGlobal(
			'requestAnimationFrame',
			vi.fn((callback: FrameRequestCallback) => {
				const id = nextFrameId++;
				frames.set(id, callback);
				return id;
			})
		);
		vi.stubGlobal(
			'cancelAnimationFrame',
			vi.fn((id: number) => {
				frames.delete(id);
			})
		);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('reveals text in fixed-size frame chunks and calls onDone once', () => {
		const updates: string[] = [];
		const onDone = vi.fn();
		const typer = createTypewriter({
			charsPerFrame: 3,
			onUpdate: (text) => updates.push(text),
			onDone
		});

		typer.setTarget('abcdefg');
		expect(updates).toEqual([]);

		runNextFrame();
		runNextFrame();
		runNextFrame();

		expect(updates).toEqual(['abc', 'abcdef', 'abcdefg']);
		expect(onDone).toHaveBeenCalledTimes(1);
		expect(frames.size).toBe(0);
	});

	it('stop cancels pending work', () => {
		const updates: string[] = [];
		const typer = createTypewriter({
			onUpdate: (text) => updates.push(text)
		});

		typer.setTarget('abcdefg');
		expect(frames.size).toBe(1);

		typer.stop();

		expect(updates).toEqual([]);
		expect(frames.size).toBe(0);
	});
});
