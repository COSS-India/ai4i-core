// Raw value → display text, shared by detail screens and tables.

/** Shown wherever a field has no value. */
export const EMPTY_VALUE = "—";

/** The value, or the placeholder when it is missing or blank. */
export function dash(v?: string | null): string {
  return v && v.trim() ? v : EMPTY_VALUE;
}

/**
 * "99,999,999 audio minutes/month" for a tier quota. Units arrive as
 * catalogue ids (`audio_minutes`), so underscores read as spaces.
 */
export function formatMonthlyQuota(limit: number, unit?: string | null): string {
  const amount = limit.toLocaleString("en-US", { maximumFractionDigits: 2 });
  const label = (unit ?? "").trim().replaceAll("_", " ").toLowerCase();
  return label ? `${amount} ${label}/month` : `${amount}/month`;
}

/** Locale date-time for an ISO timestamp; the raw value if it will not parse. */
export function fmtDate(v?: string | null): string {
  if (!v) return EMPTY_VALUE;
  // An unparseable date yields "Invalid Date" rather than throwing, so test the
  // timestamp instead of relying on a catch.
  const parsed = new Date(v);
  return Number.isNaN(parsed.getTime()) ? v : parsed.toLocaleString();
}
