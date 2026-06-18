import type { MeteringGraph, MeteringWindow } from "../types/metering";

const WINDOW_LABELS: Record<MeteringWindow, string> = {
  "1h": "last 1 hour",
  "24h": "last 24 hours",
  "7d": "last 7 days",
  "30d": "last 30 days",
};

export const getWindowLabel = (window: MeteringWindow): string =>
  WINDOW_LABELS[window] ?? window;

export interface MeteringRatePoint {
  label: string;
  rps: number;
}

/** Resolve the primary requests / RPS series from a metering graph payload. */
export function extractMeteringRequestsSeries(
  graph?: MeteringGraph | null,
): MeteringGraph["series"][number] | null {
  if (!graph?.series?.length) return null;
  return (
    graph.series.find((s) => s.key === "requests") ??
    graph.series.find((s) => s.key === "request_rate") ??
    graph.series.find((s) => /request/i.test(s.key)) ??
    graph.series[0] ??
    null
  );
}

export function extractMeteringRateChartData(
  graph?: MeteringGraph | null,
  stepFallback: MeteringWindow | string = "1h",
): MeteringRatePoint[] {
  const series = extractMeteringRequestsSeries(graph);
  if (!series?.points?.length) return [];
  const step = graph?.step ?? stepFallback;
  return series.points.map((p) => ({
    label: formatMeteringTimestamp(p.ts, step),
    rps: p.value,
  }));
}

export const METERING_RANK_COLORS = [
  "#DD6B20",
  "#3182CE",
  "#38A169",
  "#805AD5",
  "#00B5D8",
] as const;

export const METERING_SERVICE_COLORS: Record<string, string> = {
  NMT: "#38A169",
  ASR: "#FF7A61",
  TTS: "#3182CE",
  LLM: "#F061C8",
  OCR: "#319795",
  Transliteration: "#99F45A",
  Pipeline: "#805AD5",
  NER: "#9D72FF",
  "Language Detection": "#DD6B20",
  "Audio Language Detection": "#F5C554",
  "Speaker Diarization": "#718096",
  "Language Diarization": "#4FD1C5",
};

export const METERING_FALLBACK_COLORS = [
  "#DD6B20",
  "#3182CE",
  "#38A169",
  "#805AD5",
  "#D69E2E",
  "#319795",
  "#E53E3E",
  "#718096",
  "#B7791F",
  "#4FD1C5",
] as const;

export function meteringColorAt(index: number): string {
  return METERING_RANK_COLORS[index % METERING_RANK_COLORS.length];
}

export function meteringServiceColor(name: string, index: number): string {
  return METERING_SERVICE_COLORS[name] ?? METERING_FALLBACK_COLORS[index % METERING_FALLBACK_COLORS.length];
}

export function formatMeteringTimestamp(ts: number, step: string): string {
  const d = new Date(ts * 1000);
  if (step === "5m" || step === "1h") {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  }
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function formatMeteringPeakAt(peakAt?: string | null): string {
  if (!peakAt) return "—";
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
export function parseSuccessRatePct(
  rate: string | number | null | undefined,
): number | null {
  if (rate == null) return null;
  if (typeof rate === "number") return rate;
  const s = String(rate).trim();
  if (!s) return null;
  if (s.endsWith("%")) {
    const n = parseFloat(s);
    return Number.isNaN(n) ? null : n;
  }
  const n = parseFloat(s);
  return Number.isNaN(n) ? null : n;
}

export function formatSuccessRateDisplay(
  rate: string | number | null | undefined,
): string {
  const pct = parseSuccessRatePct(rate);
  if (pct == null) return "—";
  return `${pct}%`;
}

/** Format KPI Cell.value for display (mixed types per key). */
export function formatMeteringKpiValue(
  key: string,
  value: string | number | null | undefined,
): string | number {
  if (value == null) return "—";
  if (key === "success_rate") return formatSuccessRateDisplay(value);
  if (key === "avg_rps" && typeof value === "number") {
    return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  }
  return value;
}

export function formatNativeConsumption(
  nativeUnits?: number | null,
  suffix?: string | null,
): string {
  if (nativeUnits == null) return "—";
  const unit = suffix?.trim() || "";
  return unit ? `${nativeUnits.toLocaleString()} ${unit}` : nativeUnits.toLocaleString();
}

export function formatMeteringRefreshTime(iso?: string): string {
  if (!iso) return "just now";
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  return new Date(iso).toLocaleTimeString();
}

export function parseCompactTotal(total: string | number): number | null {
  if (typeof total === "number") return total;
  if (!total || total === "—") return null;
  const s = String(total).trim();
  if (s.endsWith("M")) return parseFloat(s) * 1_000_000;
  if (s.endsWith("K")) return parseFloat(s) * 1_000;
  const n = parseFloat(s);
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
