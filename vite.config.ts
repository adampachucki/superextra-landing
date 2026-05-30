import { paraglideVitePlugin } from '@inlang/paraglide-js';
import { defineConfig } from 'vitest/config';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
	plugins: [
		sveltekit(),
		tailwindcss(),
		paraglideVitePlugin({
			project: './project.inlang',
			outdir: './src/lib/paraglide',
			// Marketing/public pages are localized by URL (/, /de, /pl) for SEO.
			// The signed-in app resolves locale from the account (cookie), never the URL.
			strategy: ['url', 'cookie', 'preferredLanguage', 'baseLocale'],
			// App + English-only routes resolve locale from the cookie (account
			// language), not the URL — so they stay on canonical, unprefixed paths.
			routeStrategies: [
				{ match: '/chat/:rest(.*)?', strategy: ['cookie', 'preferredLanguage', 'baseLocale'] },
				{ match: '/login/:rest(.*)?', strategy: ['cookie', 'preferredLanguage', 'baseLocale'] },
				// English-only page — excluded from localization until translated.
				{ match: '/memo/:rest(.*)?', exclude: true }
			],
			// These routes are never prefixed: every locale maps to the same path,
			// so localizeHref() and the prerender crawl keep them unprefixed.
			urlPatterns: [
				{
					pattern: ':protocol://:domain(.*)::port?/chat:rest(/.*)?',
					localized: [
						['en', ':protocol://:domain(.*)::port?/chat:rest(/.*)?'],
						['de', ':protocol://:domain(.*)::port?/chat:rest(/.*)?'],
						['pl', ':protocol://:domain(.*)::port?/chat:rest(/.*)?']
					]
				},
				{
					pattern: ':protocol://:domain(.*)::port?/login:rest(/.*)?',
					localized: [
						['en', ':protocol://:domain(.*)::port?/login:rest(/.*)?'],
						['de', ':protocol://:domain(.*)::port?/login:rest(/.*)?'],
						['pl', ':protocol://:domain(.*)::port?/login:rest(/.*)?']
					]
				},
				{
					pattern: ':protocol://:domain(.*)::port?/memo:rest(/.*)?',
					localized: [
						['en', ':protocol://:domain(.*)::port?/memo:rest(/.*)?'],
						['de', ':protocol://:domain(.*)::port?/memo:rest(/.*)?'],
						['pl', ':protocol://:domain(.*)::port?/memo:rest(/.*)?']
					]
				},
				// Everything else: English at root, German under /de, Polish under /pl.
				{
					pattern: ':protocol://:domain(.*)::port?/:path(.*)?',
					localized: [
						['de', ':protocol://:domain(.*)::port?/de/:path(.*)?'],
						['pl', ':protocol://:domain(.*)::port?/pl/:path(.*)?'],
						['en', ':protocol://:domain(.*)::port?/:path(.*)?']
					]
				}
			]
		})
	],
	server: {
		host: true,
		port: 5199,
		allowedHosts: true,
		// No hmr.host — client auto-adapts to page hostname (works on both localhost and IP).
		// timeout doubles as the keepalive ping interval. Mobile Safari kills idle
		// WebSockets after ~30-60s, and Vite does an unconditional location.reload()
		// on reconnect. 5s pings keep the socket alive.
		// Companion patch: patches/vite+7.3.1.patch removes the unconditional
		// reload on reconnect entirely — only genuine server restarts (which send
		// a "full-reload" message) trigger reloads. Without the patch, every
		// Mobile Safari reconnect causes a full page reload.
		hmr: { timeout: 5000, overlay: false },
		watch: {
			// Exclude non-frontend dirs so changes there don't trigger full-page reloads
			ignored: ['agent/**', 'functions/**', 'docs/**', '.firebase/**']
		},
		proxy: {
			// Firebase Hosting auto-generates `/__/firebase/init.json` per site;
			// Vite doesn't serve it. Firebase Hosting doesn't set CORS on it
			// either, so we can't fetch it cross-origin from a dev page — proxy
			// it same-origin instead. Works from localhost, private LAN, the
			// public VM IP (mobile/remote testing), preview tunnels, etc.
			'/__/firebase/init.json': { target: 'https://agent.superextra.ai', changeOrigin: true },
			'/api/intake': 'https://superextra-landing.web.app',
			'/api/agent/delete': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/agent\/delete/, '/agentDelete')
			},
			'/api/agent/cancel': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/agent\/cancel/, '/agentCancel')
			},
			'/api/agent/feedback': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/agent\/feedback/, '/agentFeedback')
			},
			'/api/billing/test/checkout': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) =>
					path.replace(/^\/api\/billing\/test\/checkout/, '/billingCheckoutTest')
			},
			'/api/billing/test/confirm': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) =>
					path.replace(/^\/api\/billing\/test\/confirm/, '/billingConfirmTest')
			},
			'/api/billing/test/portal': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) =>
					path.replace(/^\/api\/billing\/test\/portal/, '/billingPortalTest')
			},
			'/api/billing/checkout': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/billing\/checkout/, '/billingCheckout')
			},
			'/api/billing/confirm': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/billing\/confirm/, '/billingConfirm')
			},
			'/api/billing/portal': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/billing\/portal/, '/billingPortal')
			},
			'/api/auth/send-magic-link': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/auth\/send-magic-link/, '/sendMagicLink')
			},
			'/api/agent/stream': {
				// Hash-based Cloud Run URL — matches the other services in the
				// superextra-site project. Legacy project-number format still
				// resolves but is not what new services are provisioned at.
				target: 'https://agentstream-22b3fxahka-uc.a.run.app',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/agent\/stream/, '/agentStream'),
				timeout: 0
			},
			'/api/stt-token': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/stt-token/, '/sttToken')
			},
			'/api/tts': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/tts/, '/tts')
			}
		}
	},
	test: {
		expect: { requireAssertions: true },
		projects: [
			{
				extends: './vite.config.ts',
				test: {
					name: 'server',
					environment: 'node',
					include: ['src/**/*.{test,spec}.{js,ts}'],
					exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
				}
			}
		]
	}
});
