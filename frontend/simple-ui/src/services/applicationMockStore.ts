/**
 * In-memory Application store for UI review.
 * Delete this file when USE_APPLICATION_MOCKS is set to false.
 */

import type {
  AllocationUpdate,
  Application,
  ApplicationListResult,
  CreateApplicationPayload,
  ListApplicationsParams,
  UpdateApplicationPayload,
} from "../types/application";

export const MOCK_TENANT_BUDGET = 100_000;
const DEFAULT_PAGE_SIZE = 20;

function fail(status: number, code: string, message: string): never {
  const err = new Error(message) as Error & {
    status: number;
    response: { status: number; data: { detail: { error: string; message: string } } };
  };
  err.status = status;
  err.response = {
    status,
    data: { detail: { error: code, message } },
  };
  throw err;
}

function nowIso(): string {
  return new Date().toISOString();
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function toBudget(pct: number | null, tenantBudget: number): number | null {
  if (pct == null) return null;
  return Math.round((pct / 100) * tenantBudget);
}

function seedApps(tenantId: string): Application[] {
  const created = "2026-08-10T09:00:00Z";
  return [
    {
      application_id: "app-a",
      tenant_id: tenantId,
      name: "App A",
      description: "Citizen-facing services portal.",
      domain: "marketing",
      allocated_percentage: 50,
      allocated_budget: toBudget(50, MOCK_TENANT_BUDGET),
      consumed_percentage: 40,
      consumed_budget: toBudget(40, MOCK_TENANT_BUDGET) ?? 0,
      status: "ACTIVE",
      created_at: created,
      updated_at: created,
      api_key_count: 2,
    },
    {
      application_id: "app-b",
      tenant_id: tenantId,
      name: "App B",
      description: "Support and grievance desk.",
      domain: "support",
      allocated_percentage: 30,
      allocated_budget: toBudget(30, MOCK_TENANT_BUDGET),
      consumed_percentage: 30,
      consumed_budget: toBudget(30, MOCK_TENANT_BUDGET) ?? 0,
      status: "ACTIVE",
      created_at: created,
      updated_at: created,
      api_key_count: 1,
    },
    {
      application_id: "app-c",
      tenant_id: tenantId,
      name: "App C",
      description: "Internal operations console.",
      domain: "ops",
      allocated_percentage: 20,
      allocated_budget: toBudget(20, MOCK_TENANT_BUDGET),
      consumed_percentage: 5,
      consumed_budget: toBudget(5, MOCK_TENANT_BUDGET) ?? 0,
      status: "ACTIVE",
      created_at: created,
      updated_at: created,
      api_key_count: 1,
    },
    {
      application_id: "app-d",
      tenant_id: tenantId,
      name: "Sandbox Tools",
      description: "Uncapped sandbox — no Budget ceiling.",
      domain: "internal",
      allocated_percentage: null,
      allocated_budget: null,
      consumed_percentage: 0,
      consumed_budget: 0,
      status: "ACTIVE",
      created_at: created,
      updated_at: created,
      api_key_count: 0,
    },
  ];
}

const appsByTenant = new Map<string, Application[]>();

function appsFor(tenantId: string): Application[] {
  const key = String(tenantId);
  if (!appsByTenant.has(key)) appsByTenant.set(key, seedApps(key));
  return appsByTenant.get(key)!;
}

function allocatedTotal(apps: Application[]): number {
  return apps.reduce((sum, app) => sum + (app.allocated_percentage ?? 0), 0);
}

function findByName(apps: Application[], name: string, exceptId?: string): Application | undefined {
  const needle = name.trim().toLowerCase();
  return apps.find(
    (app) =>
      app.name.trim().toLowerCase() === needle &&
      (exceptId == null || app.application_id !== exceptId),
  );
}

function wait(): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, 180);
  });
}

export async function mockListApplications(
  tenantId: string,
  params: ListApplicationsParams = {},
): Promise<ApplicationListResult> {
  await wait();
  const apps = appsFor(tenantId);
  const search = (params.search ?? "").trim().toLowerCase();
  const domain = (params.domain ?? "").trim().toLowerCase();
  const page = Math.max(1, params.page ?? 1);
  const size = Math.max(1, params.size ?? DEFAULT_PAGE_SIZE);

  const filtered = apps.filter((app) => {
    const matchesSearch =
      !search ||
      app.name.toLowerCase().includes(search) ||
      app.domain.toLowerCase().includes(search);
    const matchesDomain = !domain || app.domain.toLowerCase() === domain;
    return matchesSearch && matchesDomain;
  });

  const start = (page - 1) * size;
  return {
    tenant_id: String(tenantId),
    tenant_allocated_budget: MOCK_TENANT_BUDGET,
    total_allocated_percentage: allocatedTotal(apps),
    applications: clone(filtered.slice(start, start + size)),
    pagination: { page, size, total: filtered.length },
  };
}

