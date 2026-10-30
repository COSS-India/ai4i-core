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
  /** Current contact user id from GET /tenants/{id}; omit when unknown. */
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

/** Active, verified Institution Admins available as a new contact. */
export function listOtherActiveInstitutionAdmins(
  users: readonly TenantUserView[],
  options?: ListContactAdminOptions,
): InstitutionContactAdminOption[] {
  const excludeUserId = options?.excludeUserId || null;
  const eligible = users.filter(isEligibleContactAdmin);

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
