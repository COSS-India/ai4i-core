import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import { USE_APPLICATION_MOCKS } from "../config/useApplicationMocks";
import type {
  AllocationUpdate,
  Application,
  ApplicationListResult,
  CreateApplicationPayload,
  ListApplicationsParams,
  UpdateApplicationPayload,
} from "../types/application";

const SILENT = { suppressErrorAlert: true as const };

type ApplicationMockStore = typeof import("./applicationMockStore");

async function loadApplicationMockStore(): Promise<ApplicationMockStore> {
  return import("./applicationMockStore");
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function asString(value: unknown): string {
  return value == null ? "" : String(value);
}

function normalizeApplication(raw: unknown, fallbackTenantId: string): Application {
  const row = asRecord(raw) ?? {};
  return {
    application_id: asString(row.application_id ?? row.id),
    tenant_id: asString(row.tenant_id ?? fallbackTenantId),
    name: asString(row.name),
    description: asString(row.description),
    domain: asString(row.domain),
    allocated_percentage: asNumber(row.allocated_percentage),
    allocated_budget: asNumber(row.allocated_budget),
    consumed_percentage: asNumber(row.consumed_percentage),
    consumed_budget: asNumber(row.consumed_budget),
    status: row.status === "INACTIVE" ? "INACTIVE" : "ACTIVE",
    created_at: asString(row.created_at),
    updated_at: row.updated_at == null ? null : asString(row.updated_at),
    api_key_count: asNumber(row.api_key_count),
  };
}

/**
 * Auth application APIs return `{ success, data }` (2937 contract).
 * Older deployments may still return a flat resource body — both are supported.
 */
function unwrapEnvelope(payload: unknown): unknown {
  const root = asRecord(payload);
  if (root && "data" in root) return root.data;
  return payload;
}

function normalizeList(payload: unknown, tenantId: string): ApplicationListResult {
  const inner = unwrapEnvelope(payload);
  if (Array.isArray(inner)) {
    return {
      tenant_id: tenantId,
      tenant_allocated_budget: 0,
      total_allocated_percentage: 0,
      applications: inner.map((row) => normalizeApplication(row, tenantId)),
      pagination: {
        page: 1,
        size: inner.length,
        total: inner.length,
      },
    };
  }
  const root = asRecord(inner) ?? {};
  const rows = Array.isArray(root.applications)
    ? root.applications
    : Array.isArray(root.items)
      ? root.items
      : [];
  const pagination = asRecord(root.pagination) ?? {};
  return {
    tenant_id: asString(root.tenant_id ?? tenantId),
    tenant_allocated_budget: asNumber(root.tenant_allocated_budget) ?? 0,
    total_allocated_percentage: asNumber(root.total_allocated_percentage) ?? 0,
    applications: rows.map((row) => normalizeApplication(row, tenantId)),
    pagination: {
      page: asNumber(pagination.page) ?? 1,
      size: asNumber(pagination.size) ?? rows.length,
      total: asNumber(pagination.total) ?? asNumber(root.total) ?? rows.length,
    },
  };
}

export function getApplicationErrorCode(error: unknown): string | null {
  const data = asRecord((error as { response?: { data?: unknown } })?.response?.data);
  const detail = asRecord(data?.detail);
  const code = detail?.error ?? data?.error ?? data?.code;
  return code == null ? null : String(code).toUpperCase();
}

export async function listApplications(
  tenantId: string,
  params: ListApplicationsParams = {},
): Promise<ApplicationListResult> {
  if (USE_APPLICATION_MOCKS) {
    const mocks = await loadApplicationMockStore();
    return mocks.mockListApplications(tenantId, params);
  }
  const response = await apiService.get(apiEndpoints.tenants.applications(tenantId), {
    ...SILENT,
    params: {
      search: params.search || undefined,
      domain: params.domain || undefined,
      page: params.page,
      size: params.size,
    },
  });
  return normalizeList(response.data, tenantId);
}

export async function getApplication(
  tenantId: string,
  applicationId: string,
): Promise<Application> {
  if (USE_APPLICATION_MOCKS) {
    const mocks = await loadApplicationMockStore();
    return mocks.mockGetApplication(tenantId, applicationId);
  }
  const response = await apiService.get(
    apiEndpoints.tenants.application(tenantId, applicationId),
    SILENT,
  );
  return normalizeApplication(unwrapEnvelope(response.data), tenantId);
}

export async function createApplication(
  tenantId: string,
  payload: CreateApplicationPayload,
): Promise<Application> {
  if (USE_APPLICATION_MOCKS) {
    const mocks = await loadApplicationMockStore();
    return mocks.mockCreateApplication(tenantId, payload, mocks.MOCK_TENANT_BUDGET);
  }
  const body: Record<string, unknown> = { name: payload.name };
  if (payload.description) body.description = payload.description;
  if (payload.domain) body.domain = payload.domain;
  if (payload.allocated_percentage != null) {
    body.allocated_percentage = payload.allocated_percentage;
  }
  const response = await apiService.post(
    apiEndpoints.tenants.applications(tenantId),
    body,
    SILENT,
  );
  return normalizeApplication(unwrapEnvelope(response.data), tenantId);
}

export async function updateApplication(
  tenantId: string,
  applicationId: string,
  payload: UpdateApplicationPayload,
): Promise<Application> {
  if (USE_APPLICATION_MOCKS) {
    const mocks = await loadApplicationMockStore();
    return mocks.mockUpdateApplication(tenantId, applicationId, payload);
  }
  const response = await apiService.patch(
    apiEndpoints.tenants.application(tenantId, applicationId),
    payload,
    SILENT,
  );
  return normalizeApplication(unwrapEnvelope(response.data), tenantId);
}

export async function updateApplicationAllocations(
  tenantId: string,
  allocations: AllocationUpdate[],
): Promise<Application[]> {
  if (USE_APPLICATION_MOCKS) {
    const mocks = await loadApplicationMockStore();
    return mocks.mockUpdateAllocations(tenantId, allocations, mocks.MOCK_TENANT_BUDGET);
  }
  const application_allocations = allocations.map((row) => ({
    application_id: Number(row.application_id),
    allocated_percentage: row.allocated_percentage,
  }));
  const response = await apiService.put(
    apiEndpoints.allocations,
    { application_allocations },
    { ...SILENT, params: { tenant_id: tenantId } },
  );
  const data = asRecord(unwrapEnvelope(response.data)) ?? {};
  const rows = Array.isArray(data.application_allocations)
    ? data.application_allocations
    : Array.isArray(data.allocations)
      ? data.allocations
      : [];
  return rows.map((row) => normalizeApplication(row, tenantId));
}

export interface ApplicationApiKeyRow {
  id: number;
  key_name: string;
  allocated_percentage: number;
  allocated_budget: number | null;
  consumed_budget: number | null;
  is_active: boolean;
}

/** GET /auth/api-keys?application_id= — keys under one Application (for budget cascade preview). */
export async function listApplicationApiKeys(
  applicationId: string,
): Promise<ApplicationApiKeyRow[]> {
  const response = await apiService.get(`${apiEndpoints.auth.base}/api-keys`, {
    ...SILENT,
    params: { application_id: applicationId },
  });
  const envelope = unwrapEnvelope(response.data);
  const groups = Array.isArray(envelope) ? envelope : [];
  const targetId = String(applicationId);
  for (const group of groups) {
    const row = asRecord(group);
    if (!row) continue;
    const appId = asString(row.application_id);
    if (appId !== targetId) continue;
    const keyRows = Array.isArray(row.api_keys) ? row.api_keys : [];
    return keyRows.map((raw) => {
      const k = asRecord(raw) ?? {};
      return {
        id: asNumber(k.id) ?? 0,
        key_name: asString(k.key_name),
        allocated_percentage: asNumber(k.allocated_percentage) ?? 0,
        allocated_budget: asNumber(k.allocated_budget),
        consumed_budget: asNumber(k.budget_used ?? k.consumed_budget),
        is_active: k.is_active !== false,
      };
    });
  }
  if (groups.length === 1) {
    const keyRows = Array.isArray(asRecord(groups[0])?.api_keys)
      ? (asRecord(groups[0])!.api_keys as unknown[])
      : [];
    return keyRows.map((raw) => {
      const k = asRecord(raw) ?? {};
      return {
        id: asNumber(k.id) ?? 0,
        key_name: asString(k.key_name),
        allocated_percentage: asNumber(k.allocated_percentage) ?? 0,
        allocated_budget: asNumber(k.allocated_budget),
        consumed_budget: asNumber(k.budget_used ?? k.consumed_budget),
        is_active: k.is_active !== false,
      };
    });
  }
  return [];
}

/** Load every Application for bulk budget edit (ignores table search). */
export async function listAllApplicationsForBudget(tenantId: string): Promise<ApplicationListResult> {
  return listApplications(tenantId, { page: 1, size: 500 });
}
