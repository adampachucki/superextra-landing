/**
 * Meta Pixel — conversion tracking for paid-social lead campaigns.
 *
 * `initMetaPixel()` runs once from the root layout on mount (browser only) and
 * fires PageView. `trackLead()` fires the `Lead` standard event when the access
 * form is submitted successfully — that's the conversion the Leads campaign
 * optimizes toward.
 *
 * The pixel ID is public (it ships in client code and network calls), the same
 * posture as the PostHog project key in `analytics.ts`. Loaded unconditionally,
 * matching how analytics already initialises here.
 */
import { browser } from '$app/environment';

const PIXEL_ID = '2061038364814901';

interface Fbq {
	(...args: unknown[]): void;
	callMethod?: (...args: unknown[]) => void;
	queue: unknown[][];
	push: Fbq;
	loaded: boolean;
	version: string;
}

declare global {
	interface Window {
		fbq: Fbq;
		_fbq: Fbq;
	}
}

let started = false;

export function initMetaPixel(): void {
	if (!browser || started) return;
	started = true;

	// De-minified Meta bootstrap: define the fbq command queue, then load
	// fbevents.js, which drains the queue once ready.
	if (!window.fbq) {
		const fbq = function (...args: unknown[]) {
			if (fbq.callMethod) fbq.callMethod(...args);
			else fbq.queue.push(args);
		} as Fbq;
		fbq.push = fbq;
		fbq.loaded = true;
		fbq.version = '2.0';
		fbq.queue = [];
		window.fbq = fbq;
		window._fbq = fbq;

		const script = document.createElement('script');
		script.async = true;
		script.src = 'https://connect.facebook.net/en_US/fbevents.js';
		document.head.appendChild(script);
	}

	window.fbq('init', PIXEL_ID);
	window.fbq('track', 'PageView');
}

export function trackLead(): void {
	if (!started) return;
	window.fbq('track', 'Lead');
}
