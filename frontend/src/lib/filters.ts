// Map/list filters. They live in the URL so views can be shared and bookmarked.

import type { ItemType } from './api';

export type When = '' | 'today' | 'tomorrow' | 'weekend' | 'week' | 'month' | 'range';

export interface Filters {
  q: string;
  types: ItemType[]; // empty = both
  when: When;
  from: string; // YYYY-MM-DD, only with when=range
  to: string;
  open_now: boolean;
  past: boolean;
  price: string[]; // free, 1, 2, 3
  tags: string[];
  cats: string[];
  status: string[]; // want, going, been, suggested, review
  dist_km: number | null;
  near: 'home' | 'me';
}

export const EMPTY: Filters = {
  q: '',
  types: [],
  when: '',
  from: '',
  to: '',
  open_now: false,
  past: false,
  price: [],
  tags: [],
  cats: [],
  status: [],
  dist_km: null,
  near: 'home'
};

export const WHEN_LABEL: Record<When, string> = {
  '': 'Any time',
  today: 'Today',
  tomorrow: 'Tomorrow',
  weekend: 'This weekend',
  week: 'Next 7 days',
  month: 'Next 31 days',
  range: 'Dates'
};

export const PRICE_LABEL: Record<string, string> = { free: 'Free', '1': '$', '2': '$$', '3': '$$$' };

export const STATUS_LABEL: Record<string, string> = {
  want: 'Want to go',
  going: 'Going',
  been: 'Been',
  suggested: 'Suggested',
  review: 'Needs review'
};

const WHENS = new Set<When>(['today', 'tomorrow', 'weekend', 'week', 'month', 'range']);
const DATE = /^\d{4}-\d{2}-\d{2}$/;

function list(sp: URLSearchParams, key: string, allowed?: Set<string>): string[] {
  const raw = sp.get(key);
  if (!raw) return [];
  const out = raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  return [...new Set(allowed ? out.filter((s) => allowed.has(s)) : out)];
}

export function parseFilters(sp: URLSearchParams): Filters {
  const when = (sp.get('when') ?? '') as When;
  const from = sp.get('from') ?? '';
  const to = sp.get('to') ?? '';
  const dist = Number(sp.get('dist_km'));
  return {
    q: (sp.get('q') ?? '').slice(0, 200),
    types: list(sp, 'types', new Set(['place', 'event'])) as ItemType[],
    when: WHENS.has(when) ? when : '',
    from: DATE.test(from) ? from : '',
    to: DATE.test(to) ? to : '',
    open_now: sp.get('open_now') === '1',
    past: sp.get('past') === '1',
    price: list(sp, 'price', new Set(['free', '1', '2', '3'])),
    tags: list(sp, 'tags'),
    cats: list(sp, 'cats'),
    status: list(sp, 'status', new Set(Object.keys(STATUS_LABEL))),
    dist_km: Number.isFinite(dist) && dist > 0 ? Math.min(dist, 500) : null,
    near: sp.get('near') === 'me' ? 'me' : 'home'
  };
}

/** URL params for the filters, defaults left out. */
export function filterParams(f: Filters): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.q.trim()) sp.set('q', f.q.trim());
  if (f.types.length === 1) sp.set('types', f.types[0]);
  if (f.when) sp.set('when', f.when);
  if (f.when === 'range') {
    if (f.from) sp.set('from', f.from);
    if (f.to) sp.set('to', f.to);
  }
  if (f.open_now) sp.set('open_now', '1');
  if (f.past) sp.set('past', '1');
  if (f.price.length) sp.set('price', f.price.join(','));
  if (f.tags.length) sp.set('tags', f.tags.join(','));
  if (f.cats.length) sp.set('cats', f.cats.join(','));
  if (f.status.length) sp.set('status', f.status.join(','));
  if (f.dist_km) sp.set('dist_km', String(Math.round(f.dist_km * 10) / 10));
  if (f.near === 'me') sp.set('near', 'me');
  return sp;
}

/** Query string for /api/map and /api/list. `near=me` becomes coordinates. */
export function apiQuery(f: Filters, extra: { bbox?: number[]; me?: { lat: number; lon: number } | null } = {}): string {
  const sp = filterParams(f);
  sp.delete('near');
  if (f.near === 'me' && extra.me) sp.set('near', `${extra.me.lat.toFixed(5)},${extra.me.lon.toFixed(5)}`);
  if (extra.bbox) sp.set('bbox', extra.bbox.map((n) => n.toFixed(5)).join(','));
  return sp.toString();
}

/** Same filters, ignoring order (to skip refetches). */
export function sameFilters(a: Filters, b: Filters): boolean {
  return filterParams(a).toString() === filterParams(b).toString();
}

export function activeCount(f: Filters): number {
  let n = 0;
  if (f.types.length === 1) n++;
  if (f.when || f.past) n++;
  if (f.open_now) n++;
  if (f.price.length) n++;
  if (f.tags.length || f.cats.length) n++;
  if (f.status.length) n++;
  if (f.dist_km) n++;
  return n;
}

export function toggle<T>(arr: T[], v: T): T[] {
  return arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];
}
