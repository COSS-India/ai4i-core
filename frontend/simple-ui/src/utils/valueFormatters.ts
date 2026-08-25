// Raw value → display text, shared by detail screens and tables.

/** Shown wherever a field has no value. */
export const EMPTY_VALUE = "—";

/** The value, or the placeholder when it is missing or blank. */
export function dash(v?: string | null): string {
  return v && v.trim() ? v : EMPTY_VALUE;
}

/** Locale date-time for an ISO timestamp; the raw value if it will not parse. */
export function fmtDate(v?: string | null): string {
  if (!v) return EMPTY_VALUE;
  try {
    return new Date(v).toLocaleString();
  } catch {
    return v;
  }
}
