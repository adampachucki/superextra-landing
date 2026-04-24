import { defineConfig } from 'vitest/config';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
	plugins: [sveltekit(), tailwindcss()],
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
		hmr: {
			timeout: 5000,
			overlay: false
		},
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
			'/__/firebase/init.json': {
				target: 'https://agent.superextra.ai',
				changeOrigin: true
			},
			'/api/intake': 'https://superextra-landing.web.app',
			'/api/agent/delete': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/agent\/delete/, '/agentDelete')
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
