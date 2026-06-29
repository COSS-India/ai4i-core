// Client-side field rules for tenant + tenant user create/edit forms.

import type { TenantView } from "../types/tenant";
import { VALIDATION } from "../constants/validation";

const INVISIBLE_CHARS = /[\u00AD\u200B-\u200D\u2060\uFEFF\u2028\u2029\u200E\u200F]+/g;
const PHONE_FORMAT_CHARS = /[ \-().]/g;
const E164_RE = /^\+[1-9]\d{1,14}$/;
const ORG_PUNCT = new Set([" ", "-", ".", "'"]);
const NAME_PUNCT = new Set([" ", "-", "'"]);

export function cleanText(value: string): string {
  return (value ?? "").replaceAll(INVISIBLE_CHARS, "").trim();
}

// ES5-safe character checks (tsconfig target is es5; avoid \p{…} /u regex).
const LETTER_OR_MARK_RE =
  /[A-Za-z\u00C0-\u024F]|[\u0300-\u036F]|[\u0900-\u097F]|[\u0980-\u09FF]|[\u0A00-\u0A7F]/;

function isLetterOrMark(char: string): boolean {
  return LETTER_OR_MARK_RE.test(char);
}

function isDigit(char: string): boolean {
  return /[0-9]/.test(char);
}

export function validateOrganisation(value: string): string | undefined {
  const trimmed = cleanText(value);
  if (!trimmed) return VALIDATION.ORG.REQUIRED;
  if (trimmed.length < VALIDATION.ORG.MIN_LENGTH) return VALIDATION.ORG.TOO_SHORT;
  if (trimmed.length > VALIDATION.ORG.MAX_LENGTH) return VALIDATION.ORG.TOO_LONG;

  let hasAlnum = false;
  for (const char of trimmed) {
    if (isLetterOrMark(char) || isDigit(char)) {
      hasAlnum = true;
    } else if (!ORG_PUNCT.has(char)) {
      return VALIDATION.ORG.INVALID_CHARS;
    }
  }
  if (!hasAlnum) return VALIDATION.ORG.NO_ALNUM;
  return undefined;
}

export function validatePersonName(
  value: string,
  options: { requiredMessage: string }
): string | undefined {
  const trimmed = cleanText(value);
  if (!trimmed) return options.requiredMessage;
  if (trimmed.length < VALIDATION.NAME.MIN_LENGTH) return VALIDATION.NAME.TOO_SHORT;
  if (trimmed.length > VALIDATION.NAME.MAX_LENGTH) return VALIDATION.NAME.TOO_LONG;

  let hasLetter = false;
  for (const char of trimmed) {
    if (isLetterOrMark(char)) {
      hasLetter = true;
    } else if (!NAME_PUNCT.has(char)) {
      return VALIDATION.NAME.INVALID_CHARS;
    }
  }
  if (!hasLetter) return VALIDATION.NAME.NO_LETTER;
  return undefined;
}

export function validateContactName(value: string): string | undefined {
  return validatePersonName(value, { requiredMessage: VALIDATION.NAME.CONTACT_REQUIRED });
}

export function validateFullName(value: string): string | undefined {
  return validatePersonName(value, { requiredMessage: VALIDATION.NAME.FULL_REQUIRED });
}

/** Format-only check for optional name fields on edit forms. */
export function validateOptionalPersonName(value: string): string | undefined {
  const trimmed = cleanText(value);
  if (!trimmed) return undefined;
  if (trimmed.length < VALIDATION.NAME.MIN_LENGTH) return VALIDATION.NAME.TOO_SHORT;
  if (trimmed.length > VALIDATION.NAME.MAX_LENGTH) return VALIDATION.NAME.TOO_LONG;

  let hasLetter = false;
  for (const char of trimmed) {
    if (isLetterOrMark(char)) {
      hasLetter = true;
    } else if (!NAME_PUNCT.has(char)) {
      return VALIDATION.NAME.INVALID_CHARS;
    }
  }
  if (!hasLetter) return VALIDATION.NAME.NO_LETTER;
  return undefined;
}

export function normalizePhoneInput(value: string): string {
  return cleanText(value).replaceAll(PHONE_FORMAT_CHARS, "");
}

export function validateE164Phone(value: string): string | undefined {
  const trimmed = cleanText(value);
  if (!trimmed) return undefined;
  const normalized = normalizePhoneInput(trimmed);
  if (!E164_RE.test(normalized)) return VALIDATION.PHONE.E164;
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
  return duplicate ? VALIDATION.ORG.DUPLICATE : undefined;
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
