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
   * CONTACT_ALREADY_CURRENT on save. Do not assume a sole eligible admin is
   * the current contact — they may already be deactivated (AI4IDS-3401).
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
 * Active, verified Institution Admins available as a new contact.
 * When `excludeUserId` is the current contact, they are omitted so a sole
 * remaining admin who *is* the contact yields an empty picker (AI4IDS-3617).
 * When the contact is deactivated and absent from the eligible set, other
 * admins stay listed (AI4IDS-3401).
 */
export function listOtherActiveInstitutionAdmins(
  users: readonly TenantUserView[],
  options?: ListContactAdminOptions,
): InstitutionContactAdminOption[] {
  const excludeUserId = options?.excludeUserId || null;
  const out: InstitutionContactAdminOption[] = [];
  for (const user of users) {
    if (!isEligibleContactAdmin(user)) continue;
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
