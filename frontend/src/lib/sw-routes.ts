// What the service worker leaves alone, and when it may fall back to the cached app shell

/** Requests the worker never touches: the API, the calendar feed, the health check, map tiles and the Authentik
 * login hand-off (its callback must reach the server, never a cached page). */
export function bypassesWorker(path: string): boolean {
  return (
    path.startsWith('/api/') ||
    path.startsWith('/cal/') ||
    path.startsWith('/outpost.goauthentik.io/') ||
    path === '/healthz' ||
    path.endsWith('.pmtiles')
  );
}

/** The cached shell stands in for a page only when the device is offline. A failure while online (a signed-out
 * session, a server error) must show as itself, not as an old build. */
export function mayServeShell(online: boolean): boolean {
  return !online;
}
