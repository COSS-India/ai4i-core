import type { MeteringGraph, MeteringWindow, ServiceConsumptionSummary, ServiceRow } from "../types/metering";
import { METERING } from "../constants";

export const getWindowLabel = (window: MeteringWindow): string =>
  METERING.TIME_WINDOW_LABELS[window] ?? window;

export type MeteringKpiInput = string | number | null | undefined;

export interface RequestVolumeChartPoint {
  label: string;
  successful: number;
  failed: number;
}

/** Map graph series points by timestamp for aligned multi-series charts. */
export function indexMeteringSeriesByTs(
  series?: MeteringGraph["series"][number] | null,
): Map<number, number> {
  const map = new Map<number, number>();
  (series?.points ?? []).forEach((p) => map.set(p.ts, p.value));
  return map;
}

export function findMeteringSeries(
  graph: MeteringGraph | null | undefined,
  key: string,
): MeteringGraph["series"][number] | null {
  return graph?.series?.find((s) => s.key === key) ?? null;
}

/** Build request volume chart rows from the successful / failed count series. */
export function buildRequestVolumeChartData(
  graph?: MeteringGraph | null,
): RequestVolumeChartPoint[] {
  if (!graph?.series?.length) return [];

  const successfulSeries = findMeteringSeries(
    graph,
    METERING.GRAPH.SERIES_KEYS.SUCCESSFUL,
  );
  const failedSeries = findMeteringSeries(
    graph,
    METERING.GRAPH.SERIES_KEYS.FAILED,
  );

  const failedByTs = indexMeteringSeriesByTs(failedSeries);

  // Build the timeline from whichever series has points (they share timestamps).
  const baseSeries = successfulSeries ?? failedSeries;
  if (!baseSeries?.points?.length) return [];

  const successfulByTs = indexMeteringSeriesByTs(successfulSeries);

  return baseSeries.points.map((p) => ({
    label: formatMeteringTimestamp(p.ts, graph.step),
    successful: successfulByTs.get(p.ts) ?? 0,
    failed: failedByTs.get(p.ts) ?? 0,
  }));
}

/** Parse a Prometheus duration step (e.g. "10m", "4h", "1d") into seconds. */
function meteringStepSeconds(step: string): number {
  const match = /^(\d+)([smhd])$/.exec(step.trim());
  if (!match) return 0;
  const unitSeconds: Record<string, number> = { s: 1, m: 60, h: 3600, d: 86400 };
  return Number(match[1]) * (unitSeconds[match[2]] ?? 0);
}

/**
 * Label a chart bucket based on its step width, so the axis matches the window:
 *   - day-or-larger buckets (7d → 1d, 30d-as-weekly → 7d): date only ("17 Jun")
 *   - 6h buckets (30d window): date + time, since they span many days ("25 Jun, 16:36")
 *   - intraday buckets (1h → 10m, 24h → 4h): time of day ("18:12")
 * Keying off the step's duration (not exact string match) keeps labels correct even
 * for steps not enumerated in METERING.GRAPH.STEP, including stale cached responses.
 */
