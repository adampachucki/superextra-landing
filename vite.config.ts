import { defineConfig } from 'vitest/config';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		host: true,
		port: 5199,
		proxy: {
			'/api/intake': 'https://superextra-landing.web.app',
			'/api/agent/check': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/agent\/check/, '/agentCheck')
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
