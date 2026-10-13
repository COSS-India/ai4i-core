import { keepPreviousData } from "@tanstack/react-query";
import { METERING } from "../config/meteringConstants";

/**
 * True for the API's rejection of a period (422, `detail.code` "INVALID_PERIOD"),
 * from either the raw axios client or BaseApiService (which keeps `response`).
 */
export function isInvalidPeriodError(error: unknown): boolean {
  const response = (error as { response?: { status?: number; data?: unknown } } | null)?.response;
  if (response?.status !== 422) return false;
  const detail = (response.data as { detail?: unknown } | undefined)?.detail;
  return (detail as { code?: unknown } | undefined)?.code === METERING.ERRORS.INVALID_PERIOD_CODE;
}

/** One retry, as elsewhere — but a rejected period fails the same way every time. */
export function retryUnlessInvalidPeriod(failureCount: number, error: unknown): boolean {
  return failureCount < 1 && !isInvalidPeriodError(error);
}

export const meteringQueryDefaults = {
  staleTime: METERING.QUERY.STALE_TIME_MS,
  retry: retryUnlessInvalidPeriod,
  // refreshNonce bumps the query key; keep prior data so Refresh does not
  // flash a skeleton / leave cold cache entries looking empty.
  placeholderData: keepPreviousData,
} as const;

export function meteringQueryKey(scope: string, ...parts: unknown[]) {
  return ["metering", scope, ...parts] as const;
}
