/** Shared RBAC role helpers for the simple-ui app. */

import { PLATFORM_ROLES } from "../constants/roles";

export function normalizeRole(role?: string | null): string {
  return (role ?? "").trim().toUpperCase().replaceAll("_", " ");
}

export function userHasRole(roles: string[] | undefined, target: string): boolean {
  const normalized = normalizeRole(target);
  return (roles ?? []).some((r) => normalizeRole(r) === normalized);
}

export function isTenantAdminUser(roles?: string[]): boolean {
  return userHasRole(roles, PLATFORM_ROLES.TENANT_ADMIN);
}

export function isPlatformAdminUser(roles?: string[]): boolean {
  return userHasRole(roles, PLATFORM_ROLES.ADMIN);
}

/** Tenant Admin without platform ADMIN — model registry is read-only. */
export function isRegistryReadOnlyUser(roles?: string[]): boolean {
  return isTenantAdminUser(roles) && !isPlatformAdminUser(roles);
}

/** Services Management is not available to tenant-scoped admins (platform ADMIN still can). */
export function canAccessServicesManagement(roles?: string[]): boolean {
  return !isRegistryReadOnlyUser(roles);
}

/** Usage Dashboard — platform ADMIN (adopter view) or Tenant Admin only. */
export function canAccessUsageDashboard(roles?: string[]): boolean {
  if (!roles?.length) return false;
  return isDefaultAdminUser(roles) || isTenantAdminUser(roles);
}

/** Platform-wide metering tabs (tenant ranking, adoption) — ADMIN/MODERATOR only. */
export function canAccessPlatformMetering(roles?: string[]): boolean {
  return isPlatformAdminUser(roles) || userHasRole(roles, PLATFORM_ROLES.MODERATOR);
}

/** Default / platform ADMIN — adopter-wide metering view. */
export function isDefaultAdminUser(roles?: string[]): boolean {
  return isPlatformAdminUser(roles);
}

/** Adopter Admin (MODERATOR) without platform ADMIN. */
export function isAdopterAdminUser(roles?: string[]): boolean {
  return userHasRole(roles, PLATFORM_ROLES.MODERATOR) && !isPlatformAdminUser(roles);
}

/** Tenant Admin without platform ADMIN or MODERATOR. */
export function isTenantAdminOnlyUser(roles?: string[]): boolean {
  return isTenantAdminUser(roles) && !canAccessPlatformMetering(roles);
}

export function isGuestUser(roles?: string[]): boolean {
  return userHasRole(roles, PLATFORM_ROLES.GUEST);
}

export function isRegularUser(roles?: string[]): boolean {
  return userHasRole(roles, PLATFORM_ROLES.USER);
}

export type MeteringRoleView = "adopter" | "tenant";

export interface MeteringRoleViewConfig {
  availableViews: MeteringRoleView[];
  defaultView: MeteringRoleView;
}

/** Resolve the single Usage Dashboard view for the signed-in role (no view toggle). */
export function getMeteringRoleViewConfig(roles?: string[]): MeteringRoleViewConfig {
  if (isTenantAdminOnlyUser(roles)) {
    return {
      availableViews: ["tenant"],
      defaultView: "tenant",
    };
  }
  return {
    availableViews: ["adopter"],
    defaultView: "adopter",
  };
}
