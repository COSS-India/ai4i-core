import type { CreationType } from "../types/tenant";

/**
 * Registration Method for Default Institution users, derived from auth-service
 * `users.creation_type`:
 *  - `default` (email sign-up) and `google` (Google OAuth) → Self-registration
 *  - `tenant` (added by the Adopter Admin)                → Admin registration
 *
 * Self-registered users are unvetted and must stay on the USER role.
 */
export const REGISTRATION_METHOD = {
  SELF: "self",
  ADMIN: "admin",
} as const;

export type RegistrationMethod =
  (typeof REGISTRATION_METHOD)[keyof typeof REGISTRATION_METHOD];

const CREATION_TYPE_TO_REGISTRATION_METHOD: Record<CreationType, RegistrationMethod> = {
  default: REGISTRATION_METHOD.SELF,
  google: REGISTRATION_METHOD.SELF,
  tenant: REGISTRATION_METHOD.ADMIN,
};

export const REGISTRATION_METHOD_OPTIONS = [
  { value: REGISTRATION_METHOD.SELF, label: "Self-registration", colorScheme: "orange" },
  { value: REGISTRATION_METHOD.ADMIN, label: "Admin registration", colorScheme: "blue" },
] as const;

export const SELF_REGISTERED_ROLE_LOCKED_MESSAGE =
  "Role cannot be changed for self-registered users.";

/** Returns null when `creation_type` is missing or unrecognised. */
export function resolveRegistrationMethod(user: {
  creation_type?: string | null;
}): RegistrationMethod | null {
  const key = (user.creation_type ?? "").trim().toLowerCase() as CreationType;
  return CREATION_TYPE_TO_REGISTRATION_METHOD[key] ?? null;
}

export function isSelfRegisteredUser(user: { creation_type?: string | null }): boolean {
  return resolveRegistrationMethod(user) === REGISTRATION_METHOD.SELF;
}

export function getRegistrationMethodOption(method: RegistrationMethod | null) {
  return REGISTRATION_METHOD_OPTIONS.find((o) => o.value === method) ?? null;
}
