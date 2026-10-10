import { describe, expect, it } from 'vitest';
import { badge, dayKey, distance, duration, fromLocalInput, longWhen, toLocalInput, when } from './format';

const tz = 'America/Los_Angeles';
// Friday 2026-10-09 10:00 in Los Angeles
const now = new Date('2026-10-09T17:00:00Z');

describe('format', () => {
  it('formats distances in miles and km', () => {
    expect(distance(1609.344)).toBe('1.0 mi');
    expect(distance(40000)).toBe('25 mi');
    expect(distance(850, 'km')).toBe('850 m');
    expect(distance(12345, 'km')).toBe('12 km');
    expect(distance(null)).toBe('');
  });

  it('uses the app time zone for day boundaries', () => {
    // 02:00 UTC on the 10th is still the 9th in LA
    expect(dayKey(new Date('2026-10-10T02:00:00Z'), tz)).toBe('2026-10-09');
  });

  it('says today, tomorrow, a weekday, or a date', () => {
    expect(when('2026-10-10T03:00:00Z', { tz, now })).toBe('Today 8:00 PM');
    expect(when('2026-10-10T20:00:00Z', { tz, now })).toBe('Tomorrow 1:00 PM');
    expect(when('2026-10-12T02:30:00Z', { tz, now })).toBe('Sun 7:30 PM');
    expect(when('2026-11-20T20:00:00Z', { tz, now, allDay: true })).toBe('Fri, Nov 20');
    expect(when(null)).toBe('');
  });

  it('writes a full time range', () => {
    expect(longWhen('2026-10-10T03:00:00Z', '2026-10-10T06:00:00Z', { tz })).toBe('Friday, October 9, 8:00 PM to 11:00 PM');
  });

  it('formats durations', () => {
    expect(duration(45)).toBe('45 min');
    expect(duration(180)).toBe('3 h');
    expect(duration(150)).toBe('2 h 30 min');
    expect(duration(null)).toBe('');
  });

  it('makes pin badges', () => {
    expect(badge({ start: '2026-10-18T03:00:00Z', rec: null }, tz)).toBe('17');
    expect(badge({ start: null, rec: 'every Sunday' }, tz)).toBe('Su');
    expect(badge({ start: null, rec: 'monthly' }, tz)).toBe('R');
    expect(badge({ start: null, rec: null }, tz)).toBe('');
  });
});

describe('datetime-local in the app time zone', () => {
  it('converts both ways in summer and winter', () => {
    expect(toLocalInput('2026-07-04T03:30:00Z', tz)).toBe('2026-07-03T20:30');
    expect(fromLocalInput('2026-07-03T20:30', tz)).toBe('2026-07-04T03:30:00.000Z');
    expect(toLocalInput('2026-12-25T20:00:00Z', tz)).toBe('2026-12-25T12:00');
    expect(fromLocalInput('2026-12-25T12:00', tz)).toBe('2026-12-25T20:00:00.000Z');
  });

  it('handles empty values', () => {
    expect(toLocalInput(null, tz)).toBe('');
    expect(fromLocalInput('', tz)).toBeNull();
  });
});
