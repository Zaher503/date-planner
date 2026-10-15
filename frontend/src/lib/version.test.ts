import { describe, expect, it } from 'vitest';
import { buildStamp, versionLabel } from './version';

describe('version label', () => {
  it('shows month-day-hour:minute in Los Angeles time', () => {
    // 2026-10-15 01:42 UTC is 18:42 on the 14th in Los Angeles (daylight time)
    expect(buildStamp(new Date('2026-10-15T01:42:00Z'))).toBe('10-14-18:42');
  });

  it('uses a 24 hour clock and zero pads', () => {
    expect(buildStamp(new Date('2026-01-05T17:03:00Z'))).toBe('01-05-09:03');
    expect(buildStamp(new Date('2026-01-05T08:00:00Z'))).toBe('01-05-00:00');
  });

  it('puts the version first', () => {
    expect(versionLabel('0.16\n', new Date('2026-10-15T01:42:00Z'))).toBe('v0.16 10-14-18:42');
  });
});
