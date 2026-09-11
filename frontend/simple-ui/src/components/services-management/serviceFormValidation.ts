/**
 * Create-form validation rules for Service Management.
 *
 * Mirrors platform-core-service's `ServiceCreateRequest`
 * (app/schemas/model_management/service.py) after the ULCA alignment, so
 * admins get inline errors instead of an unexplained 422.
 *
 * The LENGTH rules here are CREATE ONLY — `ServiceUpdateRequest` carries none
 * of them, so the edit flow must not use those helpers. `validatePricePerUnit`
 * is the exception: the same bounds sit on both request schemas, so it applies
 * to create and edit alike.
 */

/** `description` — 25-1000 chars, required (alias: `serviceDescription`). */
export const SERVICE_DESCRIPTION_MIN_LEN = 25;
export const SERVICE_DESCRIPTION_MAX_LEN = 1000;

/** `name` — 5-100 chars, alphanumeric + `-` + `/` only. */
export const SERVICE_NAME_MIN_LEN = 5;
export const SERVICE_NAME_MAX_LEN = 100;

const SERVICE_NAME_PATTERN = /^[a-zA-Z0-9/-]+$/;

/** Strips what the Service Name charset rejects — spaces, `_`, punctuation. */
export const sanitizeServiceName = (value: string): string =>
  value.replaceAll(/[^a-zA-Z0-9/-]/g, "");

/** `inferenceEndPoint.infraDescription` — 5-100 chars (alias: `hardwareDescription`). */
export const INFRA_DESCRIPTION_MIN_LEN = 5;
export const INFRA_DESCRIPTION_MAX_LEN = 100;

/**
 * `serviceId` — min 5 on create only; existing shorter IDs stay readable
 * and deletable, which is why the backend gates this on create too.
 */
export const SERVICE_ID_MIN_LEN = 5;
export const SERVICE_ID_MAX_LEN = 255;

/**
 * Backend compares raw string length, but every create payload field is
 * trimmed before it is sent, so validating the trimmed value is what keeps
 * the inline error and the API verdict in agreement.
 */
const lengthError = (
  label: string,
  value: string | null | undefined,
  min: number,
  max: number,
  { required }: { required: boolean },
): string | null => {
  const trimmed = (value || "").trim();
  if (!trimmed) {
    return required ? `${label} is required.` : null;
  }
  if (trimmed.length < min) {
    return `${label} must be at least ${min} characters.`;
  }
  if (trimmed.length > max) {
    return `${label} must not exceed ${max} characters.`;
  }
  return null;
};

export const validateServiceDescription = (
  value: string | null | undefined,
): string | null =>
  lengthError(
    "Service Description",
    value,
    SERVICE_DESCRIPTION_MIN_LEN,
    SERVICE_DESCRIPTION_MAX_LEN,
    { required: true },
  );

export const validateServiceName = (
  value: string | null | undefined,
): string | null => {
  const lengthIssue = lengthError(
    "Service Name",
    value,
    SERVICE_NAME_MIN_LEN,
    SERVICE_NAME_MAX_LEN,
    { required: true },
  );
  if (lengthIssue) return lengthIssue;
  if (!SERVICE_NAME_PATTERN.test((value || "").trim())) {
    return "Service Name may contain only letters, numbers, hyphens (-) and forward slashes (/).";
  }
  return null;
};

export const validateHardwareDescription = (
  value: string | null | undefined,
): string | null =>
  lengthError(
    "Hardware Description",
    value,
    INFRA_DESCRIPTION_MIN_LEN,
    INFRA_DESCRIPTION_MAX_LEN,
    { required: true },
  );

/**
 * Length only — the charset rule is enforced by the Service ID input, which
 * strips disallowed characters as they are typed.
 */
export const validateServiceIdLength = (
  value: string | null | undefined,
): string | null =>
  lengthError("Service ID", value, SERVICE_ID_MIN_LEN, SERVICE_ID_MAX_LEN, {
    required: true,
  });

/**
 * `costPerUnit` — 0 to 10,000,000, on BOTH `ServiceCreateRequest` and
 * `ServiceUpdateRequest` (`ge=0, le=10_000_000`).
 */
export const PRICE_PER_UNIT_MAX = 10_000_000;

/** Grouped form of the cap, for hint and error copy. */
export const PRICE_PER_UNIT_MAX_LABEL = PRICE_PER_UNIT_MAX.toLocaleString("en-US");

/**
 * Returns a user-facing message for the first problem found, or null when the
 * price is acceptable. 0 is allowed, matching the backend's `ge=0` — a free
 * service is a legitimate configuration.
 */
export const validatePricePerUnit = (value: string): string | null => {
  const trimmed = value.trim();
  if (!trimmed) {
    return "Price per unit size is required.";
  }
  const priceNum = Number(trimmed);
  if (!Number.isFinite(priceNum)) {
    return "Price per unit size must be a number.";
  }
  if (priceNum < 0) {
    return "Price per unit size must be 0 or greater.";
  }
  if (priceNum > PRICE_PER_UNIT_MAX) {
    return `Price per unit size must not exceed ${PRICE_PER_UNIT_MAX_LABEL}.`;
  }
  return null;
};
