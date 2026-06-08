import type { useToastWithDeduplication } from "../../../../hooks/useToastWithDeduplication";
import type { TenantUserView, TenantView } from "../../../../types/tenant";
import type { TenantManagementUser } from "./shared";
import { useAddUserModal } from "./modals/useAddUserModal";
import { useCreateTenantModal } from "./modals/useCreateTenantModal";
import { useEditTenantModal } from "./modals/useEditTenantModal";
import { useEditUserModal } from "./modals/useEditUserModal";
import { useTenantEmailRegistry } from "./modals/useTenantEmailRegistry";
import { useTenantStatusDialog } from "./modals/useTenantStatusDialog";
import { useViewUserModal } from "./modals/useViewUserModal";

export interface UseTenantModalsOptions {
  user: TenantManagementUser | null;
  toast: ReturnType<typeof useToastWithDeduplication>;
  tenants: TenantView[];
  tenantUsers: TenantUserView[];
  tenantDetailView: TenantView | null;
  activeUserListTenant: TenantView | null;
  refreshLists: (tenantIdOverride?: string) => Promise<void>;
}

export function useTenantModals(options: UseTenantModalsOptions) {
  const {
    user,
    toast,
    tenants,
    tenantUsers,
    tenantDetailView,
    activeUserListTenant,
    refreshLists,
  } = options;

  const emailRegistry = useTenantEmailRegistry({ user, tenants, tenantUsers });

  const createTenant = useCreateTenantModal({
    toast,
    tenants,
    refreshLists,
    emailRegistry,
  });

  const editTenant = useEditTenantModal({
    toast,
    tenants,
    refreshLists,
    emailRegistry,
  });

  const addUser = useAddUserModal({
    user,
    toast,
    tenants,
    tenantDetailView,
    refreshLists,
    emailRegistry,
  });

  const editUser = useEditUserModal({
    user,
    toast,
    tenantDetailView,
    refreshLists,
  });

  const viewUser = useViewUserModal();

  const statusDialog = useTenantStatusDialog({
    user,
    toast,
    tenantDetailView,
    activeUserListTenant,
    refreshLists,
  });

  return {
    syncKnownEmailsFromLists: emailRegistry.syncKnownEmailsFromLists,
    isLoadingKnownEmails: emailRegistry.isLoadingKnownEmails,
    ...createTenant,
    ...addUser,
    ...viewUser,
    ...editTenant,
    ...statusDialog,
    ...editUser,
  };
}

export type UseTenantModalsReturn = ReturnType<typeof useTenantModals>;
