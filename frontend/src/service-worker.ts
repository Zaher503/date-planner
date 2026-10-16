/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

// App shell offline cache. The API and the map tiles always go to the network
// (tiles are HTTP range reads of one big file, which the browser caches itself).
import { build, files, version } from '$service-worker';
import { bypassesWorker, mayServeShell } from './lib/sw-routes';

const sw = self as unknown as ServiceWorkerGlobalScope;
const SHELL = `shell-${version}`;
const ASSETS = 'map-assets-v1';
const PRECACHE = [...build, ...files.filter((f) => !f.endsWith('.png') || f.includes('icon-192'))];

sw.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((c) => c.addAll(['/', ...PRECACHE]))
      .then(() => sw.skipWaiting())
  );
});

sw.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL && k !== ASSETS).map((k) => caches.delete(k))))
      .then(() => sw.clients.claim())
  );
});

sw.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  const path = url.pathname;
  if (bypassesWorker(path)) return;

  // Glyphs and sprites never change: cache first
  if (path.startsWith('/tiles/assets/')) {
    event.respondWith(
      caches.open(ASSETS).then(async (c) => {
        const hit = await c.match(req);
        if (hit) return hit;
        const res = await fetch(req);
        if (res.ok) c.put(req, res.clone());
        return res;
      })
    );
    return;
  }

  // Built files are content-hashed: cache first
  if (PRECACHE.includes(path)) {
    event.respondWith(caches.match(req).then((hit) => hit ?? fetch(req)));
    return;
  }

  // Pages: network first so a new deploy shows up, the cached shell only when offline
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(async () => (mayServeShell(navigator.onLine) ? await caches.match('/') : undefined) ?? Response.error())
    );
  }
});
