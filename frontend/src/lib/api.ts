// Typed wrappers for the JSON API (docs/API.md)

export type ItemType = 'place' | 'event';
export type MyStatus = 'want' | 'going' | 'been' | 'dismissed';

export interface User {
  id: number;
  username: string;
  display_name: string | null;
}

export interface Settings {
  home: { lat: number; lon: number; source: string };
  radius_km: number;
  units: 'mi' | 'km';
  tz: string;
  user: User;
  users: User[];
  map: { tiles: string; assets: string; bounds: [number, number, number, number] };
}

export interface Facets {
  tags: { tag: string; n: number }[];
  categories: { cat: string; n: number }[];
}

export interface ItemProps {
  id: string;
  t: ItemType;
  title: string;
  cat: string | null;
  start: string | null;
  end: string | null;
  all_day: boolean;
  rec: string | null;
  dates?: number;
  price: string | null;
  free: boolean | null;
  rs: 'ok' | 'needs_review' | 'suggested' | 'dismissed';
  my: MyStatus | null;
  rating: number | null;
  addr: string | null;
  venue: string | null;
  dist_m: number | null;
  thumb: boolean;
  thumb_src?: string | null;
  hero?: number | null;
  tags: string[];
  place_id?: string | null;
}

export interface MapFeature {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: ItemProps;
}

export interface MapData {
  type: 'FeatureCollection';
  features: MapFeature[];
}

export interface ListItem extends ItemProps {
  lat: number;
  lon: number;
  /** Set on a place that holds several events: they are listed under it. */
  group?: { count: number; next: string | null; allDay: boolean };
}

export interface Candidate {
  id: number;
  name: string;
  address: string | null;
  score: number;
  provider: string;
  chosen: boolean;
  lat: number;
  lon: number;
}

export interface SourceInfo {
  id: string;
  kind: string;
  url: string | null;
  title: string | null;
  caption: string | null;
  thumb: string | null;
  video: string | null;
  created_at: string;
  fetched_at: string | null;
  submitted_by: string | null;
}

export interface ItemImage {
  id: number;
  kind: 'frame' | 'page';
  at: number | null;
  chosen: boolean;
  url: string;
  video: string | null;
}

export interface MyState {
  status: MyStatus | null;
  rating: number | null;
  notes: string | null;
  visited_at: string | null;
}

export interface Item {
  id: string;
  type: ItemType;
  title: string;
  category: string | null;
  description: string | null;
  tags: string[];
  lat: number;
  lon: number;
  address_text: string | null;
  review_status: string;
  confidence: number | null;
  origin: string;
  created_at: string;
  updated_at: string;
  edited: string[];
  price_label: string | null;
  // Place
  website?: string | null;
  phone?: string | null;
  opening_hours?: string | null;
  hours_text?: string | null;
  price_tiers?: { label: string; price: number | null; note: string | null }[];
  open_now?: boolean | null;
  price_level?: number | null;
  closed?: boolean;
  events?: {
    id: string;
    title: string;
    starts_at: string | null;
    ends_at: string | null;
    all_day: boolean;
    duration_min: number | null;
    tz: string;
    dates: number;
    recurrence_text: string | null;
    price_label: string | null;
  }[];
  // Event
  starts_at?: string | null;
  ends_at?: string | null;
  duration_min?: number | null;
  duration_estimated?: boolean;
  all_day?: boolean;
  recurrence_text?: string | null;
  tz?: string;
  price_min?: number | null;
  price_max?: number | null;
  currency?: string;
  is_free?: boolean | null;
  price_text?: string | null;
  ticket_url?: string | null;
  status?: string;
  venue_name?: string | null;
  occurrences?: { starts_at: string; ends_at: string | null }[];
  place?: { id: string; title: string } | null;

  sources: SourceInfo[];
  review_reasons: string[];
  images: ItemImage[];
  me: MyState | null;
  others: { user: string; status: MyStatus | null; rating: number | null; notes: string | null }[];
  candidates: Candidate[];
}

