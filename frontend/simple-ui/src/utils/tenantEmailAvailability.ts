// Debounced live email availability checks (format + tenant list + /auth/check-email).

import authService from "../services/authService";
import { VALIDATION } from "../constants/validation";
import {
  normalizeEmail,
  validateEmailFormatOnly,
  validateTenantContactEmail,
  validateTenantContactEmailTaken,
  validateTenantUserEmail,
  type EmailUniquenessExclusions,
} from "./tenantEmailValidation";

export type EmailAvailabilityStatus = "idle" | "checking" | "available";

export type TenantEmailCheckMode = "tenant_contact" | "tenant_user";

export interface RunEmailAvailabilityCheckOptions {
  email: string;
  mode: TenantEmailCheckMode;
  tenantEmails: Set<string>;
  userEmails: Set<string>;
  exclusions?: EmailUniquenessExclusions;
  skipRemoteCheck?: boolean;
}

export interface EmailAvailabilityResult {
  error?: string;
  status: EmailAvailabilityStatus;
}

function userExistsMessage(mode: TenantEmailCheckMode): string {
  return mode === "tenant_contact"
    ? VALIDATION.EMAIL.USER_ALREADY_EXISTS
    : VALIDATION.EMAIL.ALREADY_EXISTS;
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
  const { email, mode, tenantEmails, userEmails, exclusions, skipRemoteCheck } = options;

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

  try {
    const exists = await authService.checkEmailExists(email);
    if (exists) {
      const skip = exclusions
        ? normalizeEmail(email) === normalizeEmail(exclusions.excludeUserEmail ?? "")
        : false;
      if (!skip) {
        return { error: userExistsMessage(mode), status: "idle" };
      }
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

  const lower = normalizeEmail(email);
  const skipUser =
    exclusions?.excludeUserEmail &&
    lower === normalizeEmail(exclusions.excludeUserEmail);
  if (userEmails.has(lower) && !skipUser) {
    return { error: userExistsMessage(mode), status: "idle" };
  }

  return { status: "available" };
}
