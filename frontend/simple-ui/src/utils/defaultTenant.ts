import type { User } from "../types/auth";
import type { TenantUserView, TenantView } from "../types/tenant";

/** Must match auth-service `default_tenant_org` / seed migration. */
export const DEFAULT_TENANT_ORGANISATION =
  (process.env.NEXT_PUBLIC_DEFAULT_TENANT_ORG || "default organisation").trim();

/**
 * Roles assignable on Profile → Roles (Adopter / Default tenant scope).
 * API values must match auth-service `RoleName`.
 */
export const DEFAULT_TENANT_ASSIGNABLE_ROLES = ["ADMIN", "MODERATOR", "USER"] as const;

/** All platform roles shown in the Default Tenant's Users → Role filter dropdown. */
export const DEFAULT_TENANT_ROLE_FILTER_LIST = [
  { value: "ADMIN", label: "Admin" },
  { value: "MODERATOR", label: "Moderator" },
  { value: "USER", label: "User" },
  { value: "GUEST", label: "Guest" },
  { value: "TENANT ADMIN", label: "Tenant Admin" },
] as const;

export type DefaultTenantAssignableRole = (typeof DEFAULT_TENANT_ASSIGNABLE_ROLES)[number];

const ASSIGNABLE_ROLE_LABELS: Record<DefaultTenantAssignableRole, string> = {
  ADMIN: "Admin",
  MODERATOR: "Moderator",
  USER: "User",
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
    roles: u.roles,
  }));
}
