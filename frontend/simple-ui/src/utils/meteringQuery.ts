import { keepPreviousData } from "@tanstack/react-query";
import { METERING } from "../config/meteringConstants";

export const meteringQueryDefaults = {
  staleTime: METERING.QUERY.STALE_TIME_MS,
  // refreshNonce bumps the query key; keep prior data so Refresh does not
  // flash a skeleton / leave cold cache entries looking empty.
  placeholderData: keepPreviousData,
} as const;

export function meteringQueryKey(scope: string, ...parts: unknown[]) {
  return ["metering", scope, ...parts] as const;
}
