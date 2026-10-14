import type { MeteringPeriod, MeteringPeriodEcho, MeteringTokenKey } from "./metering";

/** One task type's quota usage in the summary's billing month. No money: quota has none. */
export interface QuotaUsageItem {
  modelTaskType: string;
  unit: string;
  /** Units used in the billing month, summed across institutions. */
  consumption: number;
  /**
   * Quota allocated for this task type, summed across institutions' current tier only.
   * Null when no institution in scope has a quota snapshot for it.
   */
  allocated: number | null;
}

/** Budget across institutions — all-time, never scoped by the billing period. */
export interface SummaryBudget {
  basis: "all_time";
  /** Institutions with a budget on file (deactivated ones left out). */
  institutions: number;
  allocated: number;
  spent: number;
  /** allocated − spent; negative when overspent overall. */
  remaining: number;
  /**
   * Institutions whose all-time spend has reached their budget (institution spend
   * >= institution budget). Not the number of institutions with blocked keys:
   * billing blocks per key, against each key's own ceiling.
   */
  exceededTenants: number;
  /**
   * With a tier filter: institutions were picked by their current tier. Null without
   * one. Differs from quota.tierFilter, so an institution whose tier was removed can
   * be missing here but present in quota.
   */
  tierFilter?: "current_tier" | null;
}

/** Quota usage in one billing month (all months when billingMonth is null). */
export interface SummaryQuota {
  basis: "billing_month" | "all_time";
  billingMonth: string | null;
  /** Institutions with quota usage in scope. */
  activeTenants: number;
  byTaskType: QuotaUsageItem[];
  /** With a tier filter: institutions were picked by the most recent tier in their quota rows. */
  tierFilter?: "most_recent_quota_tier" | null;
}

/** GET /usage-summary: budget (all-time) and quota (monthly), each with its own time basis. */
export interface UsageSummaryResponse {
  currency: string;
  budget: SummaryBudget;
  quota: SummaryQuota;
}

/** An institution's budget — all-time, never scoped by the period (that's periodSpend). */
export interface TenantBudget {
  basis?: "all_time";
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
  /** Billing month (YYYY-MM) for the quota block only; omit = all months. Budget is always all-time. */
  billingPeriod?: string;
  tierId?: string;
  /** Comma-separated task types to include (frontend allowlist). */
  taskTypes?: string;
}

/** Single-tenant detail: a list item plus the period the API applied. */
export interface TenantUsageDetail extends TenantUsageItem {
  period: MeteringPeriodEcho;
}
