import type { MeteringDateRange, MeteringDayKey, MeteringPeriod } from "../types/metering";

/**
 * Usage Dashboard custom date range helpers. All calendar dates are IST days
 * ("YYYY-MM-DD"), independent of the browser's time zone.
 */

const IST_OFFSET_MS = 330 * 60_000;
const DAY_MS = 86_400_000;

const MONTHS_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const;

export interface MeteringCalendarMonth {
  year: number;
  /** 0-based, as in Date. */
  month: number;
}

function utcMsToDayKey(ms: number): MeteringDayKey {
  return new Date(ms).toISOString().slice(0, 10);
}

/** IST calendar date of an instant. */
export function istDayKey(ms: number): MeteringDayKey {
  return utcMsToDayKey(ms + IST_OFFSET_MS);
}

/** Inclusive IST days a custom range may use; `max` is today. */
export interface PickableDays {
  min: MeteringDayKey;
  max: MeteringDayKey;
}

/** Whether the custom range picker lets a day be clicked: any day in [min, max]. */
export function isPickableDay(day: MeteringDayKey, pickable: PickableDays): boolean {
  return day >= pickable.min && day <= pickable.max;
}

/** Inclusive IST range of `dayCount` days ending today. */
export function istRangeEndingToday(dayCount: number, nowMs = Date.now()): MeteringDateRange {
  const to = istDayKey(nowMs);
  const fromMs = Date.parse(`${to}T00:00:00.000Z`) - (dayCount - 1) * DAY_MS;
  return { from: utcMsToDayKey(fromMs), to };
}

/** `period` query params; `from`/`to` (IST dates) are sent only for "custom". */
export function buildPeriodParams(period: MeteringPeriod): Record<string, string> {
  if (period.key !== "custom") return { period: period.key };
  return { period: period.key, from: period.range.from, to: period.range.to };
}

/** React Query key parts for a period; a custom range is keyed by its dates. */
export function periodQueryKeyParts(period: MeteringPeriod): string[] {
  return period.key === "custom" ? [period.key, period.range.from, period.range.to] : [period.key];
}

function formatDayMonth(key: MeteringDayKey): string {
  const [, m, d] = key.split("-");
  return `${d} ${MONTHS_SHORT[Number(m) - 1]}`;
}

/** "05 Aug 2026", "05 Aug – 20 Sep 2026", or "20 Dec 2025 – 05 Jan 2026". */
export function formatMeteringDateRange(range: MeteringDateRange): string {
  const fromYear = range.from.slice(0, 4);
  const toYear = range.to.slice(0, 4);
  if (range.from === range.to) return `${formatDayMonth(range.from)} ${fromYear}`;
  const start = fromYear === toYear ? formatDayMonth(range.from) : `${formatDayMonth(range.from)} ${fromYear}`;
  return `${start} – ${formatDayMonth(range.to)} ${toYear}`;
}

export function monthOfDayKey(key: MeteringDayKey): MeteringCalendarMonth {
  const [y, m] = key.split("-").map(Number);
  return { year: y, month: m - 1 };
}

export function shiftMonth(value: MeteringCalendarMonth, delta: number): MeteringCalendarMonth {
  const index = value.year * 12 + value.month + delta;
  return { year: Math.floor(index / 12), month: ((index % 12) + 12) % 12 };
}

export function compareMonths(a: MeteringCalendarMonth, b: MeteringCalendarMonth): number {
  return a.year * 12 + a.month - (b.year * 12 + b.month);
}

/** Clamp a month into [min, max] (inclusive). */
export function clampMonth(
  value: MeteringCalendarMonth,
  min: MeteringCalendarMonth,
  max: MeteringCalendarMonth,
): MeteringCalendarMonth {
  if (compareMonths(value, min) < 0) return min;
  if (compareMonths(value, max) > 0) return max;
  return value;
}

/**
 * Short month name for a 0-based month, e.g. 7 → "Aug". Same names as the
 * range label (Intl's en-GB would give "Sept").
 */
export function formatMonthName(month: number): string {
  return MONTHS_SHORT[month];
}

export function formatCalendarMonth(value: MeteringCalendarMonth): string {
  return new Date(Date.UTC(value.year, value.month, 1)).toLocaleDateString("en-GB", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** Month grid in Monday-first weeks; null pads the leading/trailing cells. */
export function buildCalendarWeeks(value: MeteringCalendarMonth): (MeteringDayKey | null)[][] {
  const first = Date.UTC(value.year, value.month, 1);
  const daysInMonth = new Date(Date.UTC(value.year, value.month + 1, 0)).getUTCDate();
  const leading = (new Date(first).getUTCDay() + 6) % 7;
  const cells: (MeteringDayKey | null)[] = Array.from({ length: leading }, () => null);
  for (let d = 0; d < daysInMonth; d += 1) {
    cells.push(utcMsToDayKey(first + d * DAY_MS));
  }
  while (cells.length % 7) cells.push(null);
  const weeks: (MeteringDayKey | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}
