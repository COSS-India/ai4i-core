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
  /**
   * Current contact's user id when GET /tenants/{id} returns it.
   * No email fallback — masked addresses collide across users.
   * If absent, the picker may include the current contact; BE returns
   * CONTACT_ALREADY_CURRENT on save.
   */
  excludeUserId?: string | null;
};

function contactAdminLabel(user: TenantUserView): string {
  const name = user.full_name?.trim() || user.username;
  const email = user.email?.trim();
  return email ? `${name} · ${email}` : name;
}

/**
 * Active, verified Institution Admins of this institution, excluding the
 * current contact when `excludeUserId` is known. Emails stay masked; the
 * save sends `user_id`.
 */
export function listOtherActiveInstitutionAdmins(
  users: readonly TenantUserView[],
  options?: ListContactAdminOptions,
): InstitutionContactAdminOption[] {
  const excludeUserId = options?.excludeUserId || null;
  const out: InstitutionContactAdminOption[] = [];
  for (const user of users) {
    if (!user.user_id || !user.is_active) continue;
    if (user.is_activated === false) continue;
    if (!tenantUserHasRole(user, "TENANT ADMIN")) continue;
    if (excludeUserId && user.user_id === excludeUserId) continue;
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
