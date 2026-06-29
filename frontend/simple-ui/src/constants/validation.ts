// Form validation messages and text-input patterns

export const VALIDATION = {
  ORG: {
    REQUIRED: "Organisation is required.",
    TOO_SHORT: "Organisation must be at least 2 characters.",
    TOO_LONG: "Organisation must be at most 100 characters.",
    INVALID_CHARS:
      "Organisation may only contain letters, digits, spaces, hyphens, dots, and apostrophes.",
    NO_ALNUM: "Organisation must contain at least one letter or digit.",
    DUPLICATE: "A tenant with this organisation name already exists.",
    MIN_LENGTH: 2,
    MAX_LENGTH: 100,
  },
  NAME: {
    CONTACT_REQUIRED: "Contact name is required.",
    FULL_REQUIRED: "Full name is required.",
    TOO_SHORT: "Must be at least 2 characters.",
    TOO_LONG: "Must be at most 80 characters.",
    INVALID_CHARS: "May only contain letters, spaces, hyphens, and apostrophes.",
    NO_LETTER: "Must contain at least one letter.",
    MIN_LENGTH: 2,
    MAX_LENGTH: 80,
  },
  EMAIL: {
    REQUIRED: "Email is required.",
    INVALID_FORMAT: "Enter a valid email address (e.g. example@domain.com).",
    USER_ALREADY_EXISTS: "A user with this email address already exists.",
    ALREADY_EXISTS: "This email is already associated with an existing account",
    AVAILABLE: "Email is available.",
    CHECK_DEBOUNCE_MS: 400,
  },
  PHONE: {
    E164: "Phone number must be in E.164 format (e.g. +919876543210).",
  },
} as const;

const INDIC_CODEPOINT_MIN = 0x0900;
const INDIC_CODEPOINT_MAX = 0x0dff;

const ALLOWED_SPECIAL_CHARS = new Set(
  ' .,!?;:\'"-–—()[]{}@#$%&*+=/\\<>~`'.split(""),
);

function isAllowedLatinChar(char: string): boolean {
  const code = char.codePointAt(0);
  if (code === undefined) return false;
  if (code >= 0x41 && code <= 0x5a) return true;
  if (code >= 0x61 && code <= 0x7a) return true;
  if (code >= 0x30 && code <= 0x39) return true;
  if (/\s/.test(char)) return true;
  return ALLOWED_SPECIAL_CHARS.has(char);
}

/** Validates Indic + Latin text for inference inputs (replaces complex regex). */
export function isIndicTextInputValid(text: string): boolean {
  for (const char of text) {
    const codePoint = char.codePointAt(0);
    if (codePoint === undefined) return false;
    if (codePoint >= INDIC_CODEPOINT_MIN && codePoint <= INDIC_CODEPOINT_MAX) continue;
    if (isAllowedLatinChar(char)) continue;
    return false;
  }
  return true;
}
