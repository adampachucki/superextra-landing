/**
 * RAF-based text drain utility.
 *
 * Emits a callback with progressively longer prefixes of `target`, one frame
 * at a time. Used by StreamingProgress to render live agent activity.
 *
 * Two shapes:
 *  - createTypewriter — one running drain
 *  - createTypewriterGroup — a keyed set of independent drains (dictionary
 *    pattern); handles pruning when a key disappears from the live set.
 *
 * The group variant supports two update modes:
 *  - 'extend' (default): if the new target starts with the old, keep the
 *    current display and continue draining. Otherwise reset to empty.
 *  - 'reset': always reset display to empty when target changes.
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

export type UpdateMode = 'extend' | 'reset';

export interface TypewriterGroup {
	/**
	 * Set the target for a given id. Starts a new RAF if needed.
	 * Mode 'extend' (default): if the new target starts with the old, keep
	 * the current display; otherwise reset to empty.
	 * Mode 'reset': always reset to empty on change.
	 */
	setTarget(id: string, target: string, mode?: UpdateMode): void;
	/**
	 * Cancel RAFs and clear internal state for ids not in `keepIds`.
	 * Does NOT emit onUpdate for removed ids — the caller owns display state.
	 */
	prune(keepIds: Set<string>): void;
	/** Cancel all running RAFs. */
	stopAll(): void;
}

export interface TypewriterGroupOptions extends SharedOptions {
	onUpdate: (id: string, current: string) => void;
	onDone?: (id: string) => void;
}

export function createTypewriterGroup(opts: TypewriterGroupOptions): TypewriterGroup {
	const rate = opts.charsPerFrame ?? 2;
	const targets = new Map<string, string>();
	const displays = new Map<string, string>();
	const rafs = new Map<string, number>();
	const draining = new Set<string>();

	function tick(id: string) {
		const target = targets.get(id) ?? '';
		const current = displays.get(id) ?? '';
		if (current.length < target.length) {
			const next = target.slice(0, current.length + rate);
			displays.set(id, next);
			opts.onUpdate(id, next);
			rafs.set(
				id,
				requestAnimationFrame(() => tick(id))
			);
		} else {
			rafs.delete(id);
			if (draining.delete(id)) opts.onDone?.(id);
		}
	}

	function start(id: string) {
		if (rafs.has(id)) return;
		const target = targets.get(id) ?? '';
		const current = displays.get(id) ?? '';
		if (current.length < target.length) {
			draining.add(id);
			rafs.set(
				id,
				requestAnimationFrame(() => tick(id))
			);
		}
	}

	function cancel(id: string) {
		const rafId = rafs.get(id);
		if (rafId !== undefined) {
			cancelAnimationFrame(rafId);
			rafs.delete(id);
		}
		draining.delete(id);
	}

	return {
		setTarget(id: string, target: string, mode: UpdateMode = 'extend') {
			const oldTarget = targets.get(id) ?? '';
			if (oldTarget === target) return;
			targets.set(id, target);
			const shouldReset = mode === 'reset' || !target.startsWith(oldTarget);
			if (shouldReset) {
				displays.set(id, '');
				opts.onUpdate(id, '');
			}
			cancel(id);
			start(id);
		},
		prune(keepIds: Set<string>) {
			for (const id of Array.from(targets.keys())) {
				if (!keepIds.has(id)) {
					cancel(id);
					targets.delete(id);
					displays.delete(id);
				}
			}
		},
		stopAll() {
			for (const rafId of rafs.values()) cancelAnimationFrame(rafId);
			rafs.clear();
			draining.clear();
		}
	};
}
