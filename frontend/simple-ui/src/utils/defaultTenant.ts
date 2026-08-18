import type { User } from "../types/auth";
import type { TenantUserView, TenantView } from "../types/tenant";
import { INSTITUTION } from "../config/constants";

/** Must match auth-service `default_tenant_org` / seed migration. */
export const DEFAULT_TENANT_ORGANISATION =
  (process.env.NEXT_PUBLIC_DEFAULT_TENANT_ORG || "default organisation").trim();

/**
 * Roles assignable on Profile → Roles (Adopter / Default tenant scope).
 * API values must match auth-service `RoleName`.
 */
export const DEFAULT_TENANT_ASSIGNABLE_ROLES = [
  "ADMIN",
  "MODERATOR",
  "USER",
  "PROGRAM ADMIN",
] as const;

export type DefaultTenantAssignableRole = (typeof DEFAULT_TENANT_ASSIGNABLE_ROLES)[number];

const ASSIGNABLE_ROLE_LABELS: Record<DefaultTenantAssignableRole, string> = {
  ADMIN: "Admin",
  MODERATOR: "Moderator",
  USER: "User",
  "PROGRAM ADMIN": "Usage Viewer",
};

export function isDefaultTenantAssignableRole(role: string): boolean {
  const normalized = role.trim().toUpperCase();
  return (DEFAULT_TENANT_ASSIGNABLE_ROLES as readonly string[]).includes(normalized);
}

export function formatDefaultTenantAssignableRoleLabel(role: string): string {
  const normalized = role.trim().toUpperCase() as DefaultTenantAssignableRole;
  return ASSIGNABLE_ROLE_LABELS[normalized] ?? role;
}

export function resolveDefaultTenantId(tenants: TenantView[]): string | null {
  const target = DEFAULT_TENANT_ORGANISATION.toLowerCase();
  const match = tenants.find(
    (t) => (t.organisation || "").trim().toLowerCase() === target
  );
  return match?.tenant_id?.trim() || null;
}

export function isDefaultTenantOrg(organisation?: string | null): boolean {
  return (organisation ?? "").trim().toLowerCase() === DEFAULT_TENANT_ORGANISATION.toLowerCase();
}

export function isDefaultTenant(tenant: { organisation?: string | null }): boolean {
  return isDefaultTenantOrg(tenant.organisation);
}

/**
 * Default Organisation roles in Tenant Management.
 * Assignable via role API (not tenant-user role field, which only accepts
 * USER | TENANT ADMIN). Tenant Admin is never offered for default org.
 */
export const DEFAULT_ORG_USER_ROLE_OPTIONS = [
  { value: "USER", label: "User" },
  { value: "MODERATOR", label: "Moderator" },
  { value: "PROGRAM ADMIN", label: "Usage Viewer" },
] as const;

export type DefaultOrgUserRole =
  (typeof DEFAULT_ORG_USER_ROLE_OPTIONS)[number]["value"];

/**
 * Role filter options for Default Organisation users. Includes roles that are no
 * longer assignable but may still exist in `roles[]` (Admin, Guest).
 */
export const DEFAULT_TENANT_PLATFORM_ROLE_FILTER_LIST = [
  ...DEFAULT_ORG_USER_ROLE_OPTIONS,
  { value: "GUEST", label: "Guest" },
  { value: "ADMIN", label: "Admin" },
] as const;

export const DEFAULT_ORG_USER_FORM_ROLE_OPTIONS = DEFAULT_ORG_USER_ROLE_OPTIONS;

/**
 * Roles replaced when syncing to a default-org role (ADMIN excluded).
 * Keeps GUEST so legacy guests are cleared on reassignment.
 */
export const DEFAULT_ORG_MANAGED_ROLES = [
  "USER",
  "MODERATOR",
  "GUEST",
  "PROGRAM ADMIN",
  "TENANT ADMIN",
] as const;

const PLATFORM_ROLE_LABELS: Record<string, string> = {
  ADMIN: "Admin",
  USER: "User",
  MODERATOR: "Moderator",
  GUEST: "Guest",
  "TENANT ADMIN": `${INSTITUTION} Admin`,
  "PROGRAM ADMIN": "Usage Viewer",
};

export function isDefaultOrgUserRole(role: string): role is DefaultOrgUserRole {
  const normalized = role.trim().toUpperCase();
  return (DEFAULT_ORG_USER_ROLE_OPTIONS as ReadonlyArray<{ value: string }>).some(
    (o) => o.value === normalized,
  );
}

export function formatPlatformRoleLabel(role: string): string {
  const normalized = role.trim().toUpperCase();
  return PLATFORM_ROLE_LABELS[normalized] ?? role;
}

/**
 * Pick the primary role to show/edit for a default-org user.
 * Prefers a default-org assignable role when present in `roles[]`; otherwise first role.
 */
export function resolveDefaultOrgFormRole(
  roles: string[] | undefined | null,
  fallbackRole?: string | null,
): string {
  const normalized = (roles?.length ? roles : fallbackRole ? [fallbackRole] : [])
    .map((r) => r.trim().toUpperCase())
    .filter(Boolean);
  const preferred = normalized.find((r) => isDefaultOrgUserRole(r));
  if (preferred) return preferred;
  return normalized[0] || "USER";
}

/** Map tenant user rows for Profile → Roles picker (auth `User` shape). */
export function tenantUsersToAuthUsers(rows: TenantUserView[]): User[] {
  return rows.map((u) => ({
    user_id: u.user_id,
    email: u.email,
    username: u.username,
    full_name: u.full_name ?? undefined,
    phone_number: u.phone_number ?? undefined,
    is_active: u.is_active,
    is_tenant_active: u.is_tenant_active ?? undefined,
    roles: u.roles ?? [],
  }));
}
