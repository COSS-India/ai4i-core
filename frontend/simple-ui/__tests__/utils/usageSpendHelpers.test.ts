import {
  formatBillingMonth,
  formatSpendMoneyExact,
} from '../../src/utils/usageSpendHelpers';
import { formatPeriodTitle } from '../../src/utils/meteringFormatters';

describe('Budget tab formatters', () => {
  it('keeps paise on period spend', () => {
    expect(formatSpendMoneyExact(0.42)).toBe('₹0.42');
    expect(formatSpendMoneyExact(120.5)).toBe('₹120.50');
  });

  it('formats a billing month', () => {
    expect(formatBillingMonth('2026-10')).toBe('Oct 2026');
    expect(formatBillingMonth('bad')).toBe('bad');
  });

  it('titles the selected period', () => {
    expect(formatPeriodTitle({ key: 'last_7_days' })).toBe('Last 7 days');
    expect(
      formatPeriodTitle({ key: 'custom', range: { from: '2026-10-01', to: '2026-10-08' } }),
    ).toBe('01 Oct – 08 Oct 2026');
  });
});
