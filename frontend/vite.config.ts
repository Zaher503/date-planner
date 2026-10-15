import { sveltekit } from '@sveltejs/kit/vite';
import { readFileSync } from 'node:fs';
import { defineConfig } from 'vitest/config';
import { mockApi } from './mock/api';
import { versionLabel } from './src/lib/version';

// Dev: the API is the dev instance on the Zephyrus (ssh -L 8821:127.0.0.1:8821 zephyrus)
const api = process.env.DATES_API ?? 'http://127.0.0.1:8821';

// npm run dev:mock (vite --mode mock) serves sample data instead, no server needed
// Shown bottom left; bump frontend/VERSION with every push (see CLAUDE.md)
const version = versionLabel(readFileSync(new URL('./VERSION', import.meta.url), 'utf8'), new Date());

export default defineConfig(({ mode }) => ({
  define: { __APP_VERSION__: JSON.stringify(version) },
  plugins: [...(mode === 'mock' ? [mockApi()] : []), sveltekit()],
  server: {
    proxy: mode === 'mock' ? undefined : { '/api': api, '/tiles': api }
  },
  test: {
    include: ['src/**/*.test.ts']
  }
}));
