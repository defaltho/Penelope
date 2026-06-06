import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		proxy: {
			// Encaminha as chamadas /api para o backend FastAPI (evita CORS;
			// compatível com prod single-origin).
			'/api': {
				target: 'http://127.0.0.1:8000',
				changeOrigin: true,
				// O backend expõe as rotas na raiz (/chat, /memory...), não sob /api
				rewrite: (path) => path.replace(/^\/api/, '')
			}
		}
	}
});
