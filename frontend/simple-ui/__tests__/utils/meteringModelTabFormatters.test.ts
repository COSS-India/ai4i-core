import { METERING } from '../../src/config/meteringConstants';
import {
  formatModelNativeUnits,
  formatPercent,
} from '../../src/utils/meteringFormatters';

describe('formatPercent (Model tab: one decimal place with a % sign)', () => {
  it('rounds to the nearest tenth, using the ticket examples', () => {
    expect(formatPercent(12.54)).toBe('12.5%');
    expect(formatPercent(81.67)).toBe('81.7%');
    // 65.35 is stored as 65.3499…; plain toFixed(1) would give 65.3.
    expect(formatPercent(65.35)).toBe('65.4%');
  });

  it('keeps one decimal place on whole numbers', () => {
    expect(formatPercent(25)).toBe('25.0%');
    expect(formatPercent(0)).toBe('0.0%');
    expect(formatPercent(100)).toBe('100.0%');
  });

  it('supports other precisions', () => {
    expect(formatPercent(18.333, 2)).toBe('18.33%');
  });

  it('rounds halves up where scaling alone falls just short', () => {
    // 1.005 * 100 = 100.49999…, 0.145 * 100 = 14.499…: Math.round would go down.
    expect(formatPercent(1.005, 2)).toBe('1.01%');
    expect(formatPercent(0.145, 2)).toBe('0.15%');
    expect(formatPercent(4.015, 2)).toBe('4.02%');
  });

  it('shows the empty placeholder for missing values', () => {
    expect(formatPercent(null)).toBe(METERING.GRAPH.EMPTY_VALUE);
    expect(formatPercent(undefined)).toBe(METERING.GRAPH.EMPTY_VALUE);
    expect(formatPercent(Number.NaN)).toBe(METERING.GRAPH.EMPTY_VALUE);
  });
});

describe('formatModelNativeUnits', () => {
  it('shows the bare number, with no unit suffix', () => {
    expect(formatModelNativeUnits(22625)).toBe((22625).toLocaleString());
    expect(formatModelNativeUnits(19)).toBe((19).toLocaleString());
    expect(formatModelNativeUnits(4)).toBe((4).toLocaleString());
    expect(formatModelNativeUnits(0)).toBe((0).toLocaleString());
  });

  it('shows the empty placeholder for missing values', () => {
    expect(formatModelNativeUnits(null)).toBe(METERING.GRAPH.EMPTY_VALUE);
  });
});
