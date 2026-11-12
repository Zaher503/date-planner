import { describe, expect, it } from 'vitest';
import { clock, defaultForm, planPrice, saveBody, stopRange, suggestBody, totalTravelMin, travelLabel } from './plan';
import type { Itinerary, PlanForm } from './plan';

const form: PlanForm = {
  day: '2026-11-14',
  startTime: '18:00',
  endTime: '23:00',
  budget: 100,
  vibe: [' Jazz ', 'jazz', ''],
  start: null,
  mode: 'drive',
  maxTravelMin: null
};

const stop = (role: 'anchor' | 'food' | 'drinks', id: string, arrive: string, leave: string, travel: number | null) => ({
  role,
  item: { type: 'place' as const, id, title: `T-${id}`, category: null, lat: 34, lon: -118, address: null, venue: null, url: null },
  arrive,
  leave,
  stay_min: 60,
  price_pp: null,
  hours_known: true,
  travel_min: travel,
  travel_m: travel ? travel * 500 : null,
  mode: travel ? ('drive' as const) : null,
  estimated: false,
  reason: ''
});

const itinerary: Itinerary = {
  title: 'A + B',
  anchor: { type: 'place', id: 'a' },
  start: '2026-11-15T01:30:00Z',
  end: '2026-11-15T05:00:00Z',
  start_leg: { travel_min: 10, travel_m: 4000, mode: 'drive', estimated: false },
  stops: [
    stop('food', 'a', '2026-11-15T02:00:00Z', '2026-11-15T03:30:00Z', 12),
    stop('anchor', 'b', '2026-11-15T03:45:00Z', '2026-11-15T05:00:00Z', null)
  ],
  price_pp: 80,
  price_complete: true,
  notes: []
};

describe('plan helpers', () => {
  it('builds a suggest request and leaves empty options out', () => {
    expect(suggestBody(form)).toEqual({
      day: '2026-11-14',
      start_time: '18:00',
      end_time: '23:00',
      mode: 'drive',
      budget: 100,
      vibe: ['jazz']
    });
    const bare = suggestBody({ ...form, budget: null, vibe: [], start: { lat: 34.1, lon: -118.3 }, maxTravelMin: 500 });
    expect(bare).toEqual({
      day: '2026-11-14',
      start_time: '18:00',
      end_time: '23:00',
      mode: 'drive',
      start: { lat: 34.1, lon: -118.3 },
      max_travel_min: 120
    });
  });

  it('saves an itinerary as shown', () => {
    const body = saveBody(itinerary, form);
    expect(body.title).toBe('A + B');
    expect(body.window_start).toBe('18:00');
    expect(body.budget).toBe(100);
    expect(body.stops).toHaveLength(2);
    expect(body.stops[0]).toEqual({
      item: { type: 'place', id: 'a', title: 'T-a' },
      arrive: '2026-11-15T02:00:00Z',
      leave: '2026-11-15T03:30:00Z',
      role: 'food',
      travel_min: 12,
      mode: 'drive'
    });
    expect(saveBody(itinerary, { ...form, budget: null }).budget).toBeNull();
  });

  it('writes clock times in the app time zone', () => {
    // 02:00 UTC on the 15th is 6 PM on the 14th in Los Angeles
    expect(clock('2026-11-15T02:00:00Z')).toBe('6:00 PM');
    expect(stopRange({ arrive: '2026-11-15T02:00:00Z', leave: '2026-11-15T03:30:00Z' })).toBe('6:00 - 7:30 PM');
    expect(stopRange({ arrive: '2026-11-15T07:30:00Z', leave: '2026-11-15T09:00:00Z' })).toBe('11:30 PM - 1:00 AM');
  });

  it('describes travel and price', () => {
    expect(travelLabel({ travel_min: 12, mode: 'drive', estimated: false })).toBe('12 min drive');
    expect(travelLabel({ travel_min: 8, mode: 'walk', estimated: true })).toBe('about 8 min walk');
    expect(travelLabel({ travel_min: null, mode: null })).toBe('');
    expect(planPrice({ price_pp: 80, price_complete: true })).toBe('$80 per person');
    expect(planPrice({ price_pp: 80, price_complete: false })).toBe('$80+ per person');
    expect(planPrice({ price_pp: 0, price_complete: true })).toBe('Free');
    expect(planPrice({ price_pp: 0, price_complete: false })).toBe('');
    expect(planPrice({ price_pp: null, price_complete: false })).toBe('');
  });

  it('adds up road time including the first leg', () => {
    expect(totalTravelMin(itinerary)).toBe(22);
  });

  it('starts the form on today in the app time zone', () => {
    // 03:00 UTC on the 15th is still the 14th in Los Angeles
    expect(defaultForm(new Date('2026-11-15T03:00:00Z')).day).toBe('2026-11-14');
    expect(defaultForm().mode).toBe('drive');
  });
});
