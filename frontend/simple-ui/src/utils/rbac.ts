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

/** Tenant Admin without platform ADMIN — model/service registry is read-only. */
export function isRegistryReadOnlyUser(roles?: string[]): boolean {
  return isTenantAdminUser(roles) && !isPlatformAdminUser(roles);
}
