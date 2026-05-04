export interface TypewriterController {
	setTarget(text: string): void;
	stop(): void;
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
	let frame: number | null = null;
	let target = '';
	let index = 0;

	function stop() {
		if (frame !== null) {
			cancelAnimationFrame(frame);
			frame = null;
		}
	}

	function tick() {
		frame = null;
		index = Math.min(target.length, index + charsPerFrame);
		onUpdate(target.slice(0, index));
		if (index < target.length) {
			frame = requestAnimationFrame(tick);
		} else {
			onDone?.();
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
			if (!target) {
				onDone?.();
				return;
			}
			if (index < target.length) {
				frame = requestAnimationFrame(tick);
			} else {
				onDone?.();
			}
		},
		stop
	};
}
