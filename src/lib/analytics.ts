/**
 * PostHog analytics — single entry point for product + funnel tracking.
 *
 * `initAnalytics()` runs once from the root layout on mount (browser only).
 * Everything else (`identify`/`reset`/`capture`) is a thin guard over the SDK
 * so call sites don't have to care whether init has run yet: before init they
 * are no-ops, and every event that matters fires after a user action — well
 * after init has completed.
 *
 * EU-hosted (Frankfurt). The `phc_…` project key is a public, write-only
 * ingestion key — safe in client code, like the Firebase web config.
 */
import posthog from 'posthog-js';
import { browser, dev } from '$app/environment';

const POSTHOG_KEY = 'phc_ne7vefJnAEyyU2d6fbw7cfR8ERXcvFDpfFM9qjpxxabo';
const API_HOST = 'https://eu.i.posthog.com';

let started = false;

// Static super properties attached to every captured event. One project key, no
// separate dev/staging projects — stamping the environment lets localhost traffic
// be filtered out in PostHog rather than polluting product metrics. Re-registered
// after `reset()` because `posthog.reset()` clears registered super properties.
function staticSuperProperties(): Record<string, unknown> {
	return { environment: dev ? 'development' : 'production' };
}

export function initAnalytics(): void {
	if (!browser || started) return;
	started = true;
	posthog.init(POSTHOG_KEY, {
		api_host: API_HOST,
		defaults: '2026-01-30'
	});
	posthog.register(staticSuperProperties());
}

export function identify(
	distinctId: string,
	setProps?: Record<string, unknown>,
	setOnceProps?: Record<string, unknown>
): void {
	if (!started) return;
	posthog.identify(distinctId, setProps, setOnceProps);
}

export function reset(): void {
	if (!started) return;
	posthog.reset();
	// `reset()` wipes persistence, including registered super properties — restore
	// the static ones so post-sign-out events keep their `environment` tag.
	posthog.register(staticSuperProperties());
}

export function capture(event: string, props?: Record<string, unknown>): void {
	if (!started) return;
	posthog.capture(event, props);
}

/** Set properties on the current (identified) person without re-identifying.
 *  Used to keep `plan`/`market` current so every event can be sliced by them. */
export function setPersonProperties(
	setProps?: Record<string, unknown>,
	setOnceProps?: Record<string, unknown>
): void {
	if (!started) return;
	posthog.setPersonProperties(setProps, setOnceProps);
}
