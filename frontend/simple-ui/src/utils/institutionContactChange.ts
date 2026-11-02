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
   * Institution contact email from the edit GET (usually unmasked).
   * listUsers emails stay masked — we mask this the same way as auth-service
   * and exclude matching admins (AI4IDS-3617). Never empty the picker solely
   * because one admin remains: that admin may not be the contact (AI4IDS-3401).
   */
  contactEmail?: string | null;
};

/** Keep first char + `***`, matching auth-service ``mask_email`` segments. */
function maskEmailSegment(part: string): string {
  if (part.length > 0) {
    return `${part.charAt(0)}***`;
  }
  return "***";
}

function maskEmailDomain(domain: string): string {
  const dot = domain.indexOf(".");
  if (dot >= 0) {
    return `${maskEmailSegment(domain.slice(0, dot))}.${domain.slice(dot + 1)}`;
  }
  return maskEmailSegment(domain);
}

/**
 * Same shape as auth-service ``mask_email`` so unmasked contact addresses
 * compare to masked listUsers emails (``j***@e***.com``).
 */
export function maskEmailForCompare(value: string): string {
  const email = normalizeEmail(value);
  if (email?.includes("@")) {
    const at = email.indexOf("@");
    const local = email.slice(0, at);
    const domain = email.slice(at + 1);
    return `${maskEmailSegment(local)}@${maskEmailDomain(domain)}`;
  }
  return email;
}

function isCurrentContactEmail(
  userEmail: string | null | undefined,
  contactEmail: string | null | undefined,
): boolean {
  const user = normalizeEmail(userEmail ?? "");
  const contact = normalizeEmail(contactEmail ?? "");
  if (!user || !contact) return false;
  if (user === contact) return true;
  const maskedContact = maskEmailForCompare(contact);
  const maskedUser = maskEmailForCompare(user);
  return user === maskedContact || maskedUser === maskedContact;
}

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
 * Excludes admins whose (masked) email matches ``contactEmail`` so a sole
 * admin who *is* the contact yields an empty picker (AI4IDS-3617). When the
 * contact is deactivated and not among eligible admins, other admins stay
 * listed (AI4IDS-3401). No unconditional sole-admin empty list.
 */
export function listOtherActiveInstitutionAdmins(
  users: readonly TenantUserView[],
  options?: ListContactAdminOptions,
): InstitutionContactAdminOption[] {
  const contactEmail = options?.contactEmail || null;
  const out: InstitutionContactAdminOption[] = [];
  for (const user of users) {
    if (!isEligibleContactAdmin(user)) continue;
    if (contactEmail && isCurrentContactEmail(user.email, contactEmail)) {
      continue;
    }
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
