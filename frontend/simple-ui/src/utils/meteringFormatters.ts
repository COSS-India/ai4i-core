import type {
  MeteringDataState,
  MeteringGraph,
  MeteringWindow,
  ServiceConsumptionSummary,
  ServiceRow,
} from "../types/metering";
import { METERING } from "../constants";
import { meteringServiceColor } from "./meteringColors";

export const getWindowLabel = (window: MeteringWindow): string =>
  METERING.TIME_WINDOW_LABELS[window] ?? window;

export type MeteringKpiInput = string | number | null | undefined;

export interface RequestVolumeChartPoint {
  ts: number;
  label: string;
  requests: number;
  successful: number;
  failed: number;
}

/** X-axis label format per selected time window (HH:mm or DD MMM). */
export function formatMeteringAxisLabel(ts: number, window: MeteringWindow): string {
  const d = new Date(ts * 1000);
  if (window === "1h" || window === "24h") {
    const hours = String(d.getHours()).padStart(2, "0");
    const minutes = String(d.getMinutes()).padStart(2, "0");
    return `${hours}:${minutes}`;
  }
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

/** Rich tooltip timestamp — includes time for multi-day windows. */
export function formatMeteringTooltipLabel(ts: number, window: MeteringWindow): string {
  const d = new Date(ts * 1000);
  if (window === "1h" || window === "24h") {
    return formatMeteringAxisLabel(ts, window);
  }
  return d.toLocaleString([], {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
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

/** Build request volume chart rows from successful/failed counts. */
export function buildRequestVolumeChartData(
  graph?: MeteringGraph | null,
  timeWindow: MeteringWindow = METERING.DEFAULTS.TIME_WINDOW,
): RequestVolumeChartPoint[] {
  const { SUCCESSFUL, FAILED } = METERING.GRAPH.SERIES_KEYS;
  const successfulSeries = findMeteringSeries(graph, SUCCESSFUL);
  const failedSeries = findMeteringSeries(graph, FAILED);
  if (!successfulSeries?.points?.length || !failedSeries?.points?.length) return [];

  const failedByTs = indexMeteringSeriesByTs(failedSeries);

  return successfulSeries.points.map((p) => {
    const successful = Math.round(p.value);
    const failed = Math.round(failedByTs.get(p.ts) ?? 0);
    const ts = p.ts;

    return {
      ts,
      label: formatMeteringAxisLabel(ts, timeWindow),
      requests: successful + failed,
      successful,
      failed,
    };
  });
}

export function formatMeteringYTick(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(0)}K` : String(value);
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

/** Format KPI Cell.value for display (mixed types per key). */
export function formatMeteringKpiValue(
  key: string,
  value: MeteringKpiInput,
): string | number {
  if (value == null) return METERING.GRAPH.EMPTY_VALUE;
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

/** Absolute timestamp for data_state error banners. */
export function formatMeteringGeneratedAt(iso?: string | null): string {
  if (!iso?.trim()) return METERING.GRAPH.EMPTY_VALUE;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export type MeteringDataStateBanner =
  | { status: "error"; message: string }
  | { status: "info"; message: string };

/** Map API `data_state` to a dashboard banner (omit when ok). */
export function formatMeteringDataStateBanner(
  dataState: MeteringDataState | undefined,
  generatedAt?: string | null,
): MeteringDataStateBanner | null {
  switch (dataState) {
    case "error":
      return {
        status: "error",
        message: `${METERING.BANNERS.DATA_STATE.ERROR_PREFIX} ${formatMeteringGeneratedAt(generatedAt)}`,
      };
    case "empty":
      return { status: "info", message: METERING.BANNERS.DATA_STATE.EMPTY };
    case "no_history":
      return { status: "info", message: METERING.BANNERS.DATA_STATE.NO_HISTORY };
    default:
      return null;
  }
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
  mostUsed: { service: string; requests: number };
  highestFailureRate: number;
  highestFailureService: string;
}

/** Service tab KPI row — prefers API summary, derives from breakdown when absent. */
export function deriveServiceInsights(
  summary: ServiceConsumptionSummary | null | undefined,
  breakdown: ServiceRow[],
): ServiceInsights | null {
  if (summary?.most_used && summary.highest_failure_rate) {
    return {
      mostUsed: summary.most_used,
      highestFailureRate: summary.highest_failure_rate.failure_rate_pct,
      highestFailureService: summary.highest_failure_rate.service,
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
