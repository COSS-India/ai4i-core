/**
 * Track tenants deactivated from PENDING (never verified) — a terminal soft delete.
 * FE-only: the API does not expose onboarding state; we persist IDs in sessionStorage
 * so a refresh still hides row actions for these tenants.
 */

import type { TenantView } from "../types/tenant";
import { TENANT, isTenantStatus } from "../config/constants";

const STORAGE_KEY = "tenantPendingSoftDeletedIds";

function readIds(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.map(String));
  } catch {
    return new Set();
  }
}

function writeIds(ids: Set<string>): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(ids)));
}

/** Mark a tenant as soft-deleted from PENDING (terminal — no further actions). */
export function markPendingSoftDeletedTenant(tenantId: string): void {
  const ids = readIds();
  ids.add(String(tenantId));
  writeIds(ids);
}

/** True when this DEACTIVATED tenant was deactivated from PENDING verification. */
export function isPendingSoftDeletedTenant(t: TenantView): boolean {
  if (t.onboarding_completed === false) return true;
  if (!isTenantStatus(t.status, TENANT.STATUS.DEACTIVATED)) return false;
  return readIds().has(String(t.tenant_id));
}

/** Apply client-side onboarding flags after loading tenants from the API. */
export function applyTenantPendingSoftDeleteFlags(
  tenants: TenantView[],
): TenantView[] {
  const ids = readIds();
  if (ids.size === 0) return tenants;
  return tenants.map((t) =>
    ids.has(String(t.tenant_id))
      ? { ...t, onboarding_completed: false }
      : t,
  );
}
