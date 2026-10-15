import { METERING } from "../config/meteringConstants";
import type { MeteringPeriodEcho } from "../types/metering";

/**
 * An API instant (IST, +05:30) for display, in IST: "8 Oct 2026, 11:30", or
 * just the date at IST midnight.
 */
export function formatCoverageInstant(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const date = d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: METERING.IST_TIME_ZONE,
  });
  const time = d.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: METERING.IST_TIME_ZONE,
  });
  return time === "00:00" ? date : `${date}, ${time}`;
}

/** The period starts before recorded usage does, so part of it is estimated. */
export function periodIncludesEstimates(period?: MeteringPeriodEcho | null): boolean {
  if (!period?.recordedFrom) return false;
  const start = new Date(period.start).getTime();
  const recordedFrom = new Date(period.recordedFrom).getTime();
  return !Number.isNaN(start) && !Number.isNaN(recordedFrom) && start < recordedFrom;
}

/** The dashboard's notice for a period that includes estimated usage, else null. */
export function estimatedUsageNotice(period?: MeteringPeriodEcho | null): string | null {
  if (!period?.recordedFrom || !periodIncludesEstimates(period)) return null;
  const copy = METERING.ESTIMATES;
  return `${copy.NOTICE_PREFIX} ${formatCoverageInstant(period.recordedFrom)} ${copy.NOTICE_SUFFIX}`;
}