export async function mockGetApplication(
  tenantId: string,
  applicationId: string,
): Promise<Application> {
  await wait();
  const app = appsFor(tenantId).find((a) => a.application_id === applicationId);
  if (!app) fail(404, "NOT_FOUND", "Application not found.");
  return clone(app);
}

export async function mockCreateApplication(
  tenantId: string,
  payload: CreateApplicationPayload,
  tenantBudget = MOCK_TENANT_BUDGET,
): Promise<Application> {
  await wait();
  const name = payload.name.trim();
  if (!name) fail(422, "VALIDATION_ERROR", "Application name is required.");
  const apps = appsFor(tenantId);
  if (findByName(apps, name)) {
    fail(409, "APPLICATION_NAME_ALREADY_EXISTS", "An Application with this name already exists.");
  }

  const pct = payload.allocated_percentage;
  if (pct != null) {
    if (pct < 0) fail(422, "VALIDATION_ERROR", "Budget cannot be negative.");
    const remaining = 100 - allocatedTotal(apps);
    if (pct > remaining + 1e-6) {
      fail(
        422,
        "ALLOCATION_TOTAL_EXCEEDED",
        `Budget cannot exceed ${Math.max(0, remaining).toFixed(2)}% remaining.`,
      );
    }
  }

  const created: Application = {
    application_id: `app-${Date.now()}`,
    tenant_id: String(tenantId),
    name,
    description: (payload.description ?? "").trim(),
    domain: (payload.domain ?? "").trim(),
    allocated_percentage: pct ?? null,
    allocated_budget: toBudget(pct ?? null, tenantBudget),
    consumed_percentage: 0,
    consumed_budget: 0,
    status: "ACTIVE",
    created_at: nowIso(),
    updated_at: nowIso(),
    api_key_count: 0,
  };
  apps.push(created);
  return clone(created);
}

export async function mockUpdateApplication(
  tenantId: string,
  applicationId: string,
  payload: UpdateApplicationPayload,
): Promise<Application> {
  await wait();
  if ("allocated_percentage" in payload || "allocated_budget" in payload) {
    fail(
      422,
      "ALLOCATION_FIELD_NOT_ALLOWED_ON_EDIT",
      "Budget cannot be changed on this form.",
    );
  }
  const apps = appsFor(tenantId);
  const app = apps.find((a) => a.application_id === applicationId);
  if (!app) fail(404, "NOT_FOUND", "Application not found.");
  if (payload.name != null) {
    const name = payload.name.trim();
    if (!name) fail(422, "VALIDATION_ERROR", "Application name is required.");
    if (findByName(apps, name, applicationId)) {
      fail(409, "APPLICATION_NAME_ALREADY_EXISTS", "An Application with this name already exists.");
    }
    app.name = name;
  }
  if (payload.description != null) app.description = payload.description.trim();
  if (payload.domain != null) app.domain = payload.domain.trim();
  app.updated_at = nowIso();
  return clone(app);
}

export async function mockUpdateAllocations(
  tenantId: string,
  updates: AllocationUpdate[],
  tenantBudget = MOCK_TENANT_BUDGET,
): Promise<Application[]> {
  await wait();
  const apps = appsFor(tenantId);
  const nextById = new Map(apps.map((a) => [a.application_id, a.allocated_percentage]));
  for (const row of updates) {
    const current = apps.find((a) => a.application_id === row.application_id);
    if (!current) fail(404, "NOT_FOUND", "Application not found.");
    if (row.allocated_percentage < current.consumed_percentage - 1e-6) {
      fail(
        422,
        "ALLOCATION_BELOW_CONSUMED",
        `Cannot go below ${current.consumed_percentage.toFixed(2)}% already consumed by ${current.name}.`,
      );
    }
    nextById.set(row.application_id, row.allocated_percentage);
  }
  const nextTotal = Array.from(nextById.values()).reduce(
    (sum: number, pct) => sum + (pct ?? 0),
    0,
  );
  if (nextTotal > 100 + 1e-6) {
    fail(
      422,
      "ALLOCATION_TOTAL_EXCEEDED",
      `Total across Applications would be ${nextTotal.toFixed(2)}% — over 100%.`,
    );
  }

  const changed: Application[] = [];
  for (const row of updates) {
    const app = apps.find((a) => a.application_id === row.application_id)!;
    app.allocated_percentage = row.allocated_percentage;
    app.allocated_budget = toBudget(row.allocated_percentage, tenantBudget);
    app.updated_at = nowIso();
    changed.push(clone(app));
  }
  return changed;
}

export function mockListDomains(tenantId: string): string[] {
  return Array.from(
    new Set(
      appsFor(tenantId)
        .map((a) => a.domain)
        .filter(Boolean),
    ),
  ).sort((a, b) => a.localeCompare(b));
}
