import { useEffect, useMemo, useState } from "react";
import authService from "../../../../services/authService";
import * as tenantService from "../../../../services/tenantService";
import { extractErrorInfo } from "../../../../utils/errorHandler";
import { collectUserEmails } from "../../../../utils/tenantEmailValidation";
import { TENANT, resolveTenantUserDisplayStatus } from "../../../../config/constants";
import type { TenantUserStatus, TenantUserView, TenantView } from "../../../../types/tenant";
import type { DeleteUserTarget } from "../../types";
import type { useToastWithDeduplication } from "../../../../hooks/useToastWithDeduplication";
import {
  DEFAULT_TENANT_PLATFORM_ROLE_FILTER_LIST,
  isDefaultTenant,
} from "../../../../utils/defaultTenant";
import {
  normalizeTenantUserRoles,
  tenantUserHasRole,
  tenantUserMatchesSearch,
  TENANT_USER_ROLE_FILTER_LIST,
} from "../../../../utils/tenantUserRoles";
import { resolveTenantManagementRoles, type TenantManagementUser } from "./shared";

export interface UseTenantUsersOptions {
  user: TenantManagementUser | null;
  toast: ReturnType<typeof useToastWithDeduplication>;
  tenants: TenantView[];
  tenantDetailView: TenantView | null;
  onOpenUserStatus: (u: TenantUserView, newStatus: TenantUserStatus) => void;
  onUsersLoaded?: (users: TenantUserView[]) => void;
  refreshLists: (tenantIdOverride?: string) => Promise<void>;
}

