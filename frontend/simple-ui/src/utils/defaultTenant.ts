import type { User } from "../types/auth";
import type { TenantUserView, TenantView } from "../types/tenant";

/** Must match auth-service `default_tenant_org` / seed migration. */
export const DEFAULT_TENANT_ORGANISATION =
  (process.env.NEXT_PUBLIC_DEFAULT_TENANT_ORG || "default organisation").trim();

export function resolveDefaultTenantId(tenants: TenantView[]): string | null {
  const target = DEFAULT_TENANT_ORGANISATION.toLowerCase();
  const match = tenants.find(
    (t) => (t.organisation || "").trim().toLowerCase() === target
  );
  return match?.tenant_id?.trim() || null;
}

export function isDefaultTenantOrg(organisation?: string | null): boolean {
  return (organisation ?? "").trim().toLowerCase() === DEFAULT_TENANT_ORGANISATION.toLowerCase();
}

export function isDefaultTenant(tenant: { organisation?: string | null }): boolean {
  return isDefaultTenantOrg(tenant.organisation);
}

/** Map tenant user rows for Profile → Roles picker (auth `User` shape). */
export function tenantUsersToAuthUsers(rows: TenantUserView[]): User[] {
  return rows.map((u) => ({
    user_id: u.user_id,
    email: u.email,
    username: u.username,
    full_name: u.full_name ?? undefined,
    phone_number: u.phone_number ?? undefined,
    is_active: u.is_active,
    is_tenant_active: u.is_tenant_active ?? undefined,
    roles: u.roles,
  }));
}
