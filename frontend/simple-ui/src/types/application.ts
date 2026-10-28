export type ApplicationStatus = "ACTIVE" | "INACTIVE";

/** Requested service id → ordered fallback service ids. A missing key means no fallback. */
export type ServiceFallbackMap = Record<string, string[]>;

export interface Application {
  application_id: string;
  tenant_id: string;
  name: string;
  description: string;
  domain: string;
  /** Null = no ceiling (uncapped). */
  allocated_percentage: number | null;
  allocated_budget: number | null;
  /** Null when the list API does not include usage (do not treat as zero). */
  consumed_percentage?: number | null;
  consumed_budget?: number | null;
  status: ApplicationStatus;
  created_at: string;
  updated_at?: string | null;
  /** Active, unexpired API keys, filled from the API keys list. Null until that load finishes. */
  api_key_count?: number | null;
  /** {} when none are configured. */
  service_fallbacks: ServiceFallbackMap;
}

export interface ApplicationListResult {
  tenant_id: string;
  tenant_allocated_budget: number;
  total_allocated_percentage: number;
  applications: Application[];
  pagination: {
    page: number;
    size: number;
    total: number;
  };
}

export interface ListApplicationsParams {
  /** Name or domain contains. */
  search?: string;
  domain?: string;
  page?: number;
  size?: number;
}

export interface CreateApplicationPayload {
  name: string;
  description?: string;
  domain?: string;
  allocated_percentage?: number;
}

export interface UpdateApplicationPayload {
  name?: string;
  description?: string;
  domain?: string;
  status?: ApplicationStatus;
  /** Replaces the whole map; {} clears it. Omit to leave it unchanged. */
  service_fallbacks?: ServiceFallbackMap;
}

export interface AllocationUpdate {
  application_id: string;
  allocation: {
    type: "PERCENTAGE" | "FIXED";
    value: number;
  };
}
