// Update Institution — pick another Institution Admin as the contact (AI4IDS-3401).

import { FIELD_HINTS } from "../config/fieldHints";
import { TENANT, isTenantStatus } from "../config/constants";
import type { TenantUserView } from "../types/tenant";
import { isTenantContactEmailEditable, normalizeEmail } from "./tenantEmailValidation";
import { tenantUserHasRole } from "./tenantUserRoles";

export type InstitutionContactAdminOption = {
  userId: string;
  label: string;
};

function contactAdminLabel(user: TenantUserView): string {
  const name = user.full_name?.trim() || user.username;
  const email = user.email?.trim();
  return email ? `${name} · ${email}` : name;
}

/**
 * Active, verified Institution Admins of this institution, excluding the
 * current contact. Emails stay masked; the save sends `user_id`.
 */
export function listOtherActiveInstitutionAdmins(
  users: readonly TenantUserView[],
  currentEmail: string | null | undefined,
): InstitutionContactAdminOption[] {
  const current = normalizeEmail(currentEmail ?? "");
  const options: InstitutionContactAdminOption[] = [];
  for (const user of users) {
    if (!user.user_id || !user.is_active) continue;
    if (user.is_activated === false) continue;
    if (!tenantUserHasRole(user, "TENANT ADMIN")) continue;
    const email = normalizeEmail(user.email ?? "");
    if (!email || (current && email === current)) continue;
    options.push({ userId: user.user_id, label: contactAdminLabel(user) });
  }
  options.sort((a, b) => a.label.localeCompare(b.label));
  return options;
}

/** Why Change contact cannot be used, or null when the picker may open. */
export function contactChangeBlockedMessage(
  status: string | null | undefined,
  options?: { isDefaultOrganisation?: boolean },
): string | null {
  if (options?.isDefaultOrganisation) {
    return FIELD_HINTS.tenant.contactChangeDefaultOrg;
  }
  if (isTenantStatus(status, TENANT.STATUS.SUSPENDED)) {
    return FIELD_HINTS.tenant.contactChangeSuspended;
  }
  if (isTenantStatus(status, TENANT.STATUS.DEACTIVATED)) {
    return FIELD_HINTS.tenant.contactChangeDeactivated;
  }
  if (!isTenantContactEmailEditable(status)) {
    return FIELD_HINTS.tenant.contactChangeSuspended;
  }
  return null;
}
