export interface SpendByTaskType {
  modelTaskType: string;
  unit: string;
  consumption: number;
  spend: number;
  percentage: number;
}

export interface UsageSummaryResponse {
  billingPeriod: string;
  totalSpend: number;
  currency: string;
  /** Present when API supports it; otherwise derived client-side. */
  activeTenants?: number;
  budgetExceededTenants?: number;
  spendChangePercent?: number;
  spendByModelTaskType: SpendByTaskType[];
  /** Summed across tenants with a budget assignment covering this billing period. */
  totalAllocatedBudget?: number;
  totalRemainingBudget?: number;
  /**
   * Only populated when the response is scoped to a single task type (either one
   * `taskTypes` value was requested, or only one type had usage this period) —
   * different task types use incompatible units, so these are omitted otherwise.
   */
  tokenUnit?: string | null;
  totalUsedTokens?: number | null;
  totalAllocatedTokens?: number | null;
  totalRemainingTokens?: number | null;
}

export interface TenantBudget {
  limit: number;
  spent: number;
  remaining: number;
  percentageUsed: number;
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
  percentage: number;
  spend: number;
}

export interface TenantTierBreakdown {
  tierId: string;
  tierName: string;
  spend: number;
  taskTypes: TierTaskTypeUsage[];
}

export interface TenantUsageItem {
  tenantId: string;
  tenantName: string;
  tier: string;
  tierId: string;
  currency: string;
  spend: number;
  budget: TenantBudget;
  usage: TenantUsageAggregate;
  tierBreakdown: TenantTierBreakdown[];
  /**
   * Flat mirrors of budget.limit/remaining and usage.quotaLimit/consumed/remaining,
   * named identically to UsageSummaryResponse's totals — same "Total allocated / used /
   * remaining" field set whether the card is showing platform-wide or single-tenant data.
   */
  totalAllocatedBudget?: number;
  totalRemainingBudget?: number;
  tokenUnit?: string | null;
  totalUsedTokens?: number | null;
  totalAllocatedTokens?: number | null;
  totalRemainingTokens?: number | null;
}

export interface TenantUsageListResponse {
  data: TenantUsageItem[];
  total: number;
}

export interface TenantUsageParams {
  /** Billing month in YYYY-MM format. Defaults to current month server-side. */
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
  /** Billing month in YYYY-MM format. Defaults to current month server-side. */
  billingPeriod?: string;
  /** Comma-separated task types to include (frontend allowlist). */
  taskTypes?: string;
}

/** Single-tenant detail shares the same shape as a list item. */
export type TenantUsageDetail = TenantUsageItem;
