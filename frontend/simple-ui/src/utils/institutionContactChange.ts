// Update Institution — pick another Institution Admin as the contact (AI4IDS-3401).

import { FIELD_HINTS } from "../config/fieldHints";
import { TENANT, isTenantStatus } from "../config/constants";
import type { TenantUserView } from "../types/tenant";
import { normalizeEmail } from "./tenantEmailValidation";
import { tenantUserHasRole } from "./tenantUserRoles";

export type InstitutionContactAdminOption = {
  userId: string;
  label: string;
};

export type ListContactAdminOptions = {
  /** Prefer this — BE should return the current contact's user id. */
  excludeUserId?: string | null;
  /**
   * Fallback when user id is unknown. Pass the *masked* list-row email so it
   * can match masked emails from GET /tenants/{id}/users.
   */
  excludeEmail?: string | null;
};

function contactAdminLabel(user: TenantUserView): string {
  const name = user.full_name?.trim() || user.username;
  const email = user.email?.trim();
  return email ? `${name} · ${email}` : name;
}

function isCurrentContact(
  user: TenantUserView,
  options?: ListContactAdminOptions,
): boolean {
  if (options?.excludeUserId && user.user_id === options.excludeUserId) {
    return true;
  }
  const excludeEmail = normalizeEmail(options?.excludeEmail ?? "");
  if (!excludeEmail) return false;
  return normalizeEmail(user.email ?? "") === excludeEmail;
}

/**
 * Active, verified Institution Admins of this institution, excluding the
 * current contact. Emails stay masked; the save sends `user_id`.
 */
export function listOtherActiveInstitutionAdmins(
  users: readonly TenantUserView[],
  options?: ListContactAdminOptions,
): InstitutionContactAdminOption[] {
  const out: InstitutionContactAdminOption[] = [];
  for (const user of users) {
    if (!user.user_id || !user.is_active) continue;
    if (user.is_activated === false) continue;
    if (!tenantUserHasRole(user, "TENANT ADMIN")) continue;
    if (isCurrentContact(user, options)) continue;
    const email = normalizeEmail(user.email ?? "");
    if (!email) continue;
    out.push({ userId: user.user_id, label: contactAdminLabel(user) });
  }
  out.sort((a, b) => a.label.localeCompare(b.label));
  return out;
}

/** Why Change contact cannot be used, or null when the picker may open. */
export function contactChangeBlockedMessage(
  status: string | null | undefined,
  options?: { isDefaultOrganisation?: boolean },
): string | null {
  if (options?.isDefaultOrganisation) {
    return FIELD_HINTS.tenant.contactChangeDefaultOrg;
  }
  if (isTenantStatus(status, TENANT.STATUS.PENDING)) {
    return FIELD_HINTS.tenant.contactChangePending;
  }
  if (isTenantStatus(status, TENANT.STATUS.SUSPENDED)) {
    return FIELD_HINTS.tenant.contactChangeSuspended;
  }
  if (isTenantStatus(status, TENANT.STATUS.DEACTIVATED)) {
    return FIELD_HINTS.tenant.contactChangeDeactivated;
  }
  if (isTenantStatus(status, TENANT.STATUS.ACTIVE)) {
    return null;
  }
  return FIELD_HINTS.tenant.contactChangeUnavailable;
}
