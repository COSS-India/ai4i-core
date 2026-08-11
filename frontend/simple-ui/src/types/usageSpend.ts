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
