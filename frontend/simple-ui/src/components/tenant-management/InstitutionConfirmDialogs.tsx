import { Text, VStack } from "@chakra-ui/react";
import React from "react";
import ConfirmDialog from "../common/ConfirmDialog";
import {
  INSTITUTION,
  TENANT,
  formatTenantStatusLabel,
  formatTenantUserStatusLabel,
  isTenantStatus,
} from "../../config/constants";
import { useTenantManagement } from "../profile/hooks/useTenantManagement";

type InstitutionConfirmDialogsProps = {
  tm: ReturnType<typeof useTenantManagement>;
};

export default function InstitutionConfirmDialogs({ tm }: InstitutionConfirmDialogsProps) {
  function formatStatusConfirmLabel(
    targetType: "tenant" | "user" | undefined,
    status: string,
  ): string {
    if (targetType === "user") {
      return formatTenantUserStatusLabel(status);
    }
    return formatTenantStatusLabel(status);
  }

  function getTenantStatusConfirmBody(
    currentStatus: string,
    newStatus: string,
  ): string | null {
    if (isTenantStatus(newStatus, TENANT.STATUS.SUSPENDED)) {
      return `API keys become Inactive. Reactivating the ${INSTITUTION.toLowerCase()} restores the same keys to Active.`;
    }
    if (isTenantStatus(newStatus, TENANT.STATUS.DEACTIVATED)) {
      return "API keys are Revoked. After reactivation, an admin must create a new key.";
    }
    if (
      isTenantStatus(newStatus, TENANT.STATUS.ACTIVE) &&
      isTenantStatus(currentStatus, TENANT.STATUS.SUSPENDED)
    ) {
      return "Inactive API keys will automatically resume as Active.";
    }
    if (
      isTenantStatus(newStatus, TENANT.STATUS.ACTIVE) &&
      isTenantStatus(currentStatus, TENANT.STATUS.DEACTIVATED)
    ) {
      return "Previously revoked API keys are not restored. Create a new key if needed.";
    }
    return null;
  }

  const target = tm.statusUpdateTarget;
  const isOpen = tm.isStatusDialogOpen && Boolean(target);
  const targetLabel = target?.type === "tenant" ? INSTITUTION.toLowerCase() : "user";
  const statusLabel = formatStatusConfirmLabel(
    target?.type,
    tm.statusUpdateNewStatus,
  );
  const apiKeyNote =
    target?.type === "tenant"
      ? getTenantStatusConfirmBody(
          target.currentStatus,
          tm.statusUpdateNewStatus,
        )
      : null;
  const body = apiKeyNote ? (
    <VStack align="stretch" spacing={2}>
      <Text>Set {targetLabel} status to &quot;{statusLabel}&quot;?</Text>
      <Text>{apiKeyNote}</Text>
    </VStack>
  ) : (
    `Set ${targetLabel} status to "${statusLabel}"?`
  );

  const deleteTarget = tm.deleteUserTarget;

  return (
    <>
      <ConfirmDialog
        isOpen={isOpen}
        onClose={tm.closeStatusDialog}
        onConfirm={tm.handleConfirmStatusUpdate}
        title={`Change ${targetLabel} status`}
        body={body}
        confirmLabel="Update"
        confirmColorScheme="blue"
        isConfirmLoading={tm.isSubmittingStatus}
      />
      <ConfirmDialog
        isOpen={tm.isDeleteUserDialogOpen}
        onClose={tm.closeDeleteUserDialog}
        onConfirm={tm.handleConfirmDeleteUser}
        title="Delete user"
        body={`Soft-delete user ${deleteTarget?.username ?? ""}?`}
        confirmLabel="Delete"
        confirmColorScheme="red"
        isConfirmLoading={tm.isDeletingUser}
      />
    </>
  );
}