export interface Job {
  id: number;
  type: string;
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  stage: string | null;
  pct: number;
  error: string | null;
  result: {
    items?: { type?: ItemType; id?: string; name?: string; event_title?: string; error?: string; review?: boolean }[];
    placed?: number;
    review?: number;
    error?: string;
  } | null;
  source_id: string | null;
  created_at: string;
  finished_at: string | null;
  url: string | null;
  title: string | null;
  kind: string | null;
}

export interface AddResult {
  status: 'queued' | 'exists' | 'stub';
  source_id: string;
  job_id: number | null;
  kind: string;
}

export interface ServiceHealth {
  name: string;
  ok: boolean;
  ms: number;
  detail: string | null;
}

/** The Authentik sign-in ran out: the proxy answers every request with a redirect to the login site. */
export class SessionExpired extends Error {
  constructor() {
    super('Your sign-in expired.');
  }
}

const SIGN_IN_KEY = 'dates.signInAt';
const SIGN_IN_GAP_MS = 60_000;

/** Reload once so the browser itself follows the login redirect. Returns false when it already tried a moment ago. */
export function signInAgain(): boolean {
  try {
    const last = Number(sessionStorage.getItem(SIGN_IN_KEY) || 0);
    if (Date.now() - last < SIGN_IN_GAP_MS) return false;
    sessionStorage.setItem(SIGN_IN_KEY, String(Date.now()));
  } catch {
    // storage can be blocked: reload anyway, once per page load
  }
  location.reload();
  return true;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
    credentials: 'same-origin',
    // A redirect to the login site cannot be followed by fetch; see it instead of failing with "Failed to fetch"
    redirect: 'manual'
  });
  if (res.type === 'opaqueredirect') {
    signInAgain();
    throw new SessionExpired();
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (typeof j.detail === 'string') msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d: { msg: string }) => d.msg).join(', ');
    } catch {
      // not JSON
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  settings: () => request<Settings>('GET', '/api/settings'),
  facets: () => request<Facets>('GET', '/api/facets'),
  map: (query: string, signal?: AbortSignal) => request<MapData>('GET', `/api/map?${query}`, undefined, signal),
  list: (query: string, signal?: AbortSignal) =>
    request<{ items: ListItem[]; total: number }>('GET', `/api/list?${query}`, undefined, signal),
  item: (type: ItemType, id: string) => request<Item>('GET', `/api/items/${type}/${id}`),
  patch: (type: ItemType, id: string, body: Record<string, unknown>) =>
    request<Item>('PATCH', `/api/items/${type}/${id}`, body),
  setImage: (type: ItemType, id: string, imageId: number | null) =>
    request<Item>('PUT', `/api/items/${type}/${id}/image`, { image_id: imageId }),
  remove: (type: ItemType, id: string) => request<void>('DELETE', `/api/items/${type}/${id}`),
  setMine: (type: ItemType, id: string, body: Partial<MyState>) =>
    request<MyState>('PUT', `/api/items/${type}/${id}/me`, body),
  reprocess: (type: ItemType, id: string) => request<{ jobs: number[] }>('POST', `/api/items/${type}/${id}/reprocess`),
  resolve: (placeId: string, candidateId: number | null) =>
    request<{ id: string; review_status: string; lat: number; lon: number }>('POST', `/api/places/${placeId}/resolve`, {
      candidate_id: candidateId
    }),
  add: (text: string) => {
    const t = text.trim();
    return request<AddResult>('POST', '/api/ui/add', /^https?:\/\/\S+$/i.test(t) ? { url: t } : { text: t });
  },
  addBulk: (urls: string[]) => request<{ accepted: number }>('POST', '/api/ui/add-bulk', { urls }),
  addImage: async (file: Blob, name = 'screenshot') => {
    const form = new FormData();
    form.append('file', file, name);
    const res = await fetch('/api/ui/add-image', { method: 'POST', body: form, credentials: 'same-origin' });
    if (!res.ok) {
      let msg = `${res.status} ${res.statusText}`;
      try {
        const j = await res.json();
        if (typeof j.detail === 'string') msg = j.detail;
      } catch {
        // not JSON
      }
      throw new ApiError(res.status, msg);
    }
    return (await res.json()) as AddResult;
  },
  jobs: () => request<Job[]>('GET', '/api/jobs'),
  services: () => request<ServiceHealth[]>('GET', '/api/health/services')
};
