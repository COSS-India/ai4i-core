import {
  addDaysToDateInputValue,
  getTodayDateInputValue,
} from '../../src/utils/helpers';

describe('getTodayDateInputValue', () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it('returns today in YYYY-MM-DD format', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-08-11T10:00:00'));
    expect(getTodayDateInputValue()).toBe('2026-08-11');
  });

  it('pads single-digit months and days', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-01-05T10:00:00'));
    expect(getTodayDateInputValue()).toBe('2026-01-05');
  });
});

describe('addDaysToDateInputValue', () => {
  it('adds a single day', () => {
    expect(addDaysToDateInputValue('2026-08-11', 1)).toBe('2026-08-12');
  });

  it('adds multiple days', () => {
    expect(addDaysToDateInputValue('2026-08-11', 5)).toBe('2026-08-16');
  });

  it('rolls over into the next month', () => {
    expect(addDaysToDateInputValue('2026-08-31', 1)).toBe('2026-09-01');
  });

  it('rolls over into the next year', () => {
    expect(addDaysToDateInputValue('2026-12-31', 1)).toBe('2027-01-01');
  });

  it('supports negative offsets', () => {
    expect(addDaysToDateInputValue('2026-08-11', -1)).toBe('2026-08-10');
  });

  it('handles leap day rollover', () => {
    expect(addDaysToDateInputValue('2028-02-28', 1)).toBe('2028-02-29');
  });
});
