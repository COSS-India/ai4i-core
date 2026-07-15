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

export interface TenantUsageAggregate {
  taskTypeCount: number;
  unit: string;
  quotaLimit: number;
  consumed: number;
  remaining: number;
  percentage: number;
}

export interface TierTaskTypeUsage {
  taskType: string;
  unit: string;
  quotaLimit: number;
  consumed: number;
  remaining: number;
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
  sortOrder?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface UsageSummaryParams {
  /** Billing month in YYYY-MM format. Defaults to current month server-side. */
  billingPeriod?: string;
}

/** Single-tenant detail shares the same shape as a list item. */
export type TenantUsageDetail = TenantUsageItem;
