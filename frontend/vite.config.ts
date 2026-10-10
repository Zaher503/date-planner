import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';
import { mockApi } from './mock/api';

// Dev: the API is the dev instance on the Zephyrus (ssh -L 8821:127.0.0.1:8821 zephyrus)
const api = process.env.DATES_API ?? 'http://127.0.0.1:8821';

// npm run dev:mock (vite --mode mock) serves sample data instead, no server needed
export default defineConfig(({ mode }) => ({
  plugins: [...(mode === 'mock' ? [mockApi()] : []), sveltekit()],
  server: {
    proxy: mode === 'mock' ? undefined : { '/api': api, '/tiles': api }
  },
  test: {
    include: ['src/**/*.test.ts']
  }
}));
