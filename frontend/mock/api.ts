// Offline mock of the JSON API for UI work without the server: `npm run dev:mock`.
// Sample data only; edits live in memory until the dev server restarts.
import type { Connect, Plugin } from 'vite';

type Props = Record<string, unknown> & { id: string; t: 'place' | 'event'; title: string; cat: string };

const HOME = { lat: 34.0461, lon: -118.3265 };
const now = Date.now();
const iso = (h: number) => new Date(now + h * 3600e3).toISOString();

const seed: [Props, number, number][] = [
  [{ id: '11111111-1111-4111-8111-111111111111', t: 'place', title: 'Perch', cat: 'bar', price: '$$', rs: 'ok', tags: ['rooftop', 'views', 'french'], addr: '448 S Hill St, Los Angeles', thumb: false }, 34.0489, -118.2513],
  [{ id: '22222222-2222-4222-8222-222222222222', t: 'place', title: 'Mother of Pearl', cat: 'bar', price: '$$', rs: 'ok', tags: ['cocktails'], addr: '1600 Pacific Coast Hwy', thumb: false }, 34.0, -118.48],
  [{ id: '33333333-3333-4333-8333-333333333333', t: 'place', title: 'Venice Canals', cat: 'outdoors', price: 'Free', free: true, rs: 'needs_review', tags: ['walk', 'canal'], addr: 'Venice, Los Angeles', thumb: false }, 33.985, -118.4695],
  [{ id: '44444444-4444-4444-8444-444444444444', t: 'event', title: 'Rooftop jazz night', cat: 'live_music', price: '$15', rs: 'ok', tags: ['jazz', 'rooftop'], venue: 'Perch', place_id: '11111111-1111-4111-8111-111111111111', start: iso(30), end: iso(33), thumb: false }, 34.049, -118.2515],
  [{ id: 'aaaaaaaa-0000-4000-8000-000000000001', t: 'event', title: 'Wine tasting night', cat: 'live_music', price: '$30', rs: 'needs_review', tags: ['wine'], venue: 'Perch', place_id: '11111111-1111-4111-8111-111111111111', start: iso(6), end: iso(9), thumb: false }, 34.0489, -118.2513],
  [{ id: '55555555-5555-4555-8555-555555555555', t: 'event', title: 'Melrose Trading Post', cat: 'market', price: '$5', rs: 'ok', tags: ['market', 'vintage'], venue: 'Fairfax High School', rec: 'every Sunday', thumb: false }, 34.0835, -118.3617],
  [{ id: '66666666-6666-4666-8666-666666666666', t: 'place', title: 'El Matador Beach', cat: 'beach', price: 'Free', free: true, rs: 'ok', tags: ['beach', 'sunset'], addr: 'Malibu', thumb: false }, 34.0382, -118.8747],
  [{ id: '77777777-7777-4777-8777-777777777777', t: 'place', title: 'Videre', cat: 'restaurant', price: '$$$', rs: 'suggested', tags: ['dining'], addr: 'Pasadena', thumb: false }, 34.1458, -118.1505],
  [{ id: '88888888-8888-4888-8888-888888888888', t: 'event', title: 'Comedy at the Store', cat: 'comedy', price: '$25-40', rs: 'ok', tags: ['comedy'], venue: 'The Comedy Store', start: iso(80), end: iso(82), thumb: false }, 34.0955, -118.3853],
  [{ id: '99999999-9999-4999-8999-999999999999', t: 'place', title: 'Griffith Observatory', cat: 'viewpoint', price: 'Free', free: true, rs: 'ok', tags: ['views', 'stars'], addr: '2800 E Observatory Rd', thumb: false }, 34.1184, -118.3004]
];

const items = new Map<string, { p: Props; lat: number; lon: number; me: Record<string, unknown> | null; extra: Record<string, unknown> }>();
for (const [p, lat, lon] of seed) items.set(p.id, { p: { all_day: false, rec: null, start: null, end: null, free: null, my: null, rating: null, venue: null, addr: null, ...p }, lat, lon, me: null, extra: {} });

const jobs: Record<string, unknown>[] = [];
let jobId = 100;

function dist(lat: number, lon: number) {
  const dx = (lon - HOME.lon) * 111320 * Math.cos((HOME.lat * Math.PI) / 180);
  const dy = (lat - HOME.lat) * 110540;
  return Math.round(Math.hypot(dx, dy));
}

