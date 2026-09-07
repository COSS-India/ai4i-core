// Client-side field rules for tenant + tenant user create/edit forms.

import type { TenantView } from "../types/tenant";
import { INSTITUTION, INSTITUTION_ARTICLE_CAP } from "../config/constants";

const INVISIBLE_CHARS = /[\u00AD\u200B-\u200D\u2060\uFEFF\u2028\u2029\u200E\u200F]+/g;
const PHONE_FORMAT_CHARS = /[ \-().]/g;
const E164_RE = /^\+[1-9]\d{1,14}$/;

const ORG_PUNCT = new Set([" ", "-", ".", "'"]);
const NAME_PUNCT = new Set([" ", "-", "'"]);

export const ORG_REQUIRED_MSG = "Organisation is required.";
export const ORG_TOO_SHORT_MSG = "Organisation must be at least 2 characters.";
export const ORG_TOO_LONG_MSG = "Organisation must not exceed 100 characters.";
export const ORG_INVALID_CHARS_MSG =
  "Organisation may only contain letters, digits, spaces, hyphens, dots, and apostrophes.";
export const ORG_NO_ALNUM_MSG = "Organisation must contain at least one letter or digit.";
export const ORG_DUPLICATE_MSG = `${INSTITUTION_ARTICLE_CAP} ${INSTITUTION.toLowerCase()} with this organisation name already exists.`;

export const CONTACT_NAME_REQUIRED_MSG = "Contact name is required.";
export const FULL_NAME_REQUIRED_MSG = "Full name is required.";
export const NAME_TOO_SHORT_MSG = "Must be at least 2 characters.";
export const NAME_TOO_LONG_MSG = "Must be at most 80 characters.";
export const NAME_INVALID_CHARS_MSG =
  "May only contain letters, spaces, hyphens, and apostrophes.";
export const NAME_NO_LETTER_MSG = "Must contain at least one letter.";

export const PHONE_E164_MSG =
  "Phone number must be in E.164 format (e.g. +919876543210).";
export const PHONE_MAX_LENGTH_MSG =
  "Maximum 15 digits allowed in E.164 format.";

export function cleanText(value: string): string {
  return (value ?? "").replaceAll(INVISIBLE_CHARS, "").trim();
}

// ES5-safe character checks (tsconfig target is es5; avoid \p{…} /u regex).
const LETTER_OR_MARK_RE =
  /[A-Za-z\u00C0-\u024F]|[\u0300-\u036F]|[\u0900-\u0D7F]/;

function isLetterOrMark(char: string): boolean {
  return LETTER_OR_MARK_RE.test(char);
}

function isDigit(char: string): boolean {
  return /[0-9]/.test(char);
}

export function validateOrganisation(value: string): string | undefined {
  const trimmed = cleanText(value);
  if (!trimmed) return ORG_REQUIRED_MSG;
  if (trimmed.length < 2) return ORG_TOO_SHORT_MSG;
  if (trimmed.length > 100) return ORG_TOO_LONG_MSG;

  let hasAlnum = false;
  for (const char of trimmed) {
    if (isLetterOrMark(char) || isDigit(char)) {
      hasAlnum = true;
    } else if (!ORG_PUNCT.has(char)) {
      return ORG_INVALID_CHARS_MSG;
    }
  }
  if (!hasAlnum) return ORG_NO_ALNUM_MSG;
  return undefined;
}

export function validatePersonName(
  value: string,
  options: { requiredMessage: string }
): string | undefined {
  const trimmed = cleanText(value);
  if (!trimmed) return options.requiredMessage;
  if (trimmed.length < 2) return NAME_TOO_SHORT_MSG;
  if (trimmed.length > 80) return NAME_TOO_LONG_MSG;

  let hasLetter = false;
  for (const char of trimmed) {
    if (isLetterOrMark(char)) {
      hasLetter = true;
    } else if (!NAME_PUNCT.has(char)) {
      return NAME_INVALID_CHARS_MSG;
    }
  }
  if (!hasLetter) return NAME_NO_LETTER_MSG;
  return undefined;
}

export function validateContactName(value: string): string | undefined {
  return validatePersonName(value, { requiredMessage: CONTACT_NAME_REQUIRED_MSG });
}

export function validateFullName(value: string): string | undefined {
  return validatePersonName(value, { requiredMessage: FULL_NAME_REQUIRED_MSG });
}

/** Format-only check for optional name fields on edit forms. */
export function validateOptionalPersonName(value: string): string | undefined {
  const trimmed = cleanText(value);
  if (!trimmed) return undefined;
  if (trimmed.length < 2) return NAME_TOO_SHORT_MSG;
  if (trimmed.length > 80) return NAME_TOO_LONG_MSG;

  let hasLetter = false;
  for (const char of trimmed) {
    if (isLetterOrMark(char)) {
      hasLetter = true;
    } else if (!NAME_PUNCT.has(char)) {
      return NAME_INVALID_CHARS_MSG;
    }
  }
  if (!hasLetter) return NAME_NO_LETTER_MSG;
  return undefined;
}

export function normalizePhoneInput(value: string): string {
  return cleanText(value).replaceAll(PHONE_FORMAT_CHARS, "");
}

export function validateE164Phone(value: string): string | undefined {
  const trimmed = cleanText(value);
  if (!trimmed) return undefined;
  // API returns masked phone; skip format checks when echoed back unchanged.
  if (trimmed.includes("*")) return undefined;
  const normalized = normalizePhoneInput(trimmed);

  if (normalized.startsWith("+")) {
    const digits = normalized.slice(1);
    if (/^\d+$/.test(digits) && digits.length > 15) {
      return PHONE_MAX_LENGTH_MSG;
    }
  }

  if (!E164_RE.test(normalized)) return PHONE_E164_MSG;
  return undefined;
}

export function validateOrganisationUnique(
  organisation: string,
  tenants: TenantView[],
  excludeTenantId?: string
): string | undefined {
  const normalized = cleanText(organisation).toLowerCase();
  if (!normalized) return undefined;
  const duplicate = tenants.some((t) => {
    if (excludeTenantId && t.tenant_id === excludeTenantId) return false;
    return cleanText(t.organisation ?? "").toLowerCase() === normalized;
  });
  return duplicate ? ORG_DUPLICATE_MSG : undefined;
}

export function setFieldError(
  errors: Record<string, string>,
  field: string,
  error: string | undefined
): Record<string, string> {
  const next = { ...errors };
  if (error) next[field] = error;
  else delete next[field];
  return next;
}
