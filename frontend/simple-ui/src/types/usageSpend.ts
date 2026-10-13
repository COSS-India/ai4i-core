import type { MeteringPeriod, MeteringPeriodEcho, MeteringTokenKey } from "./metering";

export interface SpendByTaskType {
  modelTaskType: string;
  unit: string;
  consumption: number;
  /**
   * Quota allocated for this task type this billing period, summed across tenants'
   * current tier only. Omitted when no tenant in scope has a quota snapshot for it.
   */
  allocated?: number | null;
  /** Never sent by the summary endpoint; absent on its responses. */
  remaining?: number | null;
}

export interface UsageSummaryResponse {
  billingPeriod: string | null;
  totalSpend: number;
  currency: string;
  /** Present when API supports it; otherwise derived client-side. */
  activeTenants?: number;
  budgetExceededTenants?: number;
  spendChangePercent?: number;
  spendByModelTaskType: SpendByTaskType[];
  /** Summed across tenants with a budget assignment. */
  totalAllocatedBudget?: number;
  totalRemainingBudget?: number;
}

export interface TenantBudget {
  limit: number;
  spent: number;
  remaining: number;
  percentageUsed: number;
  /** Present on single-tenant detail only. */
  budgetEffectiveFrom?: string | null;
  budgetEffectiveTo?: string | null;
}

/** Monthly quota for one task type: the current billing month, whatever the period. */
export interface TaskTypeQuota {
  /** "YYYY-MM" (UTC month, as billed). */
  billingMonth: string;
  limit: number;
  used: number;
  /** `limit − used`; negative when over quota. */
  remaining: number;
  percentageUsed: number;
}

/** One LLM token category's usage and cost in the selected period. */
export interface MeteringCostShare {
  key: MeteringTokenKey;
  /** Display label from the API, e.g. "Cached input tokens". */
  label: string;
  units: number;
  cost: number;
  /** Share of the task type's period cost, 0–100. */
  costShare: number;
}

/** A task type's usage in the selected period. */
export interface TaskTypePeriodUsage {
  units: number;
  cost: number;
  /**
   * LLM only: input (uncached), cached input and output, summing to `units`
   * and `cost`. Cached input is left out when there is none. Null otherwise.
   */
  breakdown: MeteringCostShare[] | null;
}

export interface TierTaskTypeUsage {
  taskType: string;
  unit: string;
  /** Null when the institution has no quota for this task type this month. */
  quota: TaskTypeQuota | null;
  periodUsage: TaskTypePeriodUsage;
}

export interface TenantTierBreakdown {
  tierId: string;
  tierName: string;
  taskTypes: TierTaskTypeUsage[];
}

export interface TenantUsageItem {
  tenantId: string;
  tenantName: string;
  /** Tier of the institution's most recent usage in the period. */
  tier: string;
  tierId: string;
  currency: string;
  /** Spend in the selected period. */
  periodSpend: number;
  /** All-time budget balance — not scoped by the period. */
  budget: TenantBudget;
  usage: {
    /** Distinct task types used in the period. */
    taskTypeCount: number;
  };
  /** Usage in the period: one entry per tier used, oldest first. */
  tierBreakdown: TenantTierBreakdown[];
}

export interface TenantUsageListResponse {
  period: MeteringPeriodEcho;
  data: TenantUsageItem[];
  total: number;
}

export interface TenantUsageParams {
  period: MeteringPeriod;
  tierId?: string;
  modelTaskType?: string;
  /** Comma-separated task types to include (frontend allowlist). */
  taskTypes?: string;
  /** Sorts by `periodSpend`. */
  sortOrder?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface UsageSummaryParams {
  /** Billing month in YYYY-MM format. Omit = all-time on the API. */
  billingPeriod?: string;
  tierId?: string;
  /** Comma-separated task types to include (frontend allowlist). */
  taskTypes?: string;
}

/** Single-tenant detail: a list item plus the period the API applied. */
export interface TenantUsageDetail extends TenantUsageItem {
  period: MeteringPeriodEcho;
}
