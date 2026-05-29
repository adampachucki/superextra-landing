import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter({
			fallback: '404.html'
		}),
		// Absolute asset URLs so they don't inherit a /de or /pl locale prefix
		// (paraglide-js#503 — required for localized routes on adapter-static).
		paths: {
			relative: false
		},
		prerender: {
			// Locale variants reroute to the same routes, so the crawler can't
			// discover them by route alone. List the localized marketing pages
			// explicitly so every one is emitted at build time. App routes
			// (/chat, /login) and English-only pages (/memo, /privacy-policy,
			// /terms) stay unprefixed and are not localized yet.
			entries: ['*', '/de', '/pl', '/de/landing', '/pl/landing']
		}
	}
};

export default config;
