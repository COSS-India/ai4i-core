import { useQuery } from "@tanstack/react-query";
import {
  fetchTenantsDirectory,
  TENANTS_LIST_QUERY_KEY,
  TENANTS_LIST_STALE_MS,
} from "../services/tenantService";

/**
 * Shared tenant directory. One React Query cache entry, many consumers
 * (Logs, Metering, Profile, Policy, Alerts, Tier view).
 */
export function useTenantsList(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: TENANTS_LIST_QUERY_KEY,
    queryFn: fetchTenantsDirectory,
    staleTime: TENANTS_LIST_STALE_MS,
    enabled: options?.enabled ?? true,
    retry: 1,
  });
}