function filtered(sp: URLSearchParams) {
  const bbox = sp.get('bbox')?.split(',').map(Number);
  const q = (sp.get('q') ?? '').toLowerCase();
  const status = sp.get('status')?.split(',') ?? [];
  const types = sp.get('types')?.split(',') ?? [];
  const tags = sp.get('tags')?.split(',') ?? [];
  return [...items.values()].filter(({ p, lat, lon }) => {
    if (bbox && (lon < bbox[0] || lon > bbox[2] || lat < bbox[1] || lat > bbox[3])) return false;
    if (q && !p.title.toLowerCase().includes(q)) return false;
    if (types.length && !types.includes(p.t)) return false;
    if (tags.length && !tags.every((t) => (p.tags as string[]).includes(t))) return false;
    if (status.length) {
      const ok = status.some((s) => (s === 'review' ? p.rs === 'needs_review' : s === 'suggested' ? p.rs === 'suggested' : p.my === s));
      if (!ok) return false;
    } else if (p.rs === 'dismissed' || p.my === 'dismissed') return false;
    return true;
  });
}

function detail(id: string) {
  const it = items.get(id)!;
  const p = it.p;
  const base = {
    id, type: p.t, title: p.title, category: p.cat, description: 'Sample item from the offline mock.', tags: p.tags,
    lat: it.lat, lon: it.lon, address_text: p.addr ?? null, review_status: p.rs, confidence: 0.8, origin: 'manual',
    created_at: iso(-50), updated_at: iso(-2), edited: [], review_reasons: p.rs === 'needs_review' ? ['No date was found for this event.', 'The map pin for the venue is not certain. Open the venue to confirm it.'] : [], price_label: p.price ?? null,
    sources: [{ id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', kind: 'tiktok', url: 'https://www.tiktok.com/@someone/video/1', title: 'Date ideas in LA', caption: 'Five rooftop bars', thumb: null, video: null, created_at: iso(-50), fetched_at: iso(-50), submitted_by: 'Zaher' }],
    me: it.me, others: [{ user: 'Katherine', status: 'want', rating: null, notes: 'Go at sunset' }],
    candidates: p.rs === 'needs_review'
      ? [
          { id: 1, name: p.title, address: p.addr, score: 0.6, provider: 'photon', chosen: true, lat: it.lat, lon: it.lon },
          { id: 2, name: `${p.title} (north)`, address: 'Somewhere else', score: 0.5, provider: 'photon', chosen: false, lat: it.lat + 0.01, lon: it.lon + 0.005 }
        ]
      : [],
    ...it.extra
  };
  return p.t === 'place'
    ? { ...base, website: 'https://example.com', phone: null, opening_hours: 'Mo-Su 16:00-01:00', open_now: true, price_level: 2, closed: false, events: [] }
    : { ...base, starts_at: p.start, ends_at: p.end, duration_min: p.start ? 180 : null, duration_estimated: true, all_day: false, recurrence_text: p.rec, tz: 'America/Los_Angeles', price_min: 15, price_max: null, currency: 'USD', is_free: false, price_text: null, ticket_url: null, status: 'scheduled', venue_name: p.venue, place: null, occurrences: p.start ? [0, 7, 14, 21, 35].map((d) => ({ starts_at: new Date(Date.parse(String(p.start)) + d * 86400000).toISOString(), ends_at: null })) : [] };
}

function feature(it: { p: Props; lat: number; lon: number }) {
  return { type: 'Feature', geometry: { type: 'Point', coordinates: [it.lon, it.lat] }, properties: { ...it.p, dist_m: dist(it.lat, it.lon) } };
}

async function body(req: Connect.IncomingMessage): Promise<Record<string, unknown>> {
  let raw = '';
  for await (const chunk of req) raw += chunk;
  try {
    return JSON.parse(raw || '{}');
  } catch {
    return {};
  }
}

export function mockApi(): Plugin {
  return {
    name: 'dates-mock-api',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url ?? '/', 'http://x');
        const path = url.pathname;
        if (!path.startsWith('/api/') && !path.startsWith('/tiles/')) return next();
        const send = (code: number, data?: unknown) => {
          res.statusCode = code;
          res.setHeader('Content-Type', 'application/json');
          res.end(data === undefined ? '' : JSON.stringify(data));
        };
        const m = path.match(/^\/api\/items\/(place|event)\/([0-9a-f-]{36})(\/me|\/reprocess)?$/);
        if (path === '/api/settings')
          return send(200, {
            home: { ...HOME, source: 'ha' }, radius_km: 40, units: 'mi', tz: 'America/Los_Angeles',
            user: { id: 1, username: 'zaher', display_name: 'Zaher' },
            users: [{ id: 1, username: 'zaher', display_name: 'Zaher' }, { id: 2, username: 'katherine', display_name: 'Katherine' }],
            map: { tiles: '/tiles/region.pmtiles', assets: '/tiles/assets', bounds: [-120.3, 32.5, -116.0, 35.8] }
          });
        if (path === '/api/facets') {
          const counts = new Map<string, number>();
          const cats = new Map<string, number>();
          for (const { p } of items.values()) {
            for (const t of p.tags as string[]) counts.set(t, (counts.get(t) ?? 0) + 1);
            cats.set(p.cat, (cats.get(p.cat) ?? 0) + 1);
          }
          return send(200, { tags: [...counts].map(([tag, n]) => ({ tag, n })), categories: [...cats].map(([cat, n]) => ({ cat, n })) });
        }
        if (path === '/api/map') return send(200, { type: 'FeatureCollection', features: filtered(url.searchParams).map(feature) });
        if (path === '/api/list') {
          const all = filtered(url.searchParams);
          return send(200, { items: all.map((it) => ({ ...it.p, lat: it.lat, lon: it.lon, dist_m: dist(it.lat, it.lon) })), total: all.length });
        }
        if (m && items.has(m[2])) {
          const it = items.get(m[2])!;
          if (m[3] === '/me' && req.method === 'PUT') {
            const b = await body(req);
            it.me = { status: null, rating: null, notes: null, visited_at: null, ...(it.me ?? {}), ...b };
            it.p.my = (it.me.status as string) ?? null;
            it.p.rating = (it.me.rating as number) ?? null;
            return send(200, it.me);
          }
          if (m[3] === '/reprocess') return send(200, { jobs: [] });
          if (req.method === 'PATCH') {
            const b = await body(req);
            if (typeof b.title === 'string') it.p.title = b.title;
            if (b.lat != null && b.lon != null) {
              it.lat = Number(b.lat);
              it.lon = Number(b.lon);
            }
            if (typeof b.review_status === 'string') it.p.rs = b.review_status;
            it.extra = { ...it.extra, ...b, edited: Object.keys(b) };
            return send(200, detail(m[2]));
          }
          if (req.method === 'DELETE') {
            items.delete(m[2]);
            return send(204);
          }
          return send(200, detail(m[2]));
        }
        if (m) return send(404, { detail: 'no such item' });
        const r = path.match(/^\/api\/places\/([0-9a-f-]{36})\/resolve$/);
        if (r && items.has(r[1])) {
          const it = items.get(r[1])!;
          it.p.rs = 'ok';
          return send(200, { id: r[1], review_status: 'ok', lat: it.lat, lon: it.lon });
        }
        if (path === '/api/ui/add' || path === '/api/ui/add-image') {
          const id = ++jobId;
          const started = Date.now();
          jobs.push({ id, started });
          return send(200, { status: 'queued', source_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', job_id: id, kind: 'tiktok' });
        }
        if (path === '/api/ui/add-bulk') {
          for (let i = 0; i < 8; i++) jobs.push({ id: ++jobId, started: Date.now() + i * 4000 });
          return send(200, { accepted: 8 });
        }
        if (path === '/api/jobs') {
          const out = jobs.map((j) => {
            const age = Math.max(0, (Date.now() - (j.started as number)) / 1000);
            const done = age > 7;
            return {
              id: j.id, type: 'ingest', status: done ? 'done' : 'running', stage: age < 3 ? 'reading the link' : 'finding place 1 of 1',
              pct: Math.min(99, Math.round(age * 14)), error: null, source_id: null, created_at: iso(0), finished_at: done ? iso(0) : null,
              url: 'https://www.tiktok.com/@someone/video/2', title: 'Sample TikTok', kind: 'tiktok',
              result: done ? { items: [{ type: 'place', id: '11111111-1111-4111-8111-111111111111', name: 'Perch', review: false }], placed: 1, review: 0 } : {}
            };
          });
          return send(200, out);
        }
        if (path === '/api/health/services')
          return send(200, [
            { name: 'photon', ok: true, ms: 12, detail: null },
            { name: 'ollama', ok: false, ms: 5003, detail: 'ConnectTimeout' }
          ]);
        return send(404, { detail: 'not in the mock' });
      });
    }
  };
}
