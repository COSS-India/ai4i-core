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
  spendByModelTaskType: SpendByTaskType[];
}

export interface TenantUsageItem {
  tenantId: string;
  tenantName: string;
  tier: string;
  budgetLimit: number;
  spendToDate: number;
  remainingBudget: number;
  quotaLimit: number | null;
  quotaUnit: string;
  consumptionToDate: number | null;
  remainingQuota: number | null;
  currency: string;
}

export interface TenantUsageListResponse {
  data: TenantUsageItem[];
  total: number;
}

export interface TenantUsageParams {
  /** Billing month in YYYY-MM format. Defaults to current month server-side. */
  billingPeriod?: string;
  tier?: string;
  modelTaskType?: string;
}

export interface UsageSummaryParams {
  /** Billing month in YYYY-MM format. Defaults to current month server-side. */
  billingPeriod?: string;
}

export interface TenantBreakdownItem {
  modelTaskType: string;
  consumptionToDate: number;
  unit: string;
  spend: number;
  quotaLimit?: number | null;
  remainingQuota?: number | null;
}

export interface TenantUsageDetail extends TenantUsageItem {
  breakdown?: TenantBreakdownItem[];
}
