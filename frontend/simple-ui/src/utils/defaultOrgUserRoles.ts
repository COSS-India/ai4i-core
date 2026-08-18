/**
 * Default Organisation user roles.
 * Tenant-user API only accepts USER | TENANT ADMIN; Moderator/Usage Viewer go
 * via role API.
 */

import roleService from "../services/roleService";
import type { TenantUserView } from "../types/tenant";
import {
  DEFAULT_ORG_MANAGED_ROLES,
  isDefaultOrgUserRole,
  resolveDefaultOrgFormRole,
} from "./defaultTenant";

const norm = (r: string) => r.trim().toUpperCase();

/** Lazy single-user enrich — do not call for full tenant lists. */
export async function enrichDefaultOrgTenantUser(
  user: TenantUserView,
): Promise<{ user: TenantUserView; rolesLoaded: boolean }> {
  try {
    const cleaned = (await roleService.getUserRoles(user.user_id)).roles
      .map(norm)
      .filter(Boolean);
    return {
      user: {
        ...user,
        roles: cleaned,
        role: resolveDefaultOrgFormRole(cleaned),
      },
      rolesLoaded: true,
    };
  } catch {
    return { user, rolesLoaded: false };
  }
}

/**
 * Apply a managed default-org role onto a list/detail row locally.
 * GET /tenants/{id}/users collapses MODERATOR/GUEST to USER, so after a role
 * sync the UI must patch from the role we just wrote rather than re-reading
 * that list endpoint.
 */
export function applyDefaultOrgManagedRoleToUser(
  user: TenantUserView,
  targetRole: string,
): TenantUserView {
  const target = norm(targetRole);
  if (!isDefaultOrgUserRole(target)) return user;
  const managed = new Set<string>(DEFAULT_ORG_MANAGED_ROLES);
  const retained = (user.roles ?? [])
    .map(norm)
    .filter((r) => r && !managed.has(r) && r !== target);
  return {
    ...user,
    role: target,
    roles: [...retained, target],
  };
}

/** Set managed role to target; leaves ADMIN and other unmanaged roles untouched. */
export async function syncDefaultOrgUserRole(
  userId: string,
  targetRole: string,
  currentRoles?: string[],
): Promise<void> {
  const target = norm(targetRole);
  if (!isDefaultOrgUserRole(target)) {
    throw new Error(
      "Default Organisation users may only be User, Moderator, or Usage Viewer.",
    );
  }
  const existing =
    currentRoles?.map(norm).filter(Boolean) ??
    (await roleService.getUserRoles(userId)).roles.map(norm);
  const managed = new Set<string>(DEFAULT_ORG_MANAGED_ROLES);
  const toRemove = existing.filter((r) => managed.has(r) && r !== target);
  // Assign first so a failed assign cannot leave the user with no managed role.
  if (!existing.includes(target)) await roleService.assignRole(userId, target);
  for (const role of toRemove) await roleService.removeRole(userId, role);
}
