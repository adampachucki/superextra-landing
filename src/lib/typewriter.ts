/**
 * RAF-based text drain utility.
 *
 * Emits a callback with progressively longer prefixes of `target`, one frame
 * at a time. Used by ChatThread to render the agent reply with a fake-typing
 * effect after the worker emits the drafting timeline event.
 */

interface SharedOptions {
	/** Characters drained per animation frame. Default: 2. */
	charsPerFrame?: number;
}

export interface Typewriter {
	setTarget(target: string): void;
	stop(): void;
	reset(): void;
}

export interface TypewriterOptions extends SharedOptions {
	onUpdate: (current: string) => void;
	onDone?: () => void;
}

export function createTypewriter(opts: TypewriterOptions): Typewriter {
	const rate = opts.charsPerFrame ?? 2;
	let current = '';
	let target = '';
	let rafId: number | null = null;
	let draining = false;

	function tick() {
		if (current.length < target.length) {
			current = target.slice(0, current.length + rate);
			opts.onUpdate(current);
			rafId = requestAnimationFrame(tick);
		} else {
			rafId = null;
			if (draining) {
				draining = false;
				opts.onDone?.();
			}
		}
	}

	function start() {
		if (rafId === null && current.length < target.length) {
			draining = true;
			rafId = requestAnimationFrame(tick);
		}
	}

	function cancel() {
		if (rafId !== null) {
			cancelAnimationFrame(rafId);
			rafId = null;
		}
	}

	return {
		setTarget(newTarget: string) {
			if (newTarget === target) return;
			const extends_ = newTarget.startsWith(target);
			target = newTarget;
			if (!extends_) {
				current = '';
				opts.onUpdate(current);
			}
			start();
		},
		stop() {
			cancel();
			draining = false;
		},
		reset() {
			cancel();
			draining = false;
			current = '';
			target = '';
		}
	};
}
