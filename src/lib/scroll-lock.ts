import { browser } from '$app/environment';

let lockCount = 0;
let previousBodyOverflow = '';
let previousDocumentOverflow = '';
let lockedScrollY = 0;

export function lockPageScroll(): () => void {
	if (!browser) return () => {};

	if (lockCount === 0) {
		lockedScrollY = window.scrollY;
		previousBodyOverflow = document.body.style.overflow;
		previousDocumentOverflow = document.documentElement.style.overflow;
		document.body.style.overflow = 'hidden';
		document.documentElement.style.overflow = 'hidden';
	}

	lockCount += 1;
	let released = false;

	return () => {
		if (released) return;
		released = true;
		lockCount = Math.max(0, lockCount - 1);
		if (lockCount > 0) return;

		document.body.style.overflow = previousBodyOverflow;
		document.documentElement.style.overflow = previousDocumentOverflow;
		window.scrollTo(0, lockedScrollY);
	};
}
