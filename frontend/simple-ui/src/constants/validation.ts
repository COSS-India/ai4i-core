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

/** ES5-compatible Indic + Latin text pattern for inference inputs. */
export const INDIC_TEXT_CHAR_REGEX =
  /^(?:[\s.,!?;:'"\-–—()\[\]{}@#$%&*+=\/\\<>~`a-zA-Z0-9]|[\u0900-\u097F]|[\u0980-\u09FF]|[\u0A00-\u0A7F]|[\u0A80-\u0AFF]|[\u0B00-\u0B7F]|[\u0B80-\u0BFF]|[\u0C00-\u0C7F]|[\u0C80-\u0CFF]|[\u0D00-\u0D7F]|[\u0D80-\u0DFF])*$/;