export function useTenantUsers({
  user,
  toast,
  tenants,
  tenantDetailView,
  onOpenUserStatus,
  onUsersLoaded,
  refreshLists,
}: UseTenantUsersOptions) {
  const { isTenantScopedUser } = resolveTenantManagementRoles(user);

  const [tenantUsers, setTenantUsers] = useState<TenantUserView[]>([]);
  const [isLoadingTenantUsers, setIsLoadingTenantUsers] = useState(false);
  const [userFilterStatus, setUserFilterStatus] = useState<string>("all");
  const [userFilterRole, setUserFilterRole] = useState<string>("all");
  const [userSearch, setUserSearch] = useState("");
  const [resendVerificationUserId, setResendVerificationUserId] = useState<string | null>(null);
  const [deleteUserTarget, setDeleteUserTarget] = useState<DeleteUserTarget | null>(null);
  const [isDeleteUserDialogOpen, setIsDeleteUserDialogOpen] = useState(false);
  const [isDeletingUser, setIsDeletingUser] = useState(false);

  const activeUserListTenant = useMemo(() => {
    if (tenantDetailView) return tenantDetailView;
    if (isTenantScopedUser && user?.tenant_id) {
      return tenants.find((t) => t.tenant_id === user.tenant_id) ?? null;
    }
    return null;
  }, [tenantDetailView, isTenantScopedUser, user?.tenant_id, tenants]);

  const filteredTenantUsers = useMemo(
    () =>
      tenantUsers.filter((u) => {
        if (userFilterStatus !== "all") {
          const displayStatus = resolveTenantUserDisplayStatus(u, activeUserListTenant?.status);
          if (displayStatus !== userFilterStatus) return false;
        }
        if (userFilterRole !== "all" && !tenantUserHasRole(u, userFilterRole)) {
          return false;
        }
        if (!tenantUserMatchesSearch(u, userSearch)) {
          return false;
        }
        return true;
      }),
    [tenantUsers, userFilterStatus, userFilterRole, userSearch, activeUserListTenant?.status],
  );

  const isDefaultTenantUsersView = useMemo(
    () => activeUserListTenant != null && isDefaultTenant(activeUserListTenant),
    [activeUserListTenant],
  );

  const tenantUserRoleFilterOptions = useMemo(
    () =>
      isDefaultTenantUsersView
        ? DEFAULT_TENANT_PLATFORM_ROLE_FILTER_LIST
        : TENANT_USER_ROLE_FILTER_LIST,
    [isDefaultTenantUsersView],
  );

  useEffect(() => {
    setUserFilterRole("all");
  }, [activeUserListTenant?.tenant_id]);

  const loadTenantUsersForTenant = async (tenantId: string): Promise<TenantUserView[]> => {
    const res = await tenantService.listUsers(tenantId);
    return normalizeTenantUserRoles(res.users ?? []);
  };

  const handleFetchTenantUsers = async (tenantIdOverride?: string) => {
    const tenantId = tenantIdOverride ?? tenantDetailView?.tenant_id ?? user?.tenant_id ?? null;
    if (!tenantId) {
      toast({
        title: "Tenant context missing",
        description: "Unable to load users because no tenant ID is available.",
        status: "warning",
        isClosable: true,
        duration: 5000,
      });
      setTenantUsers([]);
      onUsersLoaded?.([]);
      return;
    }
    setIsLoadingTenantUsers(true);
    try {
      const users = await loadTenantUsersForTenant(tenantId);
      setTenantUsers(users);
      onUsersLoaded?.(users);
    } catch (err) {
      console.error("Failed to fetch tenant users:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 8000 });
      setTenantUsers([]);
      onUsersLoaded?.([]);
    } finally {
      setIsLoadingTenantUsers(false);
    }
  };

  const resetUserFilters = () => {
    setUserFilterStatus("all");
    setUserFilterRole("all");
    setUserSearch("");
  };

  const handleResendTenantUserVerification = async (u: TenantUserView) => {
    if (!u.email) return;
    try {
      setResendVerificationUserId(u.user_id);
      await authService.resendVerification({ email: u.email });
      toast({
        title: "Verification email sent",
        description: `A new verification link was sent to ${u.email}.`,
        status: "success",
        isClosable: true,
        duration: 5000,
      });
    } catch (err) {
      console.error("Failed to resend tenant user verification:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setResendVerificationUserId(null);
    }
  };

  const handleOpenUserStatus = (u: TenantUserView, newStatus: TenantUserStatus) => {
    if (newStatus !== TENANT.USER_STATUS.ACTIVE && newStatus !== TENANT.USER_STATUS.SUSPENDED) {
      return;
    }
    onOpenUserStatus(u, newStatus);
  };

  const handleOpenDeleteUser = (u: TenantUserView) => {
    setDeleteUserTarget({
      tenant_id: tenantDetailView?.tenant_id ?? user?.tenant_id ?? "",
      user_id: u.user_id,
      username: u.username ?? u.email,
    });
    setIsDeleteUserDialogOpen(true);
  };

  const handleConfirmDeleteUser = async () => {
    if (!deleteUserTarget) return;
    setIsDeletingUser(true);
    try {
      await tenantService.deleteUser({
        tenant_id: deleteUserTarget.tenant_id,
        user_id: deleteUserTarget.user_id,
      });
      toast({ title: "User deleted", status: "success", isClosable: true });
      setIsDeleteUserDialogOpen(false);
      setDeleteUserTarget(null);
      await refreshLists(deleteUserTarget.tenant_id);
    } catch (err) {
      console.error("Failed to delete user:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsDeletingUser(false);
    }
  };

  const closeDeleteUserDialog = () => {
    if (!isDeletingUser) {
      setIsDeleteUserDialogOpen(false);
      setDeleteUserTarget(null);
    }
  };

  return {
    tenantUsers,
    setTenantUsers,
    isLoadingTenantUsers,
    filteredTenantUsers,
    userFilterStatus,
    setUserFilterStatus,
    userFilterRole,
    setUserFilterRole,
    userSearch,
    setUserSearch,
    activeUserListTenant,
    tenantUserRoleFilterOptions,
    isDefaultTenantUsersView,
    handleFetchTenantUsers,
    loadTenantUsersForTenant,
    resetUserFilters,
    resendVerificationUserId,
    handleResendTenantUserVerification,
    handleOpenUserStatus,
    deleteUserTarget,
    isDeleteUserDialogOpen,
    isDeletingUser,
    handleOpenDeleteUser,
    handleConfirmDeleteUser,
    closeDeleteUserDialog,
    collectUserEmails: (rows: TenantUserView[]) => collectUserEmails(rows),
  };
}

export type UseTenantUsersReturn = ReturnType<typeof useTenantUsers>;
