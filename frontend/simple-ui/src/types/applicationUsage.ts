/**
 * Metering Dashboard — Application Usage (US6 / AI4IDS-2894). Allocated, spend
 * and remaining budget are lifetime figures; `periodSpend` is for the period.
 */
import type { MeteringPeriod, MeteringPeriodEcho } from "./metering";

export interface MoneyPercent {
  amount: number;
  percentage: number;
}

export interface ApplicationUsageSummary {
  period: MeteringPeriodEcho;
  totalApplications: number;
  allocatedBudget: MoneyPercent;
  spendBudget: MoneyPercent;
  remainingBudget: MoneyPercent;
  /** Spend across all applications in the period; % of the institution budget. */
  periodSpend: MoneyPercent;
  /** Always "lifetime"; describes `spendBudget` / `remainingBudget`. */
  billingPeriod: string;
}

export interface ApplicationUsageListItem {
  applicationId: number;
  name: string;
  domain: string | null;
  allocatedBudget: MoneyPercent;
  spendBudget: MoneyPercent;
  remainingBudget: MoneyPercent;
  /** Spend in the period; % of this application's allocation. */
  periodSpend: MoneyPercent;
}

export interface ApplicationUsageListResponse {
  period: MeteringPeriodEcho;
  data: ApplicationUsageListItem[];
  total: number;
}

export interface ApiKeyUsageItem {
  keyId: number;
  keyName: string;
  maskedKey: string;
  isActive: boolean;
  allocatedBudget: MoneyPercent;
  spendBudget: MoneyPercent;
  remainingBudget: MoneyPercent;
  /** Spend in the period; % of this key's allocation. */
  periodSpend: MoneyPercent;
}

export interface ApplicationUsageTotals {
  allocatedBudget: number;
  spendBudget: number;
  remainingBudget: number;
  /** Σ keys, period. */
  periodSpend: number;
}

export interface ApplicationUsageDetail {
  period: MeteringPeriodEcho;
  applicationId: number;
  applicationName: string;
  domain: string | null;
  allocatedBudget: MoneyPercent;
  spendBudget: MoneyPercent;
  remainingBudget: MoneyPercent;
  /** Spend in the period; % of the application's allocation. */
  periodSpend: MoneyPercent;
  apiKeys: ApiKeyUsageItem[];
  totals: ApplicationUsageTotals;
}

export interface ApplicationUsageListParams {
  tenantId: string;
  /** Omitted outside the Usage Dashboard, where only the lifetime figures are read. */
  period?: MeteringPeriod;
  sortOrder?: "asc" | "desc";
  limit?: number;
  offset?: number;
}
