/** Metering Dashboard — Application Usage (US6 / AI4IDS-2894). Lifetime-cumulative figures. */

export interface MoneyPercent {
  amount: number;
  percentage: number;
}

export interface ApplicationUsageSummary {
  totalApplications: number;
  allocatedBudget: MoneyPercent;
  spendBudget: MoneyPercent;
  remainingBudget: MoneyPercent;
  billingPeriod: string;
}

export interface ApplicationUsageListItem {
  applicationId: number;
  name: string;
  domain: string | null;
  allocatedBudget: MoneyPercent;
  spendBudget: MoneyPercent;
  remainingBudget: MoneyPercent;
}

export interface ApplicationUsageListResponse {
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
}

export interface ApplicationUsageTotals {
  allocatedBudget: number;
  spendBudget: number;
  remainingBudget: number;
}

export interface ApplicationUsageDetail {
  applicationId: number;
  applicationName: string;
  domain: string | null;
  allocatedBudget: MoneyPercent;
  spendBudget: MoneyPercent;
  remainingBudget: MoneyPercent;
  apiKeys: ApiKeyUsageItem[];
  totals: ApplicationUsageTotals;
}

export interface ApplicationUsageListParams {
  tenantId: string;
  sortOrder?: "asc" | "desc";
  limit?: number;
  offset?: number;
}
