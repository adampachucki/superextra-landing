import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createTypewriter } from './typewriter';

describe('createTypewriter', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('reveals text in soft word-sized chunks and calls onDone once', () => {
		const updates: string[] = [];
		const onDone = vi.fn();
		const typer = createTypewriter({
			charsPerFrame: 3,
			onUpdate: (text) => updates.push(text),
			onDone
		});

		typer.setTarget('abcdefg');
		expect(updates).toEqual([]);

		vi.advanceTimersByTime(35);

		expect(updates).toEqual(['abcdefg']);
		expect(onDone).toHaveBeenCalledTimes(1);
	});

	it('prefers word boundaries over hard character cuts', () => {
		const updates: string[] = [];
		const typer = createTypewriter({
			charsPerFrame: 2,
			onUpdate: (text) => updates.push(text)
		});

		typer.setTarget('alpha beta gamma delta');
		vi.advanceTimersByTime(35);
		vi.advanceTimersByTime(35);

		expect(updates).toEqual(['alpha beta ', 'alpha beta gamma delta']);
	});

	it('stop cancels pending work', () => {
		const updates: string[] = [];
		const typer = createTypewriter({
			onUpdate: (text) => updates.push(text)
		});

		typer.setTarget('abcdefg');

		typer.stop();
		vi.advanceTimersByTime(35);

		expect(updates).toEqual([]);
	});
});
