import { formatPlatformRoleLabel, PLATFORM_ROLES, TENANT_ASSIGNABLE_ROLES } from "../constants/roles";
import type { TenantAssignableRole, TenantUserView } from "../types/tenant";

const TENANT_ASSIGNABLE_ROLE_VALUES: readonly TenantAssignableRole[] =
  TENANT_ASSIGNABLE_ROLES.map((o) => o.value);

export function isTenantAssignableRole(role: string): role is TenantAssignableRole {
  const normalized = normalizeTenantUserRole(role);
  return (TENANT_ASSIGNABLE_ROLE_VALUES as readonly string[]).includes(normalized);
}

/** List-users API shape: upcoming `role` string and/or legacy `roles` array. */
export type TenantUserRoleSource = Pick<TenantUserView, "role" | "roles">;

export function normalizeTenantUserRole(role: string): string {
  return role.trim().toUpperCase();
}

export function formatTenantUserRoleLabel(role: string): string {
  const normalized = normalizeTenantUserRole(role);
  const match = TENANT_ASSIGNABLE_ROLES.find(
    (o) => normalizeTenantUserRole(o.value) === normalized,
  );
  if (match) return match.label;
  const platformLabel = formatPlatformRoleLabel(role);
  if (platformLabel !== role) return platformLabel;
  return role;
}

/**
 * Resolve roles from list-users API (frontend-only).
 * Upcoming shape: singular `role`. Also accepts `roles[]` from profile/detail endpoints.
 */
/** Primary tenant-assignable role for create/edit forms (USER or TENANT ADMIN). */
export function resolvePrimaryTenantAssignableRole(
  source: TenantUserRoleSource,
): TenantAssignableRole {
  const normalized = resolveTenantUserRoles(source).map(normalizeTenantUserRole);
  if (normalized.includes(PLATFORM_ROLES.TENANT_ADMIN)) return PLATFORM_ROLES.TENANT_ADMIN;
  return PLATFORM_ROLES.USER;
}

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

/** Client-side tenant user search: username, email, or full name. */
export function tenantUserMatchesSearch(user: TenantUserView, rawSearch: string): boolean {
  const search = rawSearch.trim().toLowerCase();
  if (!search) return true;
  const haystacks = [user.username, user.email, user.full_name];
  return haystacks.some((value) => value?.toLowerCase().includes(search));
}

/** Normalize one tenant user row for table display and filters. */
export function normalizeTenantUserRow(user: TenantUserView): TenantUserView {
  return {
    ...user,
    roles: resolveTenantUserRoles(user),
  };
}

/** Normalize tenant user rows from GET /auth/tenants/{id}/users. */
export function normalizeTenantUserRoles(users: TenantUserView[]): TenantUserView[] {
  return users.map(normalizeTenantUserRow);
}
