import {
  estimatedUsageNotice,
  formatCoverageInstant,
  periodIncludesEstimates,
} from '../../src/utils/meteringCoverage';
import type { MeteringPeriodEcho } from '../../src/types/metering';

const period = (extra: Partial<MeteringPeriodEcho> = {}): MeteringPeriodEcho => ({
  key: 'custom',
  from: '2026-10-01',
  to: '2026-10-10',
  start: '2026-10-01T00:00:00+05:30',
  end: '2026-10-11T00:00:00+05:30',
  timezone: 'Asia/Kolkata',
  recordedFrom: null,
  ...extra,
});

describe('estimated usage', () => {
  it('formats instants in IST, the date alone at midnight', () => {
    expect(formatCoverageInstant('2026-10-08T11:30:00+05:30')).toBe('8 Oct 2026, 11:30');
    expect(formatCoverageInstant('2026-10-08T00:00:00+05:30')).toBe('8 Oct 2026');
  });

  it('notes estimated usage when the period starts before recorded usage', () => {
    const p = period({ recordedFrom: '2026-10-08T11:30:00+05:30' });
    expect(periodIncludesEstimates(p)).toBe(true);
    expect(estimatedUsageNotice(p)).toBe('Usage before 8 Oct 2026, 11:30 is estimated from monitoring data.');
  });

  it('says nothing from recorded usage on, or without a backfill', () => {
    const later = period({ start: '2026-10-09T00:00:00+05:30', recordedFrom: '2026-10-08T11:30:00+05:30' });
    expect(periodIncludesEstimates(later)).toBe(false);
    expect(estimatedUsageNotice(later)).toBeNull();
    expect(estimatedUsageNotice(period())).toBeNull();
    expect(estimatedUsageNotice(undefined)).toBeNull();
  });
});
