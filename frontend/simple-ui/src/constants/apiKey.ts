// API key status filters and display helpers

import {
  isTenantLifecycleBlockingUsers,
  isTenantStatus,
  TENANT,
} from "./tenant";

/** API key list filter + effective display status (aligns with auth-service effective_is_active). */
export const API_KEY = {
  FILTER_STATUS: {
    ALL: "all",
    ACTIVE: "active",
    INACTIVE: "inactive",
    REVOKED: "revoked",
  },
  DISPLAY_STATUS: {
    ACTIVE: "active",
    INACTIVE: "inactive",
    REVOKED: "revoked",
  },
} as const;

export type ApiKeyFilterStatusValue =
  (typeof API_KEY.FILTER_STATUS)[keyof typeof API_KEY.FILTER_STATUS];

export type ApiKeyDisplayStatusValue =
  (typeof API_KEY.DISPLAY_STATUS)[keyof typeof API_KEY.DISPLAY_STATUS];

export const API_KEY_FILTER_STATUS_LIST: readonly Exclude<
  ApiKeyFilterStatusValue,
  typeof API_KEY.FILTER_STATUS.ALL
>[] = [
  API_KEY.FILTER_STATUS.ACTIVE,
  API_KEY.FILTER_STATUS.INACTIVE,
  API_KEY.FILTER_STATUS.REVOKED,
];

const API_KEY_STATUS_LABELS: Record<ApiKeyDisplayStatusValue, string> = {
  [API_KEY.DISPLAY_STATUS.ACTIVE]: "Active",
  [API_KEY.DISPLAY_STATUS.INACTIVE]: "Inactive",
  [API_KEY.DISPLAY_STATUS.REVOKED]: "Revoked",
};

/** Owner + tenant context for deriving effective API key status in the UI. */
export type ApiKeyAccessContext = {
  userIsActive?: boolean;
  userTenantActive?: boolean | null;
  tenantStatus?: string | null;
};

export type ApiKeyStatusSource = {
  is_active?: boolean;
  is_revoked?: boolean;
  expires_at?: string | null;
};

export function isApiKeyExpired(expiresAt?: string | null): boolean {
  if (!expiresAt) return false;
  try {
    return new Date(expiresAt).getTime() < Date.now();
  } catch {
    return false;
  }
}

/** Mirrors auth-service APIKeyService.user_may_use_api_keys (frontend-only). */
export function userMayUseApiKeys(context: ApiKeyAccessContext): boolean {
  if (context.userIsActive === false) return false;
  if (context.userTenantActive === false) return false;
  if (isTenantLifecycleBlockingUsers(context.tenantStatus)) return false;
  return true;
}

/**
 * Effective API key status for UI badges/filters.
 * DB ``is_active`` false = Revoked; otherwise blocked access = Inactive.
 */
export function resolveApiKeyDisplayStatus(
  key: ApiKeyStatusSource,
  context: ApiKeyAccessContext = {}
): ApiKeyDisplayStatusValue {
  if (key.is_active === false || key.is_revoked === true) {
    return API_KEY.DISPLAY_STATUS.REVOKED;
  }
  if (isApiKeyExpired(key.expires_at)) {
    return API_KEY.DISPLAY_STATUS.INACTIVE;
  }
  if (!userMayUseApiKeys(context)) {
    return API_KEY.DISPLAY_STATUS.INACTIVE;
  }
  return API_KEY.DISPLAY_STATUS.ACTIVE;
}

export function isApiKeyEffectivelyActive(
  key: ApiKeyStatusSource,
  context: ApiKeyAccessContext = {}
): boolean {
  return resolveApiKeyDisplayStatus(key, context) === API_KEY.DISPLAY_STATUS.ACTIVE;
}

/** Human-readable reason when status is Inactive (empty for Active/Revoked). */
export function getApiKeyInactiveReason(context: ApiKeyAccessContext): string {
  if (context.userIsActive === false) {
    return "Your account is inactive.";
  }
  if (context.userTenantActive === false) {
    return "Tenant access is suspended for your account.";
  }
  if (isTenantStatus(context.tenantStatus, TENANT.STATUS.SUSPENDED)) {
    return "Tenant is suspended — API keys are not usable until the tenant is reactivated.";
  }
  if (isTenantStatus(context.tenantStatus, TENANT.STATUS.DEACTIVATED)) {
    return "Tenant is deactivated — API keys are not usable until the tenant is reactivated.";
  }
  return "API key access is currently blocked.";
}

export function getApiKeyDisplayStatusColorScheme(
  status: ApiKeyDisplayStatusValue
): string {
  switch (status) {
    case API_KEY.DISPLAY_STATUS.ACTIVE:
      return "green";
    case API_KEY.DISPLAY_STATUS.INACTIVE:
      return "orange";
    case API_KEY.DISPLAY_STATUS.REVOKED:
      return "red";
    default:
      return "gray";
  }
}

export function formatApiKeyDisplayStatusLabel(
  status: ApiKeyDisplayStatusValue
): string {
  return API_KEY_STATUS_LABELS[status] ?? status;
}

export function formatApiKeyFilterStatusLabel(status: string): string {
  const key = status.trim().toLowerCase() as ApiKeyDisplayStatusValue;
  return API_KEY_STATUS_LABELS[key] ?? status;
}

export function formatApiKeyActiveLabel(isActive: boolean): string {
  return isActive
    ? API_KEY_STATUS_LABELS[API_KEY.DISPLAY_STATUS.ACTIVE]
    : API_KEY_STATUS_LABELS[API_KEY.DISPLAY_STATUS.REVOKED];
}

export function isApiKeyFilterStatus(
  actual: string,
  expected: Exclude<ApiKeyFilterStatusValue, typeof API_KEY.FILTER_STATUS.ALL>
): boolean {
  return actual.trim().toLowerCase() === expected;
}

/** Inference permission IDs → display names when GET /permissions is unavailable. */
export const INFERENCE_PERMISSION_LABEL_BY_ID: Record<number, string> = {
  60: "NMT.INFERENCE",
  61: "ASR.INFERENCE",
  62: "TTS.INFERENCE",
  63: "LLM.INFERENCE",
  64: "NER.INFERENCE",
  65: "OCR.INFERENCE",
  66: "TRANSLITERATION.INFERENCE",
  67: "LANGUAGE-DETECTION.INFERENCE",
  68: "LANGUAGE-DIARIZATION.INFERENCE",
  69: "SPEAKER-DIARIZATION.INFERENCE",
  70: "AUDIO-LANG-DETECTION.INFERENCE",
  71: "PIPELINE.INFERENCE",
};
