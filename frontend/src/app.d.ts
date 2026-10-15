// See https://svelte.dev/docs/kit/types#app.d.ts
declare global {
  namespace App {}
  // Set at build time in vite.config.ts: "v0.16 10-14-18:42"
  const __APP_VERSION__: string;
}

export {};
