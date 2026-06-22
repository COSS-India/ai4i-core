import type { MeteringGraph, MeteringWindow, ServiceConsumptionSummary, ServiceRow } from "../types/metering";
import { METERING } from "../config/meteringConstants";
import { meteringServiceColor } from "./meteringColors";

export const getWindowLabel = (window: MeteringWindow): string =>
  METERING.TIME_WINDOW_LABELS[window] ?? window;

export type MeteringKpiInput = string | number | null | undefined;

export interface MeteringRatePoint {
  label: string;
  rps: number;
}

export interface RequestVolumeChartPoint {
  label: string;
  requests: number;
  failureRate?: number | null;
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

/** Build request volume chart rows; joins failure_rate to requests by timestamp. */
export function buildRequestVolumeChartData(
  graph?: MeteringGraph | null,
): RequestVolumeChartPoint[] {
  const requestsSeries = extractMeteringRequestsSeries(graph);
  if (!requestsSeries?.points?.length || !graph) return [];

  const failureByTs = indexMeteringSeriesByTs(
    findMeteringSeries(graph, METERING.GRAPH.SERIES_KEYS.FAILURE_RATE),
  );

  return requestsSeries.points.map((p) => ({
    label: formatMeteringTimestamp(p.ts, graph.step),
    requests: p.value,
    failureRate: failureByTs.get(p.ts) ?? null,
  }));
}

/** Resolve the primary requests / RPS series from a metering graph payload. */
export function extractMeteringRequestsSeries(
  graph?: MeteringGraph | null,
): MeteringGraph["series"][number] | null {
  if (!graph?.series?.length) return null;
  const { REQUESTS, REQUEST_RATE } = METERING.GRAPH.SERIES_KEYS;
  return (
    graph.series.find((s) => s.key === REQUESTS) ??
    graph.series.find((s) => s.key === REQUEST_RATE) ??
    graph.series.find((s) => /request/i.test(s.key)) ??
    graph.series[0] ??
    null
  );
}

export function extractMeteringRateChartData(
  graph?: MeteringGraph | null,
  stepFallback: string = METERING.GRAPH.STEP.ONE_HOUR,
): MeteringRatePoint[] {
  const series = extractMeteringRequestsSeries(graph);
  if (!series?.points?.length) return [];
  const step = graph?.step ?? stepFallback;
  return series.points.map((p) => ({
    label: formatMeteringTimestamp(p.ts, step),
    rps: p.value,
  }));
}

export function formatMeteringTimestamp(ts: number, step: string): string {
  const d = new Date(ts * 1000);
  if (
    step === METERING.GRAPH.STEP.FIVE_MINUTES ||
    step === METERING.GRAPH.STEP.ONE_HOUR
  ) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  }
  if (step === METERING.GRAPH.STEP.SIX_HOURS) {
    return d.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

/** Format throughput / RPS values (supports sub-unit rates from API). */
export function formatMeteringRps(value?: number | null): string | number {
  if (value == null) return METERING.GRAPH.EMPTY_VALUE;
  if (value >= 1) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

export function formatMeteringPeakAt(peakAt?: string | null): string {
  if (!peakAt) return METERING.GRAPH.EMPTY_VALUE;
  // API returns bucket labels (e.g. H-3, D-2, M-5), not timestamps.
  if (/^[HDM]-\d+$/i.test(peakAt.trim())) {
    return peakAt.trim();
  }
  try {
    const d = new Date(peakAt);
    if (Number.isNaN(d.getTime())) return peakAt;
    return d.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return peakAt;
  }
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

/** Failure rate label for request health summary cards. */
export function formatFailureRateDisplay(
  requestHealth?: { failure_rate_pct: number } | null,
  successPct?: number | null,
): string {
  if (requestHealth) {
    return `${requestHealth.failure_rate_pct.toFixed(2)}%`;
  }
  if (successPct != null) {
    return `${(100 - successPct).toFixed(2)}%`;
  }
  return METERING.GRAPH.EMPTY_VALUE;
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

export function parseCompactTotal(total: string | number): number | null {
  if (typeof total === "number") return total;
  if (!total || total === METERING.GRAPH.EMPTY_VALUE) return null;
  const s = String(total).trim();
  if (s.endsWith("M")) return Number.parseFloat(s) * 1_000_000;
  if (s.endsWith("K")) return Number.parseFloat(s) * 1_000;
  const n = Number.parseFloat(s);
  return Number.isNaN(n) ? null : n;
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

export interface ServiceChartSlice {
  name: string;
  value: number;
  color: string;
  pct: number;
}

/** Donut + legend data for service breakdown charts. */
export function buildServiceBreakdownChart(breakdown: ServiceRow[]): {
  slices: ServiceChartSlice[];
  totalRequests: number;
} {
  const totalRequests = breakdown.reduce((sum, s) => sum + s.requests, 0);
  const slices = breakdown.map((s, i) => {
    const value = s.requests;
    const pct =
      s.percentage ?? (totalRequests > 0 ? (value / totalRequests) * 100 : 0);
    return {
      name: s.service,
      value,
      color: meteringServiceColor(s.service, i),
      pct,
    };
  });
  return { slices, totalRequests };
}

export interface ServiceInsights {
  activeCount: number;
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
      activeCount: summary.active_services,
      mostUsed: summary.most_used,
      highestFailureRate: summary.highest_failure_rate?.failure_rate_pct ?? null,
      highestFailureService: summary.highest_failure_rate?.service ?? null,
    };
  }
  if (!breakdown.length) return null;

  const active = breakdown.filter((s) => s.requests > 0);
  const mostUsed = [...breakdown].sort((a, b) => b.requests - a.requests)[0];
  const highestFailure = [...breakdown].sort(
    (a, b) =>
      (a.failure_rate_pct ?? 100 - a.success_pct) -
      (b.failure_rate_pct ?? 100 - b.success_pct),
  )[0];

  if (!mostUsed || !highestFailure) return null;

  return {
    activeCount: active.length,
    mostUsed: { service: mostUsed.service, requests: mostUsed.requests },
    highestFailureRate: highestFailure.failure_rate_pct ?? 100 - highestFailure.success_pct,
    highestFailureService: highestFailure.service,
  };
}

export function serviceFailureRate(row: ServiceRow): number {
  return row.failure_rate_pct ?? 100 - row.success_pct;
}
