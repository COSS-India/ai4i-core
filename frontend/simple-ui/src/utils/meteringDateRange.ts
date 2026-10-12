import { METERING } from "../config/meteringConstants";
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

function dayKeyToUtcMs(key: MeteringDayKey): number {
  const [y, m, d] = key.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
}

function utcMsToDayKey(ms: number): MeteringDayKey {
  return new Date(ms).toISOString().slice(0, 10);
}

/** IST calendar date of an instant. */
export function istDayKey(ms: number): MeteringDayKey {
  return utcMsToDayKey(ms + IST_OFFSET_MS);
}

export function addDays(key: MeteringDayKey, days: number): MeteringDayKey {
  return utcMsToDayKey(dayKeyToUtcMs(key) + days * DAY_MS);
}

/** Inclusive day count of a range (a single day is 1). */
export function rangeLengthDays(range: MeteringDateRange): number {
  return Math.round((dayKeyToUtcMs(range.to) - dayKeyToUtcMs(range.from)) / DAY_MS) + 1;
}

/** Inclusive IST days a custom range may use; `max` is yesterday. */
export interface PickableDays {
  min: MeteringDayKey | null;
  max: MeteringDayKey;
}

/**
 * Whether the custom range picker lets a day be clicked. Only days in
 * [min, max] are — today is not, as the API serves it only as `period=today`.
 * While the end is being picked (a start but no end yet), days before the
 * start, or past the longest allowed range, are not either.
 */
export function isPickableDay(
  day: MeteringDayKey,
  pickable: PickableDays,
  start: MeteringDayKey | null,
  end: MeteringDayKey | null,
): boolean {
  if (day > pickable.max || (pickable.min != null && day < pickable.min)) return false;
  if (start == null || end != null) return true;
  return day >= start && day <= addDays(start, METERING.CUSTOM_RANGE.MAX_DAYS - 1);
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

/**
 * IST days a period covers. "last_7_days" is the 7 days ending yesterday —
 * today is excluded.
 */
export function periodToDateRange(
  period: MeteringPeriod,
  nowMs: number = Date.now(),
): MeteringDateRange {
  const today = istDayKey(nowMs);
  switch (period.key) {
    case "today":
      return { from: today, to: today };
    case "yesterday": {
      const yesterday = addDays(today, -1);
      return { from: yesterday, to: yesterday };
    }
    case "last_7_days":
      return { from: addDays(today, -7), to: addDays(today, -1) };
    case "custom":
      return period.range;
  }
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
