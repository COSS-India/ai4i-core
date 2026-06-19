/** Shared RBAC role helpers for the simple-ui app. */

export function normalizeRole(role?: string | null): string {
  return (role ?? "").trim().toUpperCase().replaceAll("_", " ");
}

export function userHasRole(roles: string[] | undefined, target: string): boolean {
  const normalized = normalizeRole(target);
  return (roles ?? []).some((r) => normalizeRole(r) === normalized);
}

export function isTenantAdminUser(roles?: string[]): boolean {
  return userHasRole(roles, "TENANT ADMIN");
}

export function isPlatformAdminUser(roles?: string[]): boolean {
  return userHasRole(roles, "ADMIN");
}

/** Tenant Admin without platform ADMIN — model registry is read-only. */
export function isRegistryReadOnlyUser(roles?: string[]): boolean {
  return isTenantAdminUser(roles) && !isPlatformAdminUser(roles);
}

/** Services Management is not available to tenant-scoped admins (platform ADMIN still can). */
export function canAccessServicesManagement(roles?: string[]): boolean {
  return !isRegistryReadOnlyUser(roles);
}

/** Usage Dashboard — platform ADMIN (preview both views) or Tenant Admin only. */
export function canAccessUsageDashboard(roles?: string[]): boolean {
  if (!roles?.length) return false;
  return isDefaultAdminUser(roles) || isTenantAdminUser(roles);
}

/** Platform-wide metering tabs (tenant ranking, adoption) — ADMIN/MODERATOR only. */
export function canAccessPlatformMetering(roles?: string[]): boolean {
  return isPlatformAdminUser(roles) || userHasRole(roles, "MODERATOR");
}

/** Default / platform ADMIN — can preview both Adopter and Tenant Admin views. */
export function isDefaultAdminUser(roles?: string[]): boolean {
  return isPlatformAdminUser(roles);
}

/** Adopter Admin (MODERATOR) without platform ADMIN. */
export function isAdopterAdminUser(roles?: string[]): boolean {
  return userHasRole(roles, "MODERATOR") && !isPlatformAdminUser(roles);
}

/** Tenant Admin without platform ADMIN or MODERATOR. */
export function isTenantAdminOnlyUser(roles?: string[]): boolean {
  return isTenantAdminUser(roles) && !canAccessPlatformMetering(roles);
}

export type MeteringRoleView = "adopter" | "tenant";

export interface MeteringRoleViewConfig {
  canSwitchViews: boolean;
  availableViews: MeteringRoleView[];
  defaultView: MeteringRoleView;
}

/** Resolve which role-view tabs to show on the Usage Dashboard. */
export function getMeteringRoleViewConfig(roles?: string[]): MeteringRoleViewConfig {
  if (isDefaultAdminUser(roles)) {
    return {
      canSwitchViews: true,
      availableViews: ["adopter", "tenant"],
      defaultView: "adopter",
    };
  }
  if (isTenantAdminUser(roles)) {
    return {
      canSwitchViews: false,
      availableViews: ["tenant"],
      defaultView: "tenant",
    };
  }
  return {
    canSwitchViews: false,
    availableViews: ["tenant"],
    defaultView: "tenant",
  };
}
