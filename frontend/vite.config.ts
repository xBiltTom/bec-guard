import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const root = fileURLToPath(new URL('..', import.meta.url));
  // Only server-side settings are loaded here; no secret is exposed as VITE_*.
  const env = loadEnv(mode, root, ['BACKEND_PORT', 'BACKEND_PROXY_TARGET']);
  const proxy = {
    '/api': {
      target:
        env.BACKEND_PROXY_TARGET ||
        `http://127.0.0.1:${env.BACKEND_PORT || '8000'}`,
      changeOrigin: true,
    },
    '/health': {
      target:
        env.BACKEND_PROXY_TARGET ||
        `http://127.0.0.1:${env.BACKEND_PORT || '8000'}`,
      changeOrigin: true,
    },
  };

  return { plugins: [react()], server: { proxy }, preview: { proxy } };
});
