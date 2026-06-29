// Platform and tenant RBAC role values

import type { TenantAssignableRole } from "../types/tenant";

/** Platform-wide roles (auth-service RoleName). */
export const PLATFORM_ROLES = {
  ADMIN: "ADMIN",
  MODERATOR: "MODERATOR",
  USER: "USER",
  GUEST: "GUEST",
  TENANT_ADMIN: "TENANT ADMIN",
} as const;

export type PlatformRoleValue = (typeof PLATFORM_ROLES)[keyof typeof PLATFORM_ROLES];

/** Roles assignable on Profile → Roles (Adopter / Default tenant scope). */
export const DEFAULT_TENANT_ASSIGNABLE_ROLES = [
  PLATFORM_ROLES.ADMIN,
  PLATFORM_ROLES.MODERATOR,
  PLATFORM_ROLES.USER,
] as const;

export type DefaultTenantAssignableRole = (typeof DEFAULT_TENANT_ASSIGNABLE_ROLES)[number];

/** Assignable tenant-user roles (create/edit forms and list filters). */
export const TENANT_ASSIGNABLE_ROLES = [
  { value: PLATFORM_ROLES.USER, label: "User" },
  { value: PLATFORM_ROLES.TENANT_ADMIN, label: "Tenant Admin" },
] as const satisfies ReadonlyArray<{ value: TenantAssignableRole; label: string }>;

/** Role filter options for Default Tenant user list (Tenant Management). */
export const PLATFORM_ROLE_FILTER_LIST = [
  { value: PLATFORM_ROLES.ADMIN, label: "Admin" },
  { value: PLATFORM_ROLES.USER, label: "User" },
  { value: PLATFORM_ROLES.MODERATOR, label: "Moderator" },
  { value: PLATFORM_ROLES.GUEST, label: "Guest" },
  { value: PLATFORM_ROLES.TENANT_ADMIN, label: "Tenant Admin" },
] as const;

export function formatPlatformRoleLabel(role: string): string {
  const normalized = role.trim().toUpperCase();
  const match = PLATFORM_ROLE_FILTER_LIST.find((o) => o.value === normalized);
  return match?.label ?? role;
}

export function isDefaultTenantAssignableRole(role: string): boolean {
  const normalized = role.trim().toUpperCase();
  return (DEFAULT_TENANT_ASSIGNABLE_ROLES as readonly string[]).includes(normalized);
}

/** Default primary role for new tenant users. */
export const DEFAULT_TENANT_USER_ROLE = PLATFORM_ROLES.USER as TenantAssignableRole;
