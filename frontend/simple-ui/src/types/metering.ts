/** Metering & Usage Dashboard API types (matches platform-core-service contract). */

export type MeteringWindow = "1h" | "24h" | "7d" | "30d";
export type MeteringTopN = 5 | 10 | 25;
export type MeteringDataState = "ok" | "error" | "empty" | "no_history";

/** Top-level fields present on every metering dashboard API response. */
export interface MeteringResponseMeta {
  degraded?: boolean;
  generated_at: string;
  refresh_interval_seconds?: number;
  data_state?: MeteringDataState;
  is_stale?: boolean;
}

export interface MeteringCell {
  key: string;
  label: string;
  value: number | string | null;
  previous?: number | string | null;
  pct_change?: number | null;
}

export interface MeteringGraphPoint {
  ts: number;
  value: number;
}

export interface MeteringGraphSeries {
  key: string;
  label: string;
  points: MeteringGraphPoint[];
}

export interface MeteringGraph {
  series: MeteringGraphSeries[];
}

export interface MeteringScope {
  role: string;
  tenant_id: string | null;
  organisation: string | null;
  window: MeteringWindow;
}

export interface PlatformAdoption {
  total_tenants?: number | null;
  new_tenants_7d?: number | null;
  active_24h?: number | null;
  active_7d?: number | null;
  active_30d?: number | null;
}

export interface TenantRow {
  rank: number;
  tenant: string;
  organisation?: string | null;
  plan?: string | null;
  requests: number;
  formatted_requests: string;
  percentage: number;
}

export interface OthersData {
  count: number;
  requests: number;
  percentage: number;
}

export interface UsageConcentration {
  top_tenants: TenantRow[];
  others: OthersData;
  top_concentration_pct: number;
  grand_total: number;
}

export interface ThroughputData {
  avg_rps: number;
  peak_rps?: number | null;
  peak_at?: string | null;
}

export interface RequestHealth {
  total: number;
  successful: number;
  failed: number;
  total_formatted: string;
  successful_formatted: string;
  failed_formatted: string;
  success_rate_pct: number;
  failure_rate_pct: number;
}

export interface OverviewResponse extends MeteringResponseMeta {
  scope: MeteringScope;
  kpis: MeteringCell[];
  active_tenants: MeteringCell[];
  platform_adoption?: PlatformAdoption | null;
  usage_concentration?: UsageConcentration | null;
  request_health?: RequestHealth | null;
  request_volume?: MeteringGraph | null;
  throughput?: ThroughputData;
}

export interface ServiceEntry {
  display_name: string;
  requests: number;
  formatted_requests: string;
}

export interface TenantServiceRow {
  rank: number;
  tenant: string;
  organisation?: string | null;
  services: Record<string, ServiceEntry>;
  total: number;
  formatted_total: string;
}

export interface TenantConsumptionResponse extends MeteringResponseMeta {
  scope: MeteringScope;
  tenant_ranking: TenantRow[];
  usage_by_service: TenantServiceRow[];
  throughput?: ThroughputData;
  request_volume?: MeteringGraph | null;
}

export interface ServiceConsumptionSummary {
  active_services?: number;
  most_used?: { service: string; requests: number } | null;
  highest_failure_rate?: { service: string; failure_rate_pct: number } | null;
}

export interface ServiceRow {
  service: string;
  metering_unit: string;
  requests: number;
  percentage?: number;
  native_units?: number | null;
  native_unit_suffix: string;
  success_pct: number;
  failure_rate_pct?: number;
  failed: number;
  vs_prev_period_pct?: number | null;
}

export interface ServiceConsumptionResponse extends MeteringResponseMeta {
  scope: MeteringScope;
  summary?: ServiceConsumptionSummary | null;
  service_breakdown: ServiceRow[];
  throughput?: ThroughputData;
  request_volume?: MeteringGraph | null;
}
