export interface TierQuota {
  modelTaskType: string;
  unit?: string;
  limit: number;
  pendingLimit?: number | null;
}

export type TierStatus = "INACTIVE" | "ACTIVE" | "DEACTIVATED" | "DELETED";

export interface Tier {
  id: string;
  name: string;
  description?: string;
  status?: TierStatus;
  /** Requests per minute across all rate-limited inference APIs; null = gateway default. */
  rateLimit?: number | null;
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
  rateLimit?: number;
  quotas: { modelTaskType: string; limit: number }[];
}

export interface UpdateTierPayload {
  name: string;
  description?: string;
  /** Omit to keep the stored limit; null removes it. */
  rateLimit?: number | null;
  quotas?: { modelTaskType: string; limit: number }[];
  cancel_pending_quota?: string[];
}

export interface UpdateTierStatusPayload {
  status: TierStatus;
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
  /** Empty string means no tier limit. */
  rateLimit: string;
  quotas: TierFormQuota[];
};
