// Client-side email rules for tenant contact + tenant user provisioning.

import type { TenantView, TenantUserView } from "../types/tenant";
import { tenantUserHasRole } from "./tenantUserRoles";

export const EMAIL_REQUIRED_MSG = "Email is required.";
export const EMAIL_INVALID_FORMAT_MSG =
  "Enter a valid email address (e.g. example@domain.com).";
/** Tenant / tenant-admin contact email collides with an existing user account. */
export const EMAIL_USER_ALREADY_EXISTS_MSG =
  "A user with this email address already exists.";
/** Tenant user (or tenant contact) email already in use. */
export const EMAIL_ALREADY_EXISTS_MSG =
  "This email is already associated with an existing account";
export const EMAIL_AVAILABLE_MSG = "Email is available.";

export function normalizeEmail(email: string): string {
  return (email || "").trim().toLowerCase();
}

export function isValidEmailFormat(email: string): boolean {
  const trimmed = (email || "").trim();
  return /^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$/.test(trimmed);
}

export function collectTenantContactEmails(tenants: TenantView[]): Set<string> {
  const out = new Set<string>();
  for (const t of tenants) {
    const e = normalizeEmail(t.email ?? "");
    if (e) out.add(e);
  }
  return out;
}

export function collectUserEmails(users: { email?: string | null }[]): Set<string> {
  const out = new Set<string>();
  for (const u of users) {
    const e = normalizeEmail(u.email ?? "");
    if (e) out.add(e);
  }
  return out;
}

/** Emails of users already provisioned under this institution (AI4IDS-3401). */
export function collectInstitutionUserEmails(
  users: { email?: string | null }[],
): Set<string> {
  return collectUserEmails(users);
}

/** Institution Admin emails for this institution — contact update applies immediately. */
export function collectInstitutionAdminEmails(
  users: TenantUserView[],
): Set<string> {
  const out = new Set<string>();
  for (const u of users) {
    if (!tenantUserHasRole(u, "TENANT ADMIN")) continue;
    const e = normalizeEmail(u.email ?? "");
    if (e) out.add(e);
  }
  return out;
}

export function emailSetHas(
  emails: Set<string> | readonly string[] | undefined,
  email: string,
): boolean {
  if (!emails) return false;
  const lower = normalizeEmail(email);
  if (!lower) return false;
  if (emails instanceof Set) return emails.has(lower);
  return emails.some((e) => normalizeEmail(e) === lower);
}

/**
 * When editing, skip collision checks for the record's current email, and for
 * users already in the institution being updated (AI4IDS-3401).
 */
export interface EmailUniquenessExclusions {
  excludeTenantEmail?: string;
  excludeUserEmail?: string;
  /** Same-institution user emails — allowed as the new contact email. */
  allowedUserEmails?: Set<string> | readonly string[];
}

function isExcludedEmail(lower: string, exclusions?: EmailUniquenessExclusions): {
  tenant: boolean;
  user: boolean;
} {
  const excludedTenant = exclusions?.excludeTenantEmail
    ? normalizeEmail(exclusions.excludeTenantEmail)
    : "";
  const excludedUser = exclusions?.excludeUserEmail
    ? normalizeEmail(exclusions.excludeUserEmail)
    : "";
  const allowedUser = emailSetHas(exclusions?.allowedUserEmails, lower);
  return {
    tenant: Boolean(excludedTenant) && lower === excludedTenant,
    user:
      (Boolean(excludedUser) && lower === excludedUser) || allowedUser,
  };
}

export function validateEmailFormatOnly(email: string): string | undefined {
  const trimmed = (email || "").trim();
  if (!trimmed) return EMAIL_REQUIRED_MSG;
  if (!isValidEmailFormat(trimmed)) return EMAIL_INVALID_FORMAT_MSG;
  return undefined;
}

/** Sync check: tenant contact email already registered on another tenant. */
export function validateTenantContactEmailTaken(
  email: string,
  tenantEmails: Set<string>,
  exclusions?: EmailUniquenessExclusions
): string | undefined {
  const formatError = validateEmailFormatOnly(email);
  if (formatError) return formatError;
  const lower = normalizeEmail(email);
  const skip = isExcludedEmail(lower, exclusions);
  if (tenantEmails.has(lower) && !skip.tenant) return EMAIL_ALREADY_EXISTS_MSG;
  return undefined;
}

/** Validate email for Create Tenant (contact + auto-provisioned tenant admin). */
export function validateTenantContactEmail(
  email: string,
  tenantEmails: Set<string>,
  userEmails: Set<string>,
  exclusions?: EmailUniquenessExclusions
): string | undefined {
  const trimmed = (email || "").trim();
  if (!trimmed) return EMAIL_REQUIRED_MSG;
  if (!isValidEmailFormat(trimmed)) return EMAIL_INVALID_FORMAT_MSG;
  const lower = normalizeEmail(trimmed);
  const skip = isExcludedEmail(lower, exclusions);
  if (userEmails.has(lower) && !skip.user) return EMAIL_USER_ALREADY_EXISTS_MSG;
  if (tenantEmails.has(lower) && !skip.tenant) return EMAIL_ALREADY_EXISTS_MSG;
  return undefined;
}

/** Validate email for Add Tenant User. */
export function validateTenantUserEmail(
  email: string,
  tenantEmails: Set<string>,
  userEmails: Set<string>,
  exclusions?: EmailUniquenessExclusions
): string | undefined {
  const trimmed = (email || "").trim();
  if (!trimmed) return EMAIL_REQUIRED_MSG;
  if (!isValidEmailFormat(trimmed)) return EMAIL_INVALID_FORMAT_MSG;
  const lower = normalizeEmail(trimmed);
  const skip = isExcludedEmail(lower, exclusions);
  if ((userEmails.has(lower) && !skip.user) || (tenantEmails.has(lower) && !skip.tenant)) {
    return EMAIL_ALREADY_EXISTS_MSG;
  }
  return undefined;
}
