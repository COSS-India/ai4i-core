import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";

const SILENT = { suppressErrorAlert: true as const };

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function getAllocationErrorCode(error: unknown): string | null {
  const data = asRecord((error as { response?: { data?: unknown } })?.response?.data);
  const detail = asRecord(data?.detail);
  const code = detail?.error ?? data?.error ?? data?.code;
  return code == null ? null : String(code).toUpperCase();
}

export interface ApiKeyAllocationInput {
  api_key_id: number;
  allocated_percentage?: number;
  allocated_budget?: number;
}

export async function updateApiKeyAllocations(
  applicationId: number,
  allocations: ApiKeyAllocationInput[],
): Promise<void> {
  const body = {
    api_key_allocations: allocations.map((row) => {
      const entry: Record<string, number> = { api_key_id: row.api_key_id };
      if (row.allocated_budget != null) {
        entry.allocated_budget = row.allocated_budget;
      } else if (row.allocated_percentage != null) {
        entry.allocated_percentage = row.allocated_percentage;
      }
      return entry;
    }),
  };
  await apiService.put(apiEndpoints.allocations, body, {
    ...SILENT,
    params: { application_id: applicationId },
  });
}
