// Debounced live email availability checks (format + tenant list + /auth/check-email).

import authService from "../services/authService";
import {
  EMAIL_ALREADY_EXISTS_MSG,
  EMAIL_USER_ALREADY_EXISTS_MSG,
  normalizeEmail,
  validateEmailFormatOnly,
  validateTenantContactEmail,
  validateTenantContactEmailTaken,
  validateTenantUserEmail,
  type EmailUniquenessExclusions,
} from "./tenantEmailValidation";

/**
 * `unchecked` = format/tenant checks passed, user uniqueness deferred to PATCH
 * (edit contact email — listUsers emails stay masked).
 */
export type EmailAvailabilityStatus =
  | "idle"
  | "checking"
  | "available"
  | "unchecked";

export const EMAIL_CHECK_DEBOUNCE_MS = 400;

export type TenantEmailCheckMode = "tenant_contact" | "tenant_user";

export interface RunEmailAvailabilityCheckOptions {
  email: string;
  mode: TenantEmailCheckMode;
  tenantEmails: Set<string>;
  userEmails: Set<string>;
  exclusions?: EmailUniquenessExclusions;
  skipRemoteCheck?: boolean;
  /**
   * Skip /auth/check-email and known-user collision (AI4IDS-3401 edit flow).
   * listUsers emails stay masked even with unmask=true, so FE cannot tell
   * Institution Admin vs other users — PATCH owns that decision.
   */
  skipUserCollision?: boolean;
}

export interface EmailAvailabilityResult {
  error?: string;
  status: EmailAvailabilityStatus;
}

function userExistsMessage(mode: TenantEmailCheckMode): string {
  return mode === "tenant_contact"
    ? EMAIL_USER_ALREADY_EXISTS_MSG
    : EMAIL_ALREADY_EXISTS_MSG;
}

function clientCollisionError(
  email: string,
  mode: TenantEmailCheckMode,
  tenantEmails: Set<string>,
  userEmails: Set<string>,
  exclusions?: EmailUniquenessExclusions
): string | undefined {
  if (mode === "tenant_contact") {
    return validateTenantContactEmail(email, tenantEmails, userEmails, exclusions);
  }
  return validateTenantUserEmail(email, tenantEmails, userEmails, exclusions);
}

/** Run format, tenant-list, and optional API checks for a single email value. */
export async function runEmailAvailabilityCheck(
  options: RunEmailAvailabilityCheckOptions
): Promise<EmailAvailabilityResult> {
  const {
    email,
    mode,
    tenantEmails,
    userEmails,
    exclusions,
    skipRemoteCheck,
    skipUserCollision = false,
  } = options;

  const formatError = validateEmailFormatOnly(email);
  if (formatError) {
    return { error: formatError, status: "idle" };
  }

  const tenantTakenError = validateTenantContactEmailTaken(
    email,
    tenantEmails,
    exclusions
  );
  if (tenantTakenError) {
    return { error: tenantTakenError, status: "idle" };
  }

  if (skipUserCollision) {
    return { status: "unchecked" };
  }

  if (skipRemoteCheck) {
    const clientError = clientCollisionError(
      email,
      mode,
      tenantEmails,
      userEmails,
      exclusions
    );
    if (clientError) return { error: clientError, status: "idle" };
    return { status: "available" };
  }

  const lower = normalizeEmail(email);
  const skipExcludedUser =
    Boolean(exclusions?.excludeUserEmail) &&
    lower === normalizeEmail(exclusions?.excludeUserEmail ?? "");

  try {
    const exists = await authService.checkEmailExists(email);
    if (exists && !skipExcludedUser) {
      return { error: userExistsMessage(mode), status: "idle" };
    }
  } catch {
    const clientError = clientCollisionError(
      email,
      mode,
      tenantEmails,
      userEmails,
      exclusions
    );
    if (clientError) return { error: clientError, status: "idle" };
  }

  if (userEmails.has(lower) && !skipExcludedUser) {
    return { error: userExistsMessage(mode), status: "idle" };
  }

  return { status: "available" };
}
