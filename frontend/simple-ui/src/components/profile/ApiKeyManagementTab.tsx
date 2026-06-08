import React, { useEffect, useRef } from "react";
import { useAuth } from "../../hooks/useAuth";
import { useApiKeyManagementTab } from "./hooks/useApiKeyManagementTab";
import { useAdminTableSurface } from "../common/TableControls";
import ApiKeyDetailModal from "./api-key/ApiKeyDetailModal";
import ApiKeyManagementTable from "./api-key/ApiKeyManagementTable";
import ApiKeyRevokeDialog from "./api-key/ApiKeyRevokeDialog";
import ApiKeyUpdateModal from "./api-key/ApiKeyUpdateModal";

export interface ApiKeyManagementTabProps {
  /** When true, tab is visible; used to fetch data when user switches to this tab */
  isActive?: boolean;
  /** Parent can trigger refresh after keys are created on another tab */
  onRegisterRefresh?: (refresh: () => Promise<void>) => void;
}

export default function ApiKeyManagementTab({
  isActive = false,
  onRegisterRefresh,
}: ApiKeyManagementTabProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const { user } = useAuth();
  const { cardBg, borderColor: cardBorder } = useAdminTableSurface();
  const mgmt = useApiKeyManagementTab({ user: user ?? null });

  useEffect(() => {
    onRegisterRefresh?.(mgmt.handleFetchAllApiKeys);
  }, [onRegisterRefresh, mgmt.handleFetchAllApiKeys]);

  useEffect(() => {
    if (isActive) {
      void mgmt.handleFetchAllApiKeys({ silent: true });
    }
  }, [isActive, mgmt.handleFetchAllApiKeys]);

  return (
    <>
      <ApiKeyManagementTable
        apiKeys={mgmt.filteredApiKeys}
        unfilteredCount={mgmt.allApiKeys.length}
        isLoading={mgmt.isLoadingAllApiKeys}
        keyNameSearch={mgmt.keyNameSearch}
        onKeyNameSearchChange={mgmt.setKeyNameSearch}
        filterPermission={mgmt.filterPermission}
        onFilterPermissionChange={mgmt.setFilterPermission}
        filterActive={mgmt.filterActive}
        onFilterActiveChange={mgmt.setFilterActive}
        permissionFilterOptions={mgmt.permissionFilterOptions}
        onClearFilters={mgmt.handleResetFilters}
        onRefresh={() => void mgmt.handleFetchAllApiKeys()}
        onView={mgmt.handleOpenViewModal}
        onUpdate={mgmt.handleOpenUpdateModal}
        onRevoke={mgmt.handleOpenRevokeModal}
        formatPermission={mgmt.formatPermission}
        resolveKeyDisplayStatus={mgmt.resolveKeyDisplayStatus}
        getKeyInactiveReason={mgmt.getKeyInactiveReason}
        isKeyEffectivelyActive={mgmt.isKeyEffectivelyActive}
        isKeyRevocable={mgmt.isKeyRevocable}
        cardBg={cardBg}
        cardBorder={cardBorder}
      />

      <ApiKeyDetailModal
        isOpen={mgmt.isViewModalOpen}
        onClose={mgmt.handleCloseViewModal}
        apiKey={mgmt.selectedKeyForView}
        formatPermission={mgmt.formatPermission}
        formatKeyId={mgmt.formatKeyId}
        resolveKeyDisplayStatus={mgmt.resolveKeyDisplayStatus}
        getKeyInactiveReason={mgmt.getKeyInactiveReason}
      />

      <ApiKeyUpdateModal
        isOpen={mgmt.isUpdateModalOpen}
        onClose={mgmt.handleCloseUpdateModal}
        selectedKey={mgmt.selectedKeyForUpdate}
        formData={mgmt.updateFormData}
        onFormChange={mgmt.setUpdateFormData}
        permissions={mgmt.permissions}
        onSubmit={mgmt.handleUpdateApiKey}
        isUpdating={mgmt.isUpdating}
      />

      <ApiKeyRevokeDialog
        isOpen={mgmt.isRevokeModalOpen}
        onClose={mgmt.handleCloseRevokeModal}
        apiKey={mgmt.keyToRevoke}
        formatPermission={mgmt.formatPermission}
        onConfirm={mgmt.handleRevokeApiKey}
        isRevoking={mgmt.isRevoking}
        cancelRef={cancelRef}
      />
    </>
  );
}
