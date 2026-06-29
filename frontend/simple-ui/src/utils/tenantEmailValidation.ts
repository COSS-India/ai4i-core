// Client-side email rules for tenant contact + tenant user provisioning.

import type { TenantView } from "../types/tenant";
import { VALIDATION } from "../constants/validation";

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

/** When editing, skip collision checks for the record's current email. */
export interface EmailUniquenessExclusions {
  excludeTenantEmail?: string;
  excludeUserEmail?: string;
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
  return {
    tenant: Boolean(excludedTenant) && lower === excludedTenant,
    user: Boolean(excludedUser) && lower === excludedUser,
  };
}

export function validateEmailFormatOnly(email: string): string | undefined {
  const trimmed = (email || "").trim();
  if (!trimmed) return VALIDATION.EMAIL.REQUIRED;
  if (!isValidEmailFormat(trimmed)) return VALIDATION.EMAIL.INVALID_FORMAT;
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
  if (tenantEmails.has(lower) && !skip.tenant) return VALIDATION.EMAIL.ALREADY_EXISTS;
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
  if (!trimmed) return VALIDATION.EMAIL.REQUIRED;
  if (!isValidEmailFormat(trimmed)) return VALIDATION.EMAIL.INVALID_FORMAT;
  const lower = normalizeEmail(trimmed);
  const skip = isExcludedEmail(lower, exclusions);
  if (userEmails.has(lower) && !skip.user) return VALIDATION.EMAIL.USER_ALREADY_EXISTS;
  if (tenantEmails.has(lower) && !skip.tenant) return VALIDATION.EMAIL.ALREADY_EXISTS;
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
  if (!trimmed) return VALIDATION.EMAIL.REQUIRED;
  if (!isValidEmailFormat(trimmed)) return VALIDATION.EMAIL.INVALID_FORMAT;
  const lower = normalizeEmail(trimmed);
  const skip = isExcludedEmail(lower, exclusions);
  if ((userEmails.has(lower) && !skip.user) || (tenantEmails.has(lower) && !skip.tenant)) {
    return VALIDATION.EMAIL.ALREADY_EXISTS;
  }
  return undefined;
}
