import { METERING } from "../config/meteringConstants";
import type { MeteringPeriodEcho } from "../types/metering";

/**
 * An API coverage instant (IST, +05:30) for display, in IST: "8 Oct 2026, 11:30",
 * or just the date at IST midnight.
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

/** Where the period's estimates end, in epoch seconds; null when nothing is estimated. */
export function estimatedUntilSeconds(period?: MeteringPeriodEcho | null): number | null {
  if (!period?.estimated || !period.estimatedUntil) return null;
  const ms = new Date(period.estimatedUntil).getTime();
  return Number.isNaN(ms) ? null : ms / 1000;
}

/**
 * The note a tab shows about how much of the period its figures cover, or null
 * when there's nothing to say: data missing or incomplete at the start of the
 * period (`partial` with a `dataFrom`), and figures that are estimates (`estimated`).
 * A period with no data at all is left to the tab's own empty state.
 */
export function periodCoverageNotice(period?: MeteringPeriodEcho | null): string | null {
  if (!period) return null;
  const copy = METERING.COVERAGE;
  const parts: string[] = [];
  if (period.partial && period.dataFrom) {
    parts.push(`${copy.INCOMPLETE_PREFIX} ${formatCoverageInstant(period.dataFrom)} ${copy.INCOMPLETE_SUFFIX}`);
  }
  if (period.estimated && period.estimatedUntil) {
    parts.push(`${copy.ESTIMATED_PREFIX} ${formatCoverageInstant(period.estimatedUntil)} ${copy.ESTIMATED_SUFFIX}`);
  }
  return parts.length ? parts.join(" ") : null;
}
