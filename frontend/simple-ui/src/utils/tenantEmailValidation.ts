// Client-side email rules for tenant contact + tenant user provisioning.

import {
  INSTITUTION,
  TENANT,
  isTenantStatus,
} from "../config/constants";
import type { TenantView } from "../types/tenant";

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

/**
 * PATCH /tenants/{id} typed-email uniqueness conflicts (AI4IDS-3401 / #1818).
 * CONTACT_* picker failures are intentionally omitted — Change contact has no
 * email field error UI, so those codes must reach showError as toasts.
 */
export const TENANT_EMAIL_CONFLICT_CODES = new Set([
  "DUPLICATE_EMAIL",
  "DUPLICATE_TENANT_EMAIL",
]);

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

/**
 * Typed contact email is only for PENDING non-default institutions
 * (AI4IDS-3401 / #1858). ACTIVE institutions use Change contact (`contact_user_id`).
 */
export function isTenantContactEmailEditable(
  status: string | null | undefined,
  options?: { isDefaultOrganisation?: boolean },
): boolean {
  if (options?.isDefaultOrganisation) return false;
  return isTenantStatus(status, TENANT.STATUS.PENDING);
}

function asErrorDetailRecord(
  detail: unknown,
): Record<string, unknown> | null {
  if (typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
    return detail as Record<string, unknown>;
  }
  return null;
}

function stringifyErrorCode(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.toUpperCase();
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value).toUpperCase();
  }
  return null;
}

export function extractApiErrorCode(error: unknown): string | null {
  const detail = (
    error as { response?: { data?: { detail?: unknown } } } | null
  )?.response?.data?.detail;
  const record = asErrorDetailRecord(detail);
  if (!record) return null;
  return (
    stringifyErrorCode(record.code) ?? stringifyErrorCode(record.error)
  );
}

/** Message from API `detail` only — never axios's top-level `error.message`. */
export function extractApiErrorMessage(error: unknown): string | undefined {
  const detail = (
    error as { response?: { data?: { detail?: unknown } } } | null
  )?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  const record = asErrorDetailRecord(detail);
  if (!record) return undefined;
  const message = record.message;
  return typeof message === "string" && message.trim() ? message : undefined;
}

/** Inline form message for PATCH email uniqueness 409s; undefined for other errors. */
export function mapTenantEmailConflictToFieldError(
  error: unknown,
): string | undefined {
  const code = extractApiErrorCode(error);
  if (!code || !TENANT_EMAIL_CONFLICT_CODES.has(code)) return undefined;
  return extractApiErrorMessage(error) ?? EMAIL_ALREADY_EXISTS_MSG;
}

export type TenantEmailUpdateFeedback = {
  toastType: "success" | "info";
  message: string;
  /** Effective contact after save (old address while verification is pending). */
  email: string | undefined;
  pending_email: string | null;
};

/**
 * Toast + local email fields from PATCH /tenants/{id} after an email change
 * (AI4IDS-3401 / BE contract).
 */
export function resolveTenantEmailUpdateFeedback(
  updated: Pick<
    TenantView,
    "email" | "pending_email" | "email_verification_sent" | "status"
  >,
  previousEmail: string | undefined,
): TenantEmailUpdateFeedback {
  const pending = updated.pending_email?.trim() || null;
  const sent = Boolean(updated.email_verification_sent);
  const effectiveEmail = updated.email || previousEmail;

  if (sent && pending) {
    return {
      toastType: "info",
      message:
        "Verification email sent to the new address. The change takes effect once it's verified.",
      email: effectiveEmail,
      pending_email: pending,
    };
  }

  if (sent) {
    return {
      toastType: "info",
      message:
        "Email updated. A new activation link was sent to the new address.",
      email: effectiveEmail,
      pending_email: null,
    };
  }

  return {
    toastType: "success",
    message: `${INSTITUTION} updated.`,
    email: effectiveEmail,
    pending_email: null,
  };
}

/**
 * When editing, skip collision checks for the record's current email.
 * Contact-email edit uniqueness for users is decided by PATCH (emails stay masked).
 */
export type EmailUniquenessExclusions = Readonly<{
  excludeTenantEmail?: string;
  excludeUserEmail?: string;
}>;

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
