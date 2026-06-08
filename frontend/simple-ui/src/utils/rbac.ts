/** Shared RBAC role helpers for the simple-ui app. */

export function normalizeRole(role?: string | null): string {
  return (role ?? "").trim().toUpperCase();
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

export function isPlatformModeratorUser(roles?: string[]): boolean {
  return userHasRole(roles, "MODERATOR");
}

/** ADMIN and MODERATOR can view telemetry across tenants (optional tenant filter in UI). */
export function canViewCrossTenantTelemetry(roles?: string[]): boolean {
  return isPlatformAdminUser(roles) || isPlatformModeratorUser(roles);
}

/** Tenant Admin without platform ADMIN — model registry is read-only. */
export function isRegistryReadOnlyUser(roles?: string[]): boolean {
  return isTenantAdminUser(roles) && !isPlatformAdminUser(roles);
}

/** Services Management is not available to tenant-scoped admins (platform ADMIN still can). */
export function canAccessServicesManagement(roles?: string[]): boolean {
  return !isRegistryReadOnlyUser(roles);
}
