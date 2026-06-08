import { useState } from "react";
import { forceFrontendSessionEnd } from "../../../../../hooks/useAuth";
import type { useToastWithDeduplication } from "../../../../../hooks/useToastWithDeduplication";
import * as tenantService from "../../../../../services/tenantService";
import { extractErrorInfo } from "../../../../../utils/errorHandler";
import { TENANT, resolveTenantUserDisplayStatus } from "../../../../../config/constants";
import type { TenantStatus, TenantUserStatus, TenantUserView, TenantView } from "../../../../../types/tenant";
import type { StatusUpdateTargetUnion } from "../../../types";
import {
  isTenantAdminRoleForSessionEnd,
  resolveTenantManagementRoles,
  type TenantManagementUser,
} from "../shared";
import type { TenantModalBaseOptions } from "./types";

export interface UseTenantStatusDialogOptions extends TenantModalBaseOptions {
  user: TenantManagementUser | null;
  tenantDetailView: TenantView | null;
  activeUserListTenant: TenantView | null;
}

export function useTenantStatusDialog({
  user,
  toast,
  tenantDetailView,
  activeUserListTenant,
  refreshLists,
}: UseTenantStatusDialogOptions) {
  const { isTenantAdmin, userIdStr } = resolveTenantManagementRoles(user);

  const [statusUpdateTarget, setStatusUpdateTarget] = useState<StatusUpdateTargetUnion | null>(null);
  const [statusUpdateNewStatus, setStatusUpdateNewStatus] = useState<TenantStatus | TenantUserStatus>(
    TENANT.STATUS.ACTIVE,
  );
  const [isStatusDialogOpen, setIsStatusDialogOpen] = useState(false);
  const [isSubmittingStatus, setIsSubmittingStatus] = useState(false);

  const openTenantStatusDialog = (t: TenantView, newStatus: TenantStatus) => {
    setStatusUpdateTarget({ type: "tenant", tenant_id: t.tenant_id, currentStatus: t.status });
    setStatusUpdateNewStatus(newStatus);
    setIsStatusDialogOpen(true);
  };

  const openUserStatusDialog = (u: TenantUserView, newStatus: TenantUserStatus) => {
    const currentStatus = resolveTenantUserDisplayStatus(u, activeUserListTenant?.status);
    setStatusUpdateTarget({
      type: "user",
      tenant_id: tenantDetailView?.tenant_id ?? user?.tenant_id ?? "",
      user_id: u.user_id,
      currentStatus,
      role: u.role ?? u.roles?.[0],
    });
    setStatusUpdateNewStatus(newStatus);
    setIsStatusDialogOpen(true);
  };

  const handleConfirmStatusUpdate = async () => {
    if (!statusUpdateTarget) return;
    setIsSubmittingStatus(true);
    try {
      if (statusUpdateTarget.type === "tenant") {
        await tenantService.updateTenantStatus({
          tenant_id: statusUpdateTarget.tenant_id,
          status: statusUpdateNewStatus as TenantStatus,
        });
        toast({ title: "Tenant status updated", status: "success", isClosable: true });
        await refreshLists(statusUpdateTarget.tenant_id);
      } else {
        const isActive = statusUpdateNewStatus === TENANT.USER_STATUS.ACTIVE;
        await tenantService.updateUserStatus({
          tenant_id: statusUpdateTarget.tenant_id,
          user_id: statusUpdateTarget.user_id,
          is_active: isActive,
          is_tenant_active: isActive,
        });
        toast({ title: "User status updated", status: "success", isClosable: true });

        const ended = !isActive;
        const isCurrentTenantAdmin =
          ended &&
          userIdStr != null &&
          statusUpdateTarget.user_id === userIdStr &&
          (isTenantAdminRoleForSessionEnd(statusUpdateTarget.role) || isTenantAdmin);
        if (isCurrentTenantAdmin) {
          toast({
            title: "Signed out",
            description:
              "Your tenant admin account is no longer active. Sign in again when it is reactivated.",
            status: "warning",
            isClosable: true,
            duration: 6000,
          });
          forceFrontendSessionEnd();
          return;
        }
        await refreshLists(statusUpdateTarget.tenant_id);
      }
      setIsStatusDialogOpen(false);
      setStatusUpdateTarget(null);
    } catch (err) {
      console.error("Failed to update status:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsSubmittingStatus(false);
    }
  };

  const closeStatusDialog = () => {
    if (!isSubmittingStatus) {
      setIsStatusDialogOpen(false);
      setStatusUpdateTarget(null);
    }
  };

  return {
    statusUpdateTarget,
    statusUpdateNewStatus,
    isStatusDialogOpen,
    isSubmittingStatus,
    openTenantStatusDialog,
    openUserStatusDialog,
    handleConfirmStatusUpdate,
    closeStatusDialog,
  };
}
