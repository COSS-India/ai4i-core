/**
 * FE helpers for Default Organisation user roles (AI4IDS-2735).
 *
 * Tenant-user create/update only accepts USER | TENANT ADMIN. For default org we
 * provision/update as USER on that endpoint, then normalize to User / Moderator /
 * Guest via the existing role assign/remove API (same path as Profile → Roles).
 */

import roleService from "../services/roleService";
import type { TenantUserView } from "../types/tenant";
import {
  DEFAULT_ORG_MANAGED_ROLES,
  isDefaultOrgUserRole,
  resolveDefaultOrgFormRole,
} from "./defaultTenant";

function normalizeRoleName(role: string): string {
  return role.trim().toUpperCase();
}

/** Enrich list rows with real roles from GET /roles/user/{id}. */
export async function enrichDefaultOrgTenantUsers(
  users: TenantUserView[],
): Promise<TenantUserView[]> {
  if (users.length === 0) return users;
  return Promise.all(
    users.map(async (user) => {
      try {
        const { roles } = await roleService.getUserRoles(user.user_id);
        const cleaned = roles.map(normalizeRoleName).filter(Boolean);
        return {
          ...user,
          roles: cleaned,
          role: resolveDefaultOrgFormRole(cleaned, user.role),
        };
      } catch {
        return user;
      }
    }),
  );
}

/**
 * Ensure the user has exactly ``targetRole`` among managed tenant roles.
 * Leaves unrelated roles (e.g. ADMIN) untouched unless they are in the managed set.
 */
export async function syncDefaultOrgUserRole(
  userId: string,
  targetRole: string,
  currentRoles?: string[],
): Promise<void> {
  const target = normalizeRoleName(targetRole);
  if (!isDefaultOrgUserRole(target)) {
    throw new Error("Default Organisation users may only be User, Moderator, or Guest.");
  }

  const existing =
    currentRoles?.map(normalizeRoleName).filter(Boolean) ??
    (await roleService.getUserRoles(userId)).roles.map(normalizeRoleName);

  const managed = new Set<string>(DEFAULT_ORG_MANAGED_ROLES);
  const toRemove = existing.filter((role) => managed.has(role) && role !== target);
  for (const role of toRemove) {
    await roleService.removeRole(userId, role);
  }
  if (!existing.includes(target)) {
    await roleService.assignRole(userId, target);
  }
}
