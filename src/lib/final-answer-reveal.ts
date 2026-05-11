import type { Action } from 'svelte/action';

type Artifact = { block: HTMLElement; wrap: HTMLElement; loader: HTMLElement; spin: Animation };

const ease = 'cubic-bezier(0.22, 1, 0.36, 1)';

function wrapWords(root: HTMLElement) {
	const words: HTMLElement[] = [];
	const textNodes: Text[] = [];
	const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
		acceptNode(node) {
			if (!node.textContent?.trim()) return NodeFilter.FILTER_REJECT;
			return node.parentElement?.closest('pre, code, svg, canvas, table, .chart-block')
				? NodeFilter.FILTER_REJECT
				: NodeFilter.FILTER_ACCEPT;
		}
	});
	for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null)
		textNodes.push(node);
	for (const node of textNodes) {
		const fragment = document.createDocumentFragment();
		const text = node.textContent ?? '';
		let cursor = 0;
		for (const match of text.matchAll(/(\S+)(\s*)/g)) {
			const index = match.index ?? 0;
			if (index > cursor) fragment.append(text.slice(cursor, index));
			const word = document.createElement('span');
			word.textContent = match[1];
			word.style.cssText = 'display:inline-block;opacity:.05;transform:translateY(.34em)';
			fragment.append(word, match[2]);
			words.push(word);
			cursor = index + match[0].length;
		}
		if (cursor < text.length) fragment.append(text.slice(cursor));
		node.replaceWith(fragment);
	}
	return words;
}

function prepareArtifact(block: HTMLElement): Artifact {
	const wrap = document.createElement('div');
	wrap.style.position = 'relative';
	block.before(wrap);
	wrap.append(block);

	const loader = document.createElement('div');
	loader.style.cssText =
		'position:absolute;inset:0;z-index:1;display:flex;align-items:center;justify-content:center;color:currentColor;opacity:0;pointer-events:none';

	const spinner = document.createElement('span');
	spinner.style.cssText =
		'width:26px;height:26px;border-radius:999px;border:2px solid currentColor;border-top-color:transparent;opacity:.45';
	loader.append(spinner);
	wrap.append(loader);

	block.style.opacity = '0';
	block.style.transform = 'translateY(10px)';
	const spin = spinner.animate([{ transform: 'rotate(0turn)' }, { transform: 'rotate(1turn)' }], {
		duration: 760,
		iterations: Infinity
	});
	return { block, wrap, loader, spin };
}

function cleanup(words: HTMLElement[], artifacts: Artifact[]) {
	for (const word of words) word.replaceWith(word.textContent ?? '');
	for (const { block, wrap, loader, spin } of artifacts) {
		spin.cancel();
		loader.remove();
		block.style.opacity = '';
		block.style.transform = '';
		wrap.before(block);
		wrap.remove();
	}
}

export const finalAnswerReveal: Action<HTMLElement, (() => void) | undefined> = (root, onDone) => {
	if (!onDone) return;
	if (matchMedia('(prefers-reduced-motion: reduce)').matches) return void onDone();

	let cancelled = false;
	const animations: Animation[] = [];
	const artifacts: Artifact[] = [];
	let words: HTMLElement[] = [];

	const frame = requestAnimationFrame(() => {
		words = wrapWords(root);
		const blocks = Array.from(root.querySelectorAll<HTMLElement>('table, .chart-block'));
		const follows = Node.DOCUMENT_POSITION_FOLLOWING;

		words.forEach((word, index) => {
			animations.push(
				word.animate(
					[
						{ opacity: 0.05, transform: 'translateY(.34em)' },
						{ opacity: 1, transform: 'translateY(0)' }
					],
					{ duration: 640, delay: 120 + index * 10, easing: ease, fill: 'both' }
				)
			);
		});

		for (const block of blocks) {
			const artifact = prepareArtifact(block);
			const delay =
				640 + words.filter((word) => word.compareDocumentPosition(block) & follows).length * 10;
			artifacts.push(artifact);
			animations.push(
				artifact.loader.animate([{ opacity: 1 }, { opacity: 0 }], {
					duration: 1100,
					delay,
					easing: 'ease-out'
				}),
				block.animate(
					[
						{ opacity: 0, transform: 'translateY(10px)' },
						{ opacity: 1, transform: 'translateY(0)' }
					],
					{ duration: 420, delay: delay + 700, easing: ease, fill: 'both' }
				)
			);
		}

		Promise.all(animations.map((animation) => animation.finished.catch(() => undefined))).then(
			() => {
				if (cancelled) return;
				cleanup(words, artifacts);
				onDone();
			}
		);
	});

	return {
		destroy() {
			cancelled = true;
			cancelAnimationFrame(frame);
			animations.forEach((animation) => animation.cancel());
			cleanup(words, artifacts);
		}
	};
};
