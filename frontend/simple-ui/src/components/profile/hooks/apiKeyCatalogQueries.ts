import { listApplications } from "../../../services/applicationService";
import authService from "../../../services/authService";
import type { Application } from "../../../types/application";
import type { Permission } from "../../../types/auth";

/** Shared by the API key list and the create form so opening Create does not refetch. */
export const API_KEY_PERMISSIONS_QUERY_KEY = ["api-key-permission-catalog"] as const;

export function tenantApplicationsQueryKey(tenantId: string) {
  return ["api-key-tenant-applications", tenantId] as const;
}

export const API_KEY_CATALOG_STALE_MS = 60 * 1000;

export async function fetchPermissionCatalog(): Promise<Permission[]> {
  const permsList = await authService.getAllPermissions();
  return Array.isArray(permsList) ? permsList : [];
}

export async function fetchTenantApplications(tenantId: string): Promise<Application[]> {
  const result = await listApplications(tenantId);
  return result.applications;
}
