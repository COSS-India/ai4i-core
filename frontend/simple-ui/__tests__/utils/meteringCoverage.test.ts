import {
  estimatedUntilSeconds,
  formatCoverageInstant,
  periodCoverageNotice,
} from '../../src/utils/meteringCoverage';
import type { MeteringPeriodEcho } from '../../src/types/metering';

const period = (extra: Partial<MeteringPeriodEcho> = {}): MeteringPeriodEcho => ({
  key: 'custom',
  from: '2026-10-01',
  to: '2026-10-10',
  start: '2026-10-01T00:00:00+05:30',
  end: '2026-10-11T00:00:00+05:30',
  timezone: 'Asia/Kolkata',
  dataFrom: '2026-10-01T00:00:00+05:30',
  partial: false,
  estimated: false,
  estimatedUntil: null,
  ...extra,
});

describe('period coverage', () => {
  it('formats instants in IST, the date alone at midnight', () => {
    expect(formatCoverageInstant('2026-10-08T11:30:00+05:30')).toBe('8 Oct 2026, 11:30');
    expect(formatCoverageInstant('2026-10-08T00:00:00+05:30')).toBe('8 Oct 2026');
  });

  it('says nothing for a fully recorded period, or one with no data at all', () => {
    expect(periodCoverageNotice(period())).toBeNull();
    expect(periodCoverageNotice(period({ dataFrom: null, partial: true }))).toBeNull();
    expect(periodCoverageNotice(undefined)).toBeNull();
  });

  it('notes where the estimates end', () => {
    const notice = periodCoverageNotice(
      period({ estimated: true, estimatedUntil: '2026-10-08T11:30:00+05:30' }),
    );
    expect(notice).toMatch(/^Figures before 8 Oct 2026, 11:30 are estimates/);
  });

  it('notes incomplete days before the estimates', () => {
    const notice = periodCoverageNotice(
      period({
        dataFrom: '2026-10-03T00:00:00+05:30',
        partial: true,
        estimated: true,
        estimatedUntil: '2026-10-08T11:30:00+05:30',
      }),
    );
    expect(notice).toMatch(/^Figures before 3 Oct 2026 may be incomplete: .* Figures before 8 Oct 2026, 11:30/);
  });

  it('gives the end of the estimates in epoch seconds', () => {
    expect(
      estimatedUntilSeconds(period({ estimated: true, estimatedUntil: '2026-10-08T11:30:00+05:30' })),
    ).toBe(Date.UTC(2026, 9, 8, 6, 0) / 1000);
    expect(estimatedUntilSeconds(period())).toBeNull();
  });
});
