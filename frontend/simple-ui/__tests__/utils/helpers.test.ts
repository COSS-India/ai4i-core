import {
  addDaysToDateInputValue,
  dateInputToStartOfDayIso,
  dateInputToEndOfDayIso,
} from '../../src/utils/helpers';

describe('dateInputToStartOfDayIso / dateInputToEndOfDayIso', () => {
  // Both helpers build the timestamp via Date.UTC, so their output does not
  // depend on the host's local timezone (unlike a plain `new Date(y, m, d)`).
  it('anchors start-of-day to UTC midnight', () => {
    expect(dateInputToStartOfDayIso('2026-08-12')).toBe('2026-08-12T00:00:00.000Z');
  });

  it('anchors end-of-day to UTC end-of-day', () => {
    expect(dateInputToEndOfDayIso('2026-08-12')).toBe('2026-08-12T23:59:59.999Z');
  });

  it('keeps effective_from/effective_to on adjacent days contiguous with no gap or overlap', () => {
    const from = dateInputToStartOfDayIso('2026-08-14');
    const to = dateInputToEndOfDayIso('2026-08-13');
    expect(new Date(from).getTime() - new Date(to).getTime()).toBe(1);
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
