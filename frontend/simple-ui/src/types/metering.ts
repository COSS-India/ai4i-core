/** Metering & Usage Dashboard API types (matches platform-core-service contract). */

export type MeteringWindow = "1h" | "24h" | "7d" | "30d";
export type MeteringTopN = 10 | 25;
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
  helper?: string | null;        // optional dynamic sub-text (e.g. "97.40% success rate")
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
  task_types?: string[] | null;
}

export interface PlatformAdoption {
  total_tenants?: number | null;
  new_tenants_15d?: number | null;
  active_24h?: number | null;
  active_7d?: number | null;
  active_30d?: number | null;
  model_usage_growth_pct?: number | null;
}

/** Composed client-side from model-consumption (30d) and usage-summary APIs. */
export interface KeyMetricsSupplement {
  total_models?: number | null;
  active_models_30d?: number | null;
  tenants_budget_exhausted?: number | null;
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

/** Per-service row from GET /metering/model-consumption (no roll-up by model_name). */
export interface ModelConsumptionRow {
  service_id: string;
  name: string;
  model_name?: string | null;
  /** Registry task type from `mm_models.task["type"]`; null when unresolved. */
  task_type?: string | null;
  requests: number;
  native_units: number;
  native_unit_suffix: string;
  success_pct: number;
  failure_rate_pct: number;
}

/** Model-level ranking row from GET /metering/model-consumption (`top_models`). */
export interface TopModelRow {
  rank: number;
  model_name: string;
  /** From API when available; used for task-type filtering on the ranked list. */
  task_type?: string | null;
  consumption_pct: number;
  requests: number;
  formatted_requests: string;
}

/** Task-type rollup from GET /metering/model-consumption (`usage_by_task_type`). */
export interface TaskTypeUsageRow {
  rank: number;
  task_type: string;
  consumption_pct: number;
  requests: number;
  formatted_requests: string;
}

export type ModelTopN = 5 | 10;

export interface ModelConsumptionSummary {
  /** Registered model versions for enabled task types (platform-wide, not tenant-scoped). */
  total_models?: number | null;
  /** Distinct model_ids among model_totals with traffic in-window — same version grain as total_models. */
  active_models?: number | null;
  most_used?: {
    service_id?: string | null;
    name?: string | null;
    requests: number;
  } | null;
  /** Request-weighted success across all services with traffic. */
  overall_success_rate_pct?: number | null;
}

/** GET /api/v1/metering/model-consumption — no throughput/request_volume. */
export interface ModelConsumptionResponse extends MeteringResponseMeta {
  scope: MeteringScope;
  summary?: ModelConsumptionSummary | null;
  top_models?: TopModelRow[];
  /** Denominator for `top_models[].consumption_pct` (resolved-model traffic only). */
  top_models_total_requests?: number;
  /** Request share by model task type — powers the Model consumption donut (AI4IDS-2979). */
  usage_by_task_type?: TaskTypeUsageRow[];
  breakdown: ModelConsumptionRow[];
}
