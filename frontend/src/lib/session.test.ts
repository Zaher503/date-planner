import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, SessionExpired } from './api';
import { bypassesWorker, mayServeShell } from './sw-routes';

function stubBrowser() {
  const store = new Map<string, string>();
  const reload = vi.fn();
  vi.stubGlobal('sessionStorage', { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) });
  vi.stubGlobal('location', { reload });
  return reload;
}

describe('an expired sign-in', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('reloads once to sign in again, then reports it instead of looping', async () => {
    const reload = stubBrowser();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ type: 'opaqueredirect', status: 0, ok: false }));
    await expect(api.settings()).rejects.toBeInstanceOf(SessionExpired);
    expect(reload).toHaveBeenCalledTimes(1);
    await expect(api.settings()).rejects.toBeInstanceOf(SessionExpired);
    expect(reload).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(61_000);
    await expect(api.settings()).rejects.toBeInstanceOf(SessionExpired);
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it('asks fetch not to follow redirects, and still reads normal answers', async () => {
    stubBrowser();
    const fetchMock = vi.fn().mockResolvedValue({ type: 'basic', ok: true, status: 200, json: async () => ({ tz: 'x' }) });
    vi.stubGlobal('fetch', fetchMock);
    await expect(api.settings()).resolves.toEqual({ tz: 'x' });
    expect(fetchMock.mock.calls[0][1].redirect).toBe('manual');
  });
});

describe('service worker routes', () => {
  it('leaves the login hand-off, the API and the health check alone', () => {
    for (const p of ['/outpost.goauthentik.io/callback', '/outpost.goauthentik.io/start', '/api/settings', '/cal/abc.ics', '/healthz', '/tiles/socal.pmtiles']) {
      expect(bypassesWorker(p)).toBe(true);
    }
    for (const p of ['/', '/_app/immutable/entry/app.js', '/share']) expect(bypassesWorker(p)).toBe(false);
  });

  it('serves the cached shell only offline', () => {
    expect(mayServeShell(false)).toBe(true);
    expect(mayServeShell(true)).toBe(false);
  });
});
