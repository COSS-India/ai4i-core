import type { TenantView } from "../../../../types/tenant";

export const USER_EMAIL_PAGE_SIZE = 100;
export const DEFAULT_TENANT_USER_ROLE = "USER" as const;

export interface TenantManagementUser {
  user_id?: string;
  tenant_id?: string | null;
  roles?: string[];
}

export interface UseTenantManagementOptions {
  user: TenantManagementUser | null;
}

/** Client-side tenant list search: organisation name or tenant ID (substring, case-insensitive). */
export function tenantMatchesSearch(t: TenantView, rawSearch: string): boolean {
  const search = rawSearch.trim().toLowerCase();
  if (!search) return true;
  const organisation = (t.organisation ?? "").toLowerCase();
  const tenantId = String(t.tenant_id ?? "").toLowerCase();
  return organisation.includes(search) || tenantId.includes(search);
}

export function isTenantAdminRoleForSessionEnd(role?: string): boolean {
  return (role ?? "").trim().toUpperCase() === "TENANT ADMIN";
}

export function resolveTenantManagementRoles(user: TenantManagementUser | null) {
  const isTenantAdmin = Boolean(
    user?.roles?.some((role) => isTenantAdminRoleForSessionEnd(role)),
  );
  const isAdmin = Boolean(user?.roles?.includes("ADMIN"));
  const isTenantScopedUser = isTenantAdmin && !isAdmin;
  const userIdStr = user?.user_id ?? null;
  return { isTenantAdmin, isAdmin, isTenantScopedUser, userIdStr };
}
