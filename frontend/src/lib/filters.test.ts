import { describe, expect, it } from 'vitest';
import { activeCount, apiQuery, EMPTY, filterParams, parseFilters, sameFilters } from './filters';

describe('filters', () => {
  it('round-trips through the URL', () => {
    const sp = new URLSearchParams('when=weekend&price=free,2&tags=rooftop,jazz&status=want&dist_km=40&types=event&q=jazz');
    const f = parseFilters(sp);
    expect(f.when).toBe('weekend');
    expect(f.price).toEqual(['free', '2']);
    expect(f.tags).toEqual(['rooftop', 'jazz']);
    expect(f.types).toEqual(['event']);
    expect(f.dist_km).toBe(40);
    expect(parseFilters(filterParams(f))).toEqual(f);
  });

  it('drops junk values', () => {
    const f = parseFilters(new URLSearchParams('when=forever&price=9,free&status=nope&from=yesterday&dist_km=-3&types=planet'));
    expect(f.when).toBe('');
    expect(f.price).toEqual(['free']);
    expect(f.status).toEqual([]);
    expect(f.dist_km).toBeNull();
    expect(f.types).toEqual([]);
  });

  it('leaves defaults out of the URL', () => {
    expect(filterParams(EMPTY).toString()).toBe('');
    expect(filterParams({ ...EMPTY, types: ['place', 'event'] }).toString()).toBe('');
  });

  it('only keeps range dates with when=range', () => {
    const sp = filterParams({ ...EMPTY, when: 'today', from: '2026-10-01', to: '2026-10-02' });
    expect(sp.has('from')).toBe(false);
  });

  it('builds the API query with bbox and my location', () => {
    const q = apiQuery({ ...EMPTY, near: 'me', dist_km: 10 }, { bbox: [-118.5, 33.9, -118.1, 34.2], me: { lat: 34.1, lon: -118.3 } });
    const sp = new URLSearchParams(q);
    expect(sp.get('bbox')).toBe('-118.50000,33.90000,-118.10000,34.20000');
    expect(sp.get('near')).toBe('34.10000,-118.30000');
    expect(sp.get('dist_km')).toBe('10');
  });

  it('counts active filter groups', () => {
    expect(activeCount(EMPTY)).toBe(0);
    expect(activeCount({ ...EMPTY, tags: ['a'], cats: ['bar'], price: ['1'] })).toBe(2);
  });

  it('compares filters ignoring list order of keys', () => {
    expect(sameFilters({ ...EMPTY, q: 'a ' }, { ...EMPTY, q: 'a' })).toBe(true);
    expect(sameFilters({ ...EMPTY, when: 'today' }, EMPTY)).toBe(false);
  });
});
