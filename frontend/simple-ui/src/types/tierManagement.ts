export interface TierQuota {
  modelTaskType: string;
  unit?: string;
  limit: number;
  rateLimit?: number;
  pendingLimit?: number | null;
}

export interface Tier {
  id: string;
  name: string;
  description?: string;
  quotas: TierQuota[];
  createdAt?: string;
  updatedAt?: string;
}

export interface TiersListResponse {
  data: Tier[];
  total: number;
}

export interface CreateTierPayload {
  name: string;
  description?: string;
  quotas: { modelTaskType: string; limit: number }[];
}

export interface UpdateTierPayload {
  name: string;
  description?: string;
  quotas?: { modelTaskType: string; limit: number }[];
  cancel_pending_quota?: string[];
}

export type TierFormQuota = {
  _key?: string;
  modelTaskType: string;
  unit: string;
  limit: string;
  isExisting?: boolean;
};

export type TierFormData = {
  name: string;
  description: string;
  quotas: TierFormQuota[];
};
