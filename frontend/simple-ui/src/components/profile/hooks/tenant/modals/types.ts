import type { useToastWithDeduplication } from "../../../../../hooks/useToastWithDeduplication";
import type { TenantUserView, TenantView } from "../../../../../types/tenant";
import type { TenantManagementUser } from "../shared";

export interface TenantModalBaseOptions {
  toast: ReturnType<typeof useToastWithDeduplication>;
  refreshLists: (tenantIdOverride?: string) => Promise<void>;
}

export interface TenantEmailRegistryState {
  knownTenantEmails: Set<string>;
  knownUserEmails: Set<string>;
  isLoadingKnownEmails: boolean;
  knownEmailRecheckKey: string;
  syncKnownEmailsFromLists: (tenantRows: TenantView[], userRows: TenantUserView[]) => void;
  refreshKnownAccountEmails: () => Promise<void>;
}

export interface UseTenantEmailRegistryOptions {
  user: TenantManagementUser | null;
  tenants: TenantView[];
  tenantUsers: TenantUserView[];
}
