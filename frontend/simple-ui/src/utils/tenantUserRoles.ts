import { TENANT_USER_ROLE_OPTIONS } from "../components/profile/types";
import type { TenantUserView } from "../types/tenant";

/** Static RBAC role values for tenant user list filters. */
export const TENANT_USER_ROLE_FILTER_LIST = TENANT_USER_ROLE_OPTIONS;

/** List-users API shape: upcoming `role` string and/or legacy `roles` array. */
export type TenantUserRoleSource = Pick<TenantUserView, "role" | "roles">;

export function normalizeTenantUserRole(role: string): string {
  return role.trim().toUpperCase();
}

export function formatTenantUserRoleLabel(role: string): string {
  const normalized = normalizeTenantUserRole(role);
  const match = TENANT_USER_ROLE_OPTIONS.find(
    (o) => normalizeTenantUserRole(o.value) === normalized,
  );
  return match?.label ?? role;
}

/**
 * Resolve roles from list-users API (frontend-only).
 * Upcoming shape: singular `role`. Also accepts `roles[]` from profile/detail endpoints.
 */
export function resolveTenantUserRoles(source: TenantUserRoleSource): string[] {
  const single = source.role;
  if (single != null && String(single).trim()) {
    return [String(single).trim()];
  }
  if (Array.isArray(source.roles)) {
    return source.roles.map((r) => String(r).trim()).filter(Boolean);
  }
  return [];
}

export function tenantUserHasRole(user: TenantUserView, filterRole: string): boolean {
  const target = normalizeTenantUserRole(filterRole);
  return resolveTenantUserRoles(user).some((r) => normalizeTenantUserRole(r) === target);
}

/** Normalize one tenant user row for table display and filters. */
export function normalizeTenantUserRow(user: TenantUserView): TenantUserView {
  return {
    ...user,
    roles: resolveTenantUserRoles(user),
  };
}

/** Normalize tenant user rows from GET /tenants/{id}/users. */
export function normalizeTenantUserRoles(users: TenantUserView[]): TenantUserView[] {
  return users.map(normalizeTenantUserRow);
}
