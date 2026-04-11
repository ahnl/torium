import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  output: 'static',
  integrations: [react()],
  vite: {
    plugins: [tailwindcss()],
    server: {
      proxy: {
        '/delete-request': 'http://127.0.0.1:5001',
        '/delete-confirm': 'http://127.0.0.1:5001',
        '/tori-login': 'http://127.0.0.1:5001',
        '/mcp': 'http://127.0.0.1:5001',
      },
    },
  },
});
