/**
 * Default Organisation user roles (AI4IDS-2735).
 * Tenant-user API only accepts USER | TENANT ADMIN; Moderator/Guest go via role API.
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
        role: resolveDefaultOrgFormRole(cleaned, user.role),
      },
      rolesLoaded: true,
    };
  } catch {
    return { user, rolesLoaded: false };
  }
}

/** Set managed role to target; leaves ADMIN and other unmanaged roles untouched. */
export async function syncDefaultOrgUserRole(
  userId: string,
  targetRole: string,
  currentRoles?: string[],
): Promise<void> {
  const target = norm(targetRole);
  if (!isDefaultOrgUserRole(target)) {
    throw new Error("Default Organisation users may only be User, Moderator, or Guest.");
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
