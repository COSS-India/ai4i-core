import { apiClient } from './api';

export interface TierPricingDetail {
  service_id: string;
  service_name: string;
  cost_per_unit: number;
  unit_type: string;
}

export interface PricingSummaryRow {
  task_type: string;
  unit_type: string;
  tier_1: TierPricingDetail | null;
  tier_2: TierPricingDetail | null;
}

export async function getPricingSummary(): Promise<PricingSummaryRow[]> {
  const { data } = await apiClient.get<PricingSummaryRow[]>(
    '/api/v1/model-management/pricing-summary'
  );
  return data;
}
