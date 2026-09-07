import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import type { AllocationUpdate } from "../types/application";

const SILENT = { suppressErrorAlert: true as const };

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export type AllocationValue = AllocationUpdate["allocation"];

export interface ApiKeyAllocationRow {
  api_key_id: number;
  allocation: AllocationValue;
}

export function getAllocationErrorCode(error: unknown): string | null {
  const data = asRecord((error as { response?: { data?: unknown } })?.response?.data);
  const detail = asRecord(data?.detail);
  const code = detail?.error ?? data?.error ?? data?.code;
  return code == null ? null : String(code).toUpperCase();
}

export async function updateApiKeyAllocations(
  applicationId: number,
  applicationAllocation: AllocationValue,
  apiKeys: ApiKeyAllocationRow[],
): Promise<void> {
  const body = {
    application_id: applicationId,
    allocation: applicationAllocation,
    api_keys: apiKeys,
  };
  await apiService.put(
    apiEndpoints.applications.budgetAllocation(String(applicationId)),
    body,
    SILENT,
  );
}
