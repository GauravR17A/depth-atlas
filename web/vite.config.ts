import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } },
  },
  build: {
    target: ['chrome109', 'firefox115', 'safari16.4'],
    sourcemap: false,
    rolldownOptions: {
      input: {
        workspace: fileURLToPath(new URL('./index.html', import.meta.url)),
        privacy: fileURLToPath(new URL('./privacy.html', import.meta.url)),
        terms: fileURLToPath(new URL('./terms.html', import.meta.url)),
        about: fileURLToPath(new URL('./about.html', import.meta.url)),
        dataAccess: fileURLToPath(new URL('./data-access.html', import.meta.url)),
      },
    },
  },
});
