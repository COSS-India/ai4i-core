/** Metering & Usage Dashboard API types (matches platform-core-service contract). */

export type MeteringWindow = "1h" | "24h" | "7d" | "30d";
export type MeteringTopN = 5 | 10 | 25;

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
  step: string;
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

export interface OverviewResponse {
  scope: MeteringScope;
  kpis: MeteringCell[];
  platform_adoption?: PlatformAdoption | null;
  usage_concentration?: UsageConcentration | null;
  request_volume?: MeteringGraph | null;
  degraded?: boolean;
  generated_at: string;
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

export interface TenantConsumptionResponse {
  scope: MeteringScope;
  tenant_ranking: TenantRow[];
  usage_by_service: TenantServiceRow[];
  degraded?: boolean;
  generated_at: string;
}

export interface ServiceConsumptionSummary {
  // null in the empty-state (no service has traffic in the window).
  most_used: { service: string; requests: number } | null;
  highest_failure_rate: { service: string; failure_rate_pct: number } | null;
}

export interface ServiceRow {
  service: string;
  requests: number;
  native_units?: number | null;
  native_unit_suffix: string;
  success_pct: number;
  failure_rate_pct?: number;
}

export interface ServiceConsumptionResponse {
  scope: MeteringScope;
  summary?: ServiceConsumptionSummary | null;
  service_breakdown: ServiceRow[];
  degraded?: boolean;
  generated_at: string;
}