export function formatMeteringTimestamp(ts: number, step: string): string {
  const d = new Date(ts * 1000);
  const stepSeconds = meteringStepSeconds(step);
  if (stepSeconds >= 86_400) {
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  }
  if (stepSeconds >= 6 * 3_600) {
    return d.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

/** Format throughput / RPS values (supports sub-unit rates from API). */
export function formatMeteringRps(value?: number | null): string | number {
  if (value == null) return METERING.GRAPH.EMPTY_VALUE;
  if (value >= 1) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

/** Prefer organisation name; fall back to tenant id/slug or lookup table. */
export function formatTenantLabel(
  tenant: string,
  organisation?: string | null,
  organisationByTenantId?: Record<string, string>,
): string {
  const org =
    organisation?.trim() ||
    organisationByTenantId?.[tenant]?.trim() ||
    organisationByTenantId?.[String(tenant)]?.trim();
  return org || tenant;
}

/** Parse success rate from API Cell.value (number or "99.1%" string). */
export function parseSuccessRatePct(rate: MeteringKpiInput): number | null {
  if (rate == null) return null;
  if (typeof rate === "number") return rate;
  const s = String(rate).trim();
  if (!s) return null;
  if (s.endsWith("%")) {
    const n = Number.parseFloat(s);
    return Number.isNaN(n) ? null : n;
  }
  const n = Number.parseFloat(s);
  return Number.isNaN(n) ? null : n;
}

export function formatSuccessRateDisplay(rate: MeteringKpiInput): string {
  const pct = parseSuccessRatePct(rate);
  if (pct == null) return METERING.GRAPH.EMPTY_VALUE;
  return `${pct}%`;
}

/** Format KPI Cell.value for display (mixed types per key). */
export function formatMeteringKpiValue(
  key: string,
  value: MeteringKpiInput,
): string | number {
  if (value == null) return METERING.GRAPH.EMPTY_VALUE;
  if (key === METERING.KPI.KEYS.SUCCESS_RATE) return formatSuccessRateDisplay(value);
  if (
    (key === METERING.KPI.KEYS.AVG_RPS || key === "avg_rps") &&
    typeof value === "number"
  ) {
    return formatMeteringRps(value);
  }
  return value;
}

export function formatNativeConsumption(
  nativeUnits?: number | null,
  suffix?: string | null,
): string {
  if (nativeUnits == null) return METERING.GRAPH.EMPTY_VALUE;
  const unit = suffix?.trim() || "";
  return unit ? `${nativeUnits.toLocaleString()} ${unit}` : nativeUnits.toLocaleString();
}

export function formatMeteringRefreshTime(iso?: string): string {
  if (!iso) return METERING.REFRESH.JUST_NOW;
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return METERING.REFRESH.JUST_NOW;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}${METERING.REFRESH.MINUTES_AGO_SUFFIX}`;
  return new Date(iso).toLocaleTimeString();
}

/** Pick the latest `generated_at` among active metering endpoint responses. */
export function resolveMeteringGeneratedAt(
  timestamps: (string | undefined | null)[],
): string | undefined {
  let latest: string | undefined;
  let latestMs = Number.NEGATIVE_INFINITY;

  for (const value of timestamps) {
    const trimmed = value?.trim();
    if (!trimmed) continue;
    const ms = new Date(trimmed).getTime();
    if (Number.isNaN(ms) || ms <= latestMs) continue;
    latestMs = ms;
    latest = trimmed;
  }

  return latest;
}

export function formatMeteringLastRefreshed(
  timestamps: (string | undefined | null)[],
): string {
  return formatMeteringRefreshTime(resolveMeteringGeneratedAt(timestamps));
}

/** Compact number display — `indian` uses Cr/L suffixes for service metrics. */
export function formatCompactNumber(
  n: number,
  variant: "default" | "indian" = "default",
): string {
  if (variant === "indian") {
    if (n >= 10_000_000) return `${(n / 10_000_000).toFixed(2)}Cr`;
    if (n >= 100_000) return `${(n / 100_000).toFixed(2)}L`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return n.toLocaleString();
  }
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

export interface ServiceInsights {
  // null in the empty-state (no service had traffic in the window).
  mostUsed: { service: string; requests: number } | null;
  highestFailureRate: number | null;
  highestFailureService: string | null;
}

/** Service tab KPI row — prefers API summary, derives from breakdown when absent. */
export function deriveServiceInsights(
  summary: ServiceConsumptionSummary | null | undefined,
  breakdown: ServiceRow[],
): ServiceInsights | null {
  if (summary) {
    return {
      mostUsed: summary.most_used,
      highestFailureRate: summary.highest_failure_rate?.failure_rate_pct ?? null,
      highestFailureService: summary.highest_failure_rate?.service ?? null,
    };
  }
  if (!breakdown.length) return null;

  const mostUsed = [...breakdown].sort((a, b) => b.requests - a.requests)[0];
  const highestFailure = [...breakdown].sort(
    (a, b) =>
      (a.failure_rate_pct ?? 100 - a.success_pct) -
      (b.failure_rate_pct ?? 100 - b.success_pct),
  )[0];

  if (!mostUsed || !highestFailure) return null;

  return {
    mostUsed: { service: mostUsed.service, requests: mostUsed.requests },
    highestFailureRate: highestFailure.failure_rate_pct ?? 100 - highestFailure.success_pct,
    highestFailureService: highestFailure.service,
  };
}

export function serviceFailureRate(row: ServiceRow): number {
  return row.failure_rate_pct ?? 100 - row.success_pct;
}
