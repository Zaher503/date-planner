// Display helpers: dates in the app time zone, distances in miles or km

export const DEFAULT_TZ = 'America/Los_Angeles';

const KM_PER_MI = 1.609344;

export function kmToMi(km: number): number {
  return km / KM_PER_MI;
}

export function miToKm(mi: number): number {
  return mi * KM_PER_MI;
}

export function distance(metres: number | null | undefined, units: 'mi' | 'km' = 'mi'): string {
  if (metres == null) return '';
  if (units === 'km') {
    return metres < 1000 ? `${Math.round(metres / 10) * 10} m` : `${(metres / 1000).toFixed(metres < 10000 ? 1 : 0)} km`;
  }
  const mi = metres / 1000 / KM_PER_MI;
  return `${mi.toFixed(mi < 10 ? 1 : 0)} mi`;
}

/** Calendar day (YYYY-MM-DD) of an instant in a time zone. */
export function dayKey(d: Date, tz = DEFAULT_TZ): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(b + 'T00:00:00Z') - Date.parse(a + 'T00:00:00Z')) / 86400000);
}

/** "Today 8:00 PM", "Tomorrow", "Sat 8:00 PM", "Sat, Oct 18" (all-day or far away). */
export function when(startIso: string | null, opts: { allDay?: boolean; tz?: string; now?: Date } = {}): string {
  if (!startIso) return '';
  const tz = opts.tz ?? DEFAULT_TZ;
  const now = opts.now ?? new Date();
  const d = new Date(startIso);
  const diff = daysBetween(dayKey(now, tz), dayKey(d, tz));
  const time = new Intl.DateTimeFormat('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' }).format(d);
  let day: string;
  if (diff === 0) day = 'Today';
  else if (diff === 1) day = 'Tomorrow';
  else if (diff > 1 && diff < 7) day = new Intl.DateTimeFormat('en-US', { timeZone: tz, weekday: 'short' }).format(d);
  else {
    const sameYear = dayKey(now, tz).slice(0, 4) === dayKey(d, tz).slice(0, 4);
    day = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: sameYear ? undefined : 'numeric'
    }).format(d);
  }
  return opts.allDay ? day : `${day} ${time}`;
}

/** Full date and time for the detail card. */
export function longWhen(startIso: string, endIso: string | null, opts: { allDay?: boolean; tz?: string } = {}): string {
  const tz = opts.tz ?? DEFAULT_TZ;
  const s = new Date(startIso);
  const date = new Intl.DateTimeFormat('en-US', { timeZone: tz, weekday: 'long', month: 'long', day: 'numeric' }).format(s);
  if (opts.allDay) return date;
  const t = (d: Date) => new Intl.DateTimeFormat('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' }).format(d);
  if (!endIso) return `${date}, ${t(s)}`;
  const e = new Date(endIso);
  if (dayKey(s, tz) === dayKey(e, tz)) return `${date}, ${t(s)} to ${t(e)}`;
  const endDate = new Intl.DateTimeFormat('en-US', { timeZone: tz, weekday: 'short', month: 'short', day: 'numeric' }).format(e);
  return `${date}, ${t(s)} to ${endDate} ${t(e)}`;
}

export function duration(minutes: number | null | undefined): string {
  if (!minutes) return '';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (!h) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}

/** Short text for the event pin badge: month and day of the next date, weekday for recurring, blank when unknown. */
export function badge(p: { start: string | null; rec: string | null }, tz = DEFAULT_TZ): string {
  if (p.start) {
    return new Intl.DateTimeFormat('en-US', { timeZone: tz, month: 'short', day: 'numeric' }).format(new Date(p.start));
  }
  if (p.rec) {
    const m = p.rec.toLowerCase().match(/\b(mon|tue|wed|thu|fri|sat|sun)(day|s|\b)/);
    return m ? m[1].slice(0, 2).replace(/^\w/, (c) => c.toUpperCase()) : 'R';
  }
  return '';
}

export function relativeAgo(iso: string, now = new Date()): string {
  const s = Math.round((now.getTime() - new Date(iso).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  return d === 1 ? 'yesterday' : `${d} days ago`;
}

export function hostOf(url: string | null | undefined): string {
  if (!url) return '';
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

export function appleMapsUrl(lat: number, lon: number, name: string, address?: string | null): string {
  const q = encodeURIComponent(name);
  const a = address ? `&address=${encodeURIComponent(address)}` : '';
  return `https://maps.apple.com/?q=${q}&ll=${lat},${lon}${a}`;
}

export function googleMapsUrl(lat: number, lon: number, name: string, address?: string | null): string {
  const query = encodeURIComponent(address ? `${name}, ${address}` : `${name} ${lat},${lon}`);
  return `https://www.google.com/maps/search/?api=1&query=${query}`;
}

function tzOffsetMs(utcMs: number, tz: string): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }).formatToParts(new Date(utcMs));
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value);
  const asUtc = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour'), get('minute'), get('second'));
  return asUtc - Math.floor(utcMs / 1000) * 1000;
}

/** ISO instant -> value for <input type="datetime-local"> in a time zone. */
export function toLocalInput(iso: string | null | undefined, tz = DEFAULT_TZ): string {
  if (!iso) return '';
  const ms = new Date(iso).getTime();
  const local = new Date(ms + tzOffsetMs(ms, tz));
  return local.toISOString().slice(0, 16);
}

/** <input type="datetime-local"> value read in a time zone -> ISO instant (UTC). */
export function fromLocalInput(value: string, tz = DEFAULT_TZ): string | null {
  const m = value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return null;
  const guess = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  let ms = guess - tzOffsetMs(guess, tz);
  // Second pass settles times near a DST change
  ms = guess - tzOffsetMs(ms, tz);
  return new Date(ms).toISOString();
}
