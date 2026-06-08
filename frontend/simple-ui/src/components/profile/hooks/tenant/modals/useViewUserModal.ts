import { useState } from "react";
import type { TenantUserView } from "../../../../../types/tenant";
import { normalizeTenantUserRow } from "../../../../../utils/tenantUserRoles";

export function useViewUserModal() {
  const [viewUserDetail, setViewUserDetail] = useState<TenantUserView | null>(null);
  const [isViewUserModalOpen, setIsViewUserModalOpen] = useState(false);

  const handleViewUser = (u: TenantUserView) => {
    setViewUserDetail(normalizeTenantUserRow(u));
    setIsViewUserModalOpen(true);
  };

  const closeViewUserModal = () => {
    setIsViewUserModalOpen(false);
    setViewUserDetail(null);
  };

  return {
    viewUserDetail,
    isViewUserModalOpen,
    handleViewUser,
    closeViewUserModal,
  };
}
