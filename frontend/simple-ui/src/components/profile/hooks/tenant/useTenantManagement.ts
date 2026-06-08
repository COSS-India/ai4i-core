import { useCallback, useRef } from "react";
import { useToastWithDeduplication } from "../../../../hooks/useToastWithDeduplication";
import { TENANT_ADMIN_UPDATABLE_STATUSES } from "../../../../config/constants";
import type { TenantView } from "../../../../types/tenant";
import { extractErrorInfo } from "../../../../utils/errorHandler";
import type { UseTenantManagementOptions } from "./shared";
import { resolveTenantManagementRoles } from "./shared";
import { useTenantList } from "./useTenantList";
import { useTenantModals, type UseTenantModalsReturn } from "./useTenantModals";
import { useTenantUsers, type UseTenantUsersReturn } from "./useTenantUsers";

export type { UseTenantManagementOptions } from "./shared";

export function useTenantManagement(options: UseTenantManagementOptions) {
  const { user } = options;
  const toast = useToastWithDeduplication();

  const modalsRef = useRef<UseTenantModalsReturn>(null!);
  const usersRef = useRef<UseTenantUsersReturn>(null!);
  const refreshListsRef = useRef<(tenantIdOverride?: string) => Promise<void>>(async () => {});

  const list = useTenantList({
    user,
    toast,
    onOpenTenantStatus: (t, newStatus) => modalsRef.current.openTenantStatusDialog(t, newStatus),
    onTenantsLoaded: (rows) => {
      modalsRef.current?.syncKnownEmailsFromLists(rows, usersRef.current?.tenantUsers ?? []);
    },
  });

  const users = useTenantUsers({
    user,
    toast,
    tenants: list.tenants,
    tenantDetailView: list.tenantDetailView,
    onOpenUserStatus: (u, newStatus) => modalsRef.current.openUserStatusDialog(u, newStatus),
    onUsersLoaded: (rows) => {
      modalsRef.current?.syncKnownEmailsFromLists(list.tenants, rows);
    },
    refreshLists: (tenantIdOverride) => refreshListsRef.current(tenantIdOverride),
  });

  usersRef.current = users;

  const { isAdmin } = resolveTenantManagementRoles(user);

  refreshListsRef.current = async (tenantIdOverride?: string) => {
    if (isAdmin) {
      await list.handleFetchTenants();
    }
    const tenantId =
      tenantIdOverride ?? list.tenantDetailView?.tenant_id ?? user?.tenant_id ?? null;
    if (tenantId) {
      await users.handleFetchTenantUsers(tenantId);
    }
  };

  const modals = useTenantModals({
    user,
    toast,
    tenants: list.tenants,
    tenantUsers: users.tenantUsers,
    tenantDetailView: list.tenantDetailView,
    activeUserListTenant: users.activeUserListTenant,
    refreshLists: (tenantIdOverride) => refreshListsRef.current(tenantIdOverride),
  });

  modalsRef.current = modals;

  const handleViewTenant = useCallback(
    async (t: TenantView) => {
      list.openTenantDetail(t);
      try {
        const rows = await users.loadTenantUsersForTenant(t.tenant_id);
        users.setTenantUsers(rows);
        modals.syncKnownEmailsFromLists(list.tenants, rows);
      } catch (err) {
        console.error("Failed to fetch tenant users:", err);
        const { title, message } = extractErrorInfo(err);
        toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
      }
    },
    [list, users, modals, toast],
  );

  const handleResetTenantFilters = useCallback(() => {
    list.resetTenantFilters();
    users.resetUserFilters();
  }, [list, users]);

  const handleResetUserFilters = users.resetUserFilters;

  return {
    tenants: list.tenants,
    tenantUsers: users.tenantUsers,
    filteredTenants: list.filteredTenants,
    filteredTenantUsers: users.filteredTenantUsers,
    isLoadingTenants: list.isLoadingTenants,
    isLoadingTenantUsers: users.isLoadingTenantUsers,
    tenantFilterStatus: list.tenantFilterStatus,
    setTenantFilterStatus: list.setTenantFilterStatus,
    tenantSearch: list.tenantSearch,
    setTenantSearch: list.setTenantSearch,
    userFilterStatus: users.userFilterStatus,
    setUserFilterStatus: users.setUserFilterStatus,
    userFilterRole: users.userFilterRole,
    setUserFilterRole: users.setUserFilterRole,
    userSearch: users.userSearch,
    setUserSearch: users.setUserSearch,
    handleResetTenantFilters,
    handleResetUserFilters,
    tenantUserRoleFilterOptions: users.tenantUserRoleFilterOptions,
    isDefaultTenantUsersView: users.isDefaultTenantUsersView,
    activeUserListTenant: users.activeUserListTenant,
    TENANT_ADMIN_UPDATABLE_STATUSES,
    isTenantModalOpen: modals.isTenantModalOpen,
    tenantForm: modals.tenantForm,
    setTenantForm: modals.setTenantForm,
    tenantFormErrors: modals.tenantFormErrors,
    setTenantFormErrors: modals.setTenantFormErrors,
    isSubmittingTenant: modals.isSubmittingTenant,
    openTenantModal: modals.openTenantModal,
    closeTenantModal: modals.closeTenantModal,
    handleRegisterTenant: modals.handleRegisterTenant,
    handleTenantOrganisationChange: modals.handleTenantOrganisationChange,
    handleTenantOrganisationBlur: modals.handleTenantOrganisationBlur,
    handleTenantContactNameChange: modals.handleTenantContactNameChange,
    handleTenantEmailChange: modals.handleTenantEmailChange,
    handleTenantPhoneChange: modals.handleTenantPhoneChange,
    tenantEmailStatus: modals.tenantEmailStatus,
    canSubmitTenantForm: modals.canSubmitTenantForm,
    isLoadingKnownEmails: modals.isLoadingKnownEmails,
    isUserModalOpen: modals.isUserModalOpen,
    userForm: modals.userForm,
    setUserForm: modals.setUserForm,
    userFormErrors: modals.userFormErrors,
    setUserFormErrors: modals.setUserFormErrors,
    isSubmittingUser: modals.isSubmittingUser,
    openUserModal: modals.openUserModal,
    closeUserModal: modals.closeUserModal,
    lockedUserFormTenantId: modals.lockedUserFormTenantId,
    getLockedUserFormTenantLabel: modals.getLockedUserFormTenantLabel,
    setUserFormTenantId: modals.setUserFormTenantId,
    handleRegisterUser: modals.handleRegisterUser,
    handleUserFullNameChange: modals.handleUserFullNameChange,
    handleUserEmailChange: modals.handleUserEmailChange,
    handleUserPhoneChange: modals.handleUserPhoneChange,
    userEmailStatus: modals.userEmailStatus,
    canSubmitUserForm: modals.canSubmitUserForm,
    openAddUserForTenant: modals.openAddUserForTenant,
    viewUserDetail: modals.viewUserDetail,
    isViewUserModalOpen: modals.isViewUserModalOpen,
    handleViewTenant,
    handleViewUser: modals.handleViewUser,
    closeViewUserModal: modals.closeViewUserModal,
    tenantDetailView: list.tenantDetailView,
    tenantDetailSubTab: list.tenantDetailSubTab,
    setTenantDetailSubTab: list.setTenantDetailSubTab,
    closeTenantDetailView: list.closeTenantDetailView,
    isEditTenantModalOpen: modals.isEditTenantModalOpen,
    editTenantRow: modals.editTenantRow,
    editTenantForm: modals.editTenantForm,
    setEditTenantForm: modals.setEditTenantForm,
    editTenantFormErrors: modals.editTenantFormErrors,
    isSubmittingEditTenant: modals.isSubmittingEditTenant,
    handleOpenEditTenant: modals.handleOpenEditTenant,
    handleSaveEditTenant: modals.handleSaveEditTenant,
    handleEditTenantOrganisationChange: modals.handleEditTenantOrganisationChange,
    handleEditTenantOrganisationBlur: modals.handleEditTenantOrganisationBlur,
    handleEditTenantContactNameChange: modals.handleEditTenantContactNameChange,
    handleEditTenantEmailChange: modals.handleEditTenantEmailChange,
    handleEditTenantPhoneChange: modals.handleEditTenantPhoneChange,
    editTenantEmailStatus: modals.editTenantEmailStatus,
    canSubmitEditTenantForm: modals.canSubmitEditTenantForm,
    closeEditTenantModal: modals.closeEditTenantModal,
    statusUpdateTarget: modals.statusUpdateTarget,
    statusUpdateNewStatus: modals.statusUpdateNewStatus,
    isStatusDialogOpen: modals.isStatusDialogOpen,
    isSubmittingStatus: modals.isSubmittingStatus,
    handleOpenTenantStatus: list.handleOpenTenantStatus,
    handleOpenUserStatus: users.handleOpenUserStatus,
    handleConfirmStatusUpdate: modals.handleConfirmStatusUpdate,
    closeStatusDialog: modals.closeStatusDialog,
    resendVerificationTenantId: list.resendVerificationTenantId,
    resendVerificationUserId: users.resendVerificationUserId,
    handleResendTenantVerificationEmail: list.handleResendTenantVerificationEmail,
    handleResendTenantUserVerification: users.handleResendTenantUserVerification,
    isEditUserModalOpen: modals.isEditUserModalOpen,
    editUserRow: modals.editUserRow,
    editUserForm: modals.editUserForm,
    setEditUserForm: modals.setEditUserForm,
    editUserFormErrors: modals.editUserFormErrors,
    setEditUserFormErrors: modals.setEditUserFormErrors,
    isSubmittingEditUser: modals.isSubmittingEditUser,
    handleOpenEditUser: modals.handleOpenEditUser,
    handleSaveEditUser: modals.handleSaveEditUser,
    handleEditUserUsernameChange: modals.handleEditUserUsernameChange,
    handleEditUserFullNameChange: modals.handleEditUserFullNameChange,
    handleEditUserPhoneChange: modals.handleEditUserPhoneChange,
    canSubmitEditUserForm: modals.canSubmitEditUserForm,
    closeEditUserModal: modals.closeEditUserModal,
    deleteUserTarget: users.deleteUserTarget,
    isDeleteUserDialogOpen: users.isDeleteUserDialogOpen,
    isDeletingUser: users.isDeletingUser,
    handleOpenDeleteUser: users.handleOpenDeleteUser,
    handleConfirmDeleteUser: users.handleConfirmDeleteUser,
    closeDeleteUserDialog: users.closeDeleteUserDialog,
    handleFetchTenants: list.handleFetchTenants,
    handleFetchTenantUsers: users.handleFetchTenantUsers,
  };
}
