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
  /** Share of the Institution budget already consumed (same unit as allocated %). */
  consumed_percentage: number;
  consumed_budget: number;
  status: ApplicationStatus;
  created_at: string;
  updated_at?: string | null;
  /** Present when the list API includes key counts; 0 until keys ship. */
  api_key_count?: number;
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
}

export interface AllocationUpdate {
  application_id: string;
  allocated_percentage: number;
}
