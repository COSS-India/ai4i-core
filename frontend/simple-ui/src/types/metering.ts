/** Metering & Usage Dashboard API types (matches platform-core-service contract). */

/** IST calendar date, "YYYY-MM-DD". */
export type MeteringDayKey = string;

/** Inclusive IST date range for the Usage Dashboard custom range filter. */
export interface MeteringDateRange {
  from: MeteringDayKey;
  to: MeteringDayKey;
}

// The 4 values the API accepts
export type MeteringPeriodKey = "today" | "yesterday" | "last_7_days" | "custom";

/** The period the dashboard asks for; only "custom" carries its own dates. */
export type MeteringPeriod =
  | { key: Exclude<MeteringPeriodKey, "custom"> }
  | { key: "custom"; range: MeteringDateRange };

/** Period the API applied, echoed on every period-filtered response. */
export interface MeteringPeriodEcho {
  key: MeteringPeriodKey;
  /** First IST day, inclusive. */
  from: MeteringDayKey;
  /** Last IST day, inclusive; equals `from` for "today". */
  to: MeteringDayKey;
  /** UTC ISO start of the queried range, inclusive. */
  start: string;
  /** UTC ISO end of the queried range, exclusive. */
  end: string;
  /** Always "Asia/Kolkata". */
  timezone: string;
  /** Where the data behind the figures begins in the period (IST, +05:30); null when there is none. */
  dataFrom?: string | null;
  /** True when the data covers only part of the period (or none of it): a 0 may mean "no data". */
  partial?: boolean;
  /** True when part of the figures are estimates (days before usage was recorded, backfilled from monitoring data). */
  estimated?: boolean;
  /** Where the estimates end (exclusive, IST, +05:30); null when nothing is estimated. */
  estimatedUntil?: string | null;
}
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

/** Request-volume bucket size: hourly for a 1-day period, daily up to 31 days, weekly beyond. */
export type MeteringGraphStep = "1h" | "1d" | "1w";

export interface MeteringGraph {
  step?: MeteringGraphStep;
  series: MeteringGraphSeries[];
}

export interface MeteringScope {
  role: string;
  tenant_id: string | null;
  organisation: string | null;
  period: MeteringPeriodEcho;
  task_types?: string[] | null;
}

export interface PlatformAdoption {
  total_tenants?: number | null;
  new_tenants_15d?: number | null;
  active_24h?: number | null;
  active_7d?: number | null;
  active_30d?: number | null;
  model_usage_growth_pct?: number | null;
  /** Registered models, platform-wide. */
  total_models?: number | null;
  /** Distinct registered models with requests in the last 30 days. */
  active_models_30d?: number | null;
}

/** Key metrics read from `platform_adoption` (overview) and the usage-summary API. */
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
  /** First recorded usage for the tenant scope (UTC); null when there is none yet. */
  first_usage_at?: string | null;
  /**
   * When the scoped institution was onboarded (IST, with offset); the date
   * picker's floor. Null for the platform-wide view.
   */
  onboarded_at?: string | null;
}

/** LLM token category in a usage breakdown. */
export type MeteringTokenKey = "input" | "cached_input" | "output";

/** One token category of an LLM row on the Model tab. */
export interface MeteringTokenShare {
  key: MeteringTokenKey;
  /** Display label from the API, e.g. "Cached input tokens". */
  label: string;
  units: number;
  /** Share of the row's total tokens, 0–100. */
  percentage: number;
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
  /**
   * LLM only: input (uncached), cached input and output tokens, summing to
   * `native_units`. Cached input is left out when there is none. Null otherwise.
   */
  native_breakdown?: MeteringTokenShare[] | null;
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
  breakdown: ModelConsumptionRow[];
}
