import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		host: true,
		port: 5199,
		proxy: {
			'/api/intake': 'https://superextra-landing.web.app',
			'/api/agent': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/agent/, '/agent')
			},
			'/api/stt-token': {
				target: 'https://us-central1-superextra-site.cloudfunctions.net',
				changeOrigin: true,
				rewrite: (path: string) => path.replace(/^\/api\/stt-token/, '/sttToken')
			}
		}
	}
});
