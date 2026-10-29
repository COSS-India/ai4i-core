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
   * If absent and there is more than one admin, the picker may include the
   * current contact; BE returns CONTACT_ALREADY_CURRENT on save. A sole
   * admin with no id is treated as "no alternative" so Change contact stays
   * blocked with the hover message.
   */
  excludeUserId?: string | null;
};

function contactAdminLabel(user: TenantUserView): string {
  const name = user.full_name?.trim() || user.username;
  const email = user.email?.trim();
  return email ? `${name} · ${email}` : name;
}

function isEligibleContactAdmin(user: TenantUserView): boolean {
  if (!user.user_id || !user.is_active) return false;
  if (user.is_activated === false) return false;
  if (!tenantUserHasRole(user, "TENANT ADMIN")) return false;
  return Boolean(normalizeEmail(user.email ?? ""));
}

/**
 * Active, verified Institution Admins available as a new contact. Excludes
 * the current contact when `excludeUserId` is known. Emails stay masked; the
 * save sends `user_id`.
 */
export function listOtherActiveInstitutionAdmins(
  users: readonly TenantUserView[],
  options?: ListContactAdminOptions,
): InstitutionContactAdminOption[] {
  const excludeUserId = options?.excludeUserId || null;
  const eligible = users.filter(isEligibleContactAdmin);

  // Without a contact user id we cannot tell who the current contact is.
  // A single eligible admin must be them — nothing to switch to.
  if (!excludeUserId && eligible.length <= 1) {
    return [];
  }

  const out: InstitutionContactAdminOption[] = [];
  for (const user of eligible) {
    if (excludeUserId && user.user_id === excludeUserId) continue;
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
