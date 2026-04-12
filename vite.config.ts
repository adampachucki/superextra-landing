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
		hmr: {
			timeout: 5000,
			overlay: false
		},
		watch: {
			// Exclude non-frontend dirs so changes there don't trigger full-page reloads
			ignored: ['agent/**', 'functions/**', 'docs/**', '.firebase/**']
		},
		proxy: {
			'/api/intake': 'https://superextra-landing.web.app',
			'/api/agent/check': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/agent\/check/, '/agentCheck')
			},
			'/api/agent/stream': {
				target: 'https://agentstream-907466498524.us-central1.run.app',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/agent\/stream/, '/agentStream'),
				timeout: 0
			},
			'/api/agent/debug': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/agent\/debug/, '/agentDebug')
			},
			'/api/agent': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/agent/, '/agent')
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
