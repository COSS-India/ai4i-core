export interface SpendByTaskType {
  modelTaskType: string;
  unit: string;
  consumption: number;
  /**
   * Quota allocated for this task type this billing period, summed across tenants'
   * current tier only. Omitted when no tenant in scope has a quota snapshot for it.
   */
  allocated?: number | null;
  /**
   * Never sent by the summary endpoint; derived locally in summaryFromDetail from
   * tenant-detail tier breakdown. Absent on responses from the summary endpoint.
   */
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

/**
 * Flat quota-bar fields on the tenant usage response.
 * Populated only when the tenant used a single model task type this period;
 * left null for multi-type tenants because consumed/quotaLimit cannot be summed
 * across heterogeneous units (characters vs images vs minutes).
 */
export interface TenantUsageAggregate {
  taskTypeCount: number;
  unit?: string | null;
  quotaLimit?: number | null;
  consumed?: number | null;
  remaining?: number | null;
  percentage?: number | null;
}

export interface TierTaskTypeUsage {
  taskType: string;
  unit: string;
  quotaLimit?: number | null;
  consumed: number;
  remaining?: number | null;
}

export interface TenantTierBreakdown {
  tierId: string;
  tierName: string;
  taskTypes: TierTaskTypeUsage[];
}

export interface TenantUsageItem {
  tenantId: string;
  tenantName: string;
  tier: string;
  tierId: string;
  currency: string;
  /** All-time institution spend — not scoped by billing_period. */
  spend: number;
  budget: TenantBudget;
  /** Quota usage for the selected billing_period. */
  usage: TenantUsageAggregate;
  /** Quota breakdown for the selected billing_period. */
  tierBreakdown: TenantTierBreakdown[];
}

export interface TenantUsageListResponse {
  data: TenantUsageItem[];
  total: number;
}

export interface TenantUsageParams {
  /** Billing month in YYYY-MM format. Scopes quota usage only. */
  billingPeriod?: string;
  tierId?: string;
  modelTaskType?: string;
  /** Comma-separated task types to include (frontend allowlist). */
  taskTypes?: string;
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

/** Single-tenant detail shares the same shape as a list item. */
export type TenantUsageDetail = TenantUsageItem;
