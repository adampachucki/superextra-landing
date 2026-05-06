export interface TypewriterController {
	setTarget(text: string): void;
	stop(): void;
}

const REVEAL_INTERVAL_MS = 35;

function nextRevealIndex(text: string, index: number, minChars: number): number {
	const floor = Math.min(text.length, index + minChars);
	if (floor >= text.length) return text.length;

	const rest = text.slice(floor);
	const boundary = rest.search(/\s+/);
	if (boundary === -1) return text.length;

	const whitespace = rest.slice(boundary).match(/^\s+/)?.[0].length ?? 0;
	return Math.min(text.length, floor + boundary + whitespace);
}

export function createTypewriter({
	charsPerFrame = 4,
	onDone,
	onUpdate
}: {
	charsPerFrame?: number;
	onDone?: () => void;
	onUpdate: (text: string) => void;
}): TypewriterController {
	let timer: ReturnType<typeof setTimeout> | null = null;
	let target = '';
	let index = 0;
	let completedTarget: string | null = null;

	function stop() {
		if (timer !== null) {
			clearTimeout(timer);
			timer = null;
		}
	}

	function finish() {
		if (completedTarget === target) return;
		completedTarget = target;
		onDone?.();
	}

	function schedule() {
		timer = setTimeout(tick, REVEAL_INTERVAL_MS);
	}

	function tick() {
		timer = null;
		index = nextRevealIndex(target, index, Math.max(8, charsPerFrame * 4));
		onUpdate(target.slice(0, index));
		if (index < target.length) {
			schedule();
		} else {
			finish();
		}
	}

	return {
		setTarget(text: string) {
			stop();
			// If the new target extends the currently-displayed prefix, keep
			// our position so already-revealed text doesn't re-type. This
			// matters when a buffered thought grows as more thought-summary
			// events arrive — the user shouldn't see prior chars vanish.
			const displayedPrefix = target.slice(0, index);
			if (text.startsWith(displayedPrefix)) {
				target = text;
			} else {
				target = text;
				index = 0;
			}
			if (completedTarget !== target) completedTarget = null;
			if (!target) {
				finish();
				return;
			}
			if (index < target.length) {
				schedule();
			} else {
				finish();
			}
		},
		stop
	};
}
