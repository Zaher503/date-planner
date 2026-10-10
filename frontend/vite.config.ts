import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

// Dev: the API is the dev instance on the Zephyrus (ssh -L 8821:127.0.0.1:8821 zephyrus)
const api = process.env.DATES_API ?? 'http://127.0.0.1:8821';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: {
      '/api': api,
      '/tiles': api
    }
  },
  test: {
    include: ['src/**/*.test.ts']
  }
});
