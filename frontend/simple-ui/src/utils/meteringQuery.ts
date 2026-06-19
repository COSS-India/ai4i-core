import { METERING } from "../config/meteringConstants";

export const meteringQueryDefaults = {
  staleTime: METERING.QUERY.STALE_TIME_MS,
} as const;

export function meteringQueryKey(scope: string, ...parts: unknown[]) {
  return ["metering", scope, ...parts] as const;
}
