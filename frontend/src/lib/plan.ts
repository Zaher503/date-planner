// Types and helpers for the date-night planner (docs/API.md, "Date-night plans")
import { DEFAULT_TZ, duration } from './format';

export type TravelMode = 'drive' | 'walk';

export interface PlanForm {
  day: string; // YYYY-MM-DD
  startTime: string; // HH:MM
  endTime: string; // HH:MM, earlier than startTime means after midnight
  budget: number | null; // dollars per person
  vibe: string[];
  start: { lat: number; lon: number } | null; // null = home
  mode: TravelMode;
  maxTravelMin: number | null;
}

export interface SuggestRequest {
  day: string;
  start_time: string;
  end_time: string;
  budget?: number;
  vibe?: string[];
  start?: { lat: number; lon: number };
  mode: TravelMode;
  max_travel_min?: number;
}

export interface PlanItemRef {
  type: 'place' | 'event';
  id: string;
  title: string;
}

export interface SuggestedStop {
  role: 'anchor' | 'food' | 'drinks';
  item: PlanItemRef & {
    category: string | null;
    lat: number;
    lon: number;
    address: string | null;
    venue: string | null;
    url: string | null;
  };
  arrive: string;
  leave: string;
  stay_min: number;
  price_pp: number | null;
  hours_known: boolean | null;
  travel_min: number | null; // to the next stop
  travel_m: number | null;
  mode: TravelMode | null;
  estimated: boolean;
  reason: string;
}

export interface Hop {
  travel_min: number | null;
  travel_m: number | null;
  mode: TravelMode | null;
  estimated: boolean;
}

export interface Itinerary {
  title: string;
  anchor: { type: 'place' | 'event'; id: string };
  start: string;
  end: string;
  start_leg: Hop;
  stops: SuggestedStop[];
  price_pp: number | null;
  price_complete: boolean;
  notes: string[];
}

export interface SuggestResponse {
  itineraries: Itinerary[];
  window: { start: string; end: string };
  start: { lat: number; lon: number; source: 'given' | 'home' };
  considered: { events: number; places: number };
}

export interface SavedStop {
  item: PlanItemRef;
  arrive: string;
  leave: string;
  role?: string;
  travel_min?: number | null;
  mode?: TravelMode | null;
}

export interface SavePlanBody {
  title?: string;
  day: string;
  window_start?: string;
  window_end?: string;
  budget?: number | null;
  vibe?: string[];
  stops: SavedStop[];
}

export interface Plan {
  id: string;
  title: string;
  day: string;
  window_start: string | null;
  window_end: string | null;
  budget: number | null;
  vibe: string[];
  stops: SavedStop[];
  created_by: { id: number; display_name: string | null } | null;
  created_at: string;
  past?: boolean;
  ics: string;
}

/** The body for POST /api/plans/suggest; empty optional fields are left out so the server defaults apply. */
export function suggestBody(f: PlanForm): SuggestRequest {
  const body: SuggestRequest = { day: f.day, start_time: f.startTime, end_time: f.endTime, mode: f.mode };
  if (f.budget != null && f.budget > 0) body.budget = f.budget;
  const vibe = [...new Set(f.vibe.map((v) => v.trim().toLowerCase()).filter(Boolean))];
  if (vibe.length) body.vibe = vibe;
  if (f.start) body.start = { lat: f.start.lat, lon: f.start.lon };
  if (f.maxTravelMin != null && f.maxTravelMin > 0) body.max_travel_min = Math.min(120, Math.round(f.maxTravelMin));
  return body;
}

/** The body for POST /api/plans that saves a suggested itinerary as it was shown. */
export function saveBody(it: Itinerary, form: Pick<PlanForm, 'day' | 'startTime' | 'endTime' | 'budget' | 'vibe'>): SavePlanBody {
  return {
    title: it.title,
    day: form.day,
    window_start: form.startTime,
    window_end: form.endTime,
    budget: form.budget != null && form.budget > 0 ? form.budget : null,
    vibe: form.vibe,
    stops: it.stops.map((s) => ({
      item: { type: s.item.type, id: s.item.id, title: s.item.title },
      arrive: s.arrive,
      leave: s.leave,
      role: s.role,
      travel_min: s.travel_min,
      mode: s.mode
    }))
  };
}

/** "7:30 PM" in the app time zone */
export function clock(iso: string, tz = DEFAULT_TZ): string {
  return new Intl.DateTimeFormat('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' }).format(new Date(iso));
}

/** "7:30 - 9:00 PM", or "11:30 PM - 1:00 AM" when the am/pm differs */
export function stopRange(s: { arrive: string; leave: string }, tz = DEFAULT_TZ): string {
  const a = clock(s.arrive, tz);
  const b = clock(s.leave, tz);
  return a.slice(-2) === b.slice(-2) ? `${a.slice(0, -3)} - ${b}` : `${a} - ${b}`;
}

/** "12 min drive" or "8 min walk"; a straight-line guess is marked "about". Empty when there is no next stop. */
export function travelLabel(h: { travel_min?: number | null; mode?: string | null; estimated?: boolean }): string {
  if (h.travel_min == null || h.mode == null) return '';
  const verb = h.mode === 'walk' ? 'walk' : 'drive';
  return `${h.estimated ? 'about ' : ''}${duration(h.travel_min)} ${verb}`;
}

/** "$80 per person"; "$80+ per person" when some stops have no known price; empty when nothing is known */
export function planPrice(it: Pick<Itinerary, 'price_pp' | 'price_complete'>): string {
  if (it.price_pp == null) return '';
  if (it.price_pp === 0) return it.price_complete ? 'Free' : '';
  return `$${Math.round(it.price_pp)}${it.price_complete ? '' : '+'} per person`;
}

/** Total minutes on the road for an itinerary, including the leg from the start point */
export function totalTravelMin(it: Pick<Itinerary, 'start_leg' | 'stops'>): number {
  return (it.start_leg.travel_min ?? 0) + it.stops.reduce((n, s) => n + (s.travel_min ?? 0), 0);
}

/** Today's date and a default 6 PM to 11 PM night for the form */
export function defaultForm(now = new Date(), tz = DEFAULT_TZ): PlanForm {
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
  return { day, startTime: '18:00', endTime: '23:00', budget: null, vibe: [], start: null, mode: 'drive', maxTravelMin: null };
}
