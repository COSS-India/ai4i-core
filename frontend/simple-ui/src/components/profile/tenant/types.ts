import type { useTenantManagement } from "../hooks/useTenantManagement";

export type TenantManagementState = ReturnType<typeof useTenantManagement>;

export interface TenantTabContext {
  tm: TenantManagementState;
  isAdmin: boolean;
}
