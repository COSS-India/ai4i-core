import { formatPlatformRoleLabel } from "./defaultTenant";
import { TENANT_USER_ROLE_OPTIONS } from "../components/profile/types";
import type { TenantAssignableRole, TenantUserView } from "../types/tenant";
import { INSTITUTION } from "../config/constants";

const TENANT_ASSIGNABLE_ROLE_VALUES: readonly TenantAssignableRole[] = [
  "USER",
  "TENANT ADMIN",
];

/** Tenant user list role filter only (not platform ADMIN / MODERATOR / GUEST). */
export const TENANT_USER_ROLE_FILTER_LIST: ReadonlyArray<{
  value: TenantAssignableRole;
  label: string;
}> = [
  { value: "USER", label: "User" },
  { value: "TENANT ADMIN", label: `${INSTITUTION} Admin` },
] as const;

export function isTenantAssignableRole(role: string): role is TenantAssignableRole {
  const normalized = normalizeTenantUserRole(role);
  return (TENANT_ASSIGNABLE_ROLE_VALUES as readonly string[]).includes(normalized);
}

/** User payload role fields. `roles[]` is the API source of truth; `role` is legacy. */
export type TenantUserRoleSource = Pick<TenantUserView, "role" | "roles">;

export function normalizeTenantUserRole(role: string): string {
  return role.trim().toUpperCase();
}

export function formatTenantUserRoleLabel(role: string): string {
  const normalized = normalizeTenantUserRole(role);
  const match = TENANT_USER_ROLE_OPTIONS.find(
    (o) => normalizeTenantUserRole(o.value) === normalized,
  );
  if (match) return match.label;
  const platformLabel = formatPlatformRoleLabel(role);
  if (platformLabel !== role) return platformLabel;
  return role;
}

/** Primary tenant-assignable role for create/edit forms (USER or TENANT ADMIN). */
export function resolvePrimaryTenantAssignableRole(
  source: TenantUserRoleSource,
): TenantAssignableRole {
  const normalized = resolveTenantUserRoles(source).map(normalizeTenantUserRole);
  if (normalized.includes("TENANT ADMIN")) return "TENANT ADMIN";
  return "USER";
}

/** Prefer `roles[]` (BE source of truth); fall back to legacy singular `role`. */
export function resolveTenantUserRoles(source: TenantUserRoleSource): string[] {
  const fromArray = Array.isArray(source.roles)
    ? source.roles.map((r) => String(r).trim()).filter(Boolean)
    : [];
  if (fromArray.length > 0) return fromArray;
  const single = source.role;
  if (single != null && String(single).trim()) {
    return [String(single).trim()];
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
