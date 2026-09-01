export type ApplicationStatus = "ACTIVE" | "INACTIVE";

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
  /** Null when the list API does not include key counts. */
  api_key_count?: number | null;
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
}

export interface AllocationUpdate {
  application_id: string;
  allocated_percentage: number;
}
