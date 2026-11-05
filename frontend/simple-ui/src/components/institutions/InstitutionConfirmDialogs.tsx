import {
  FormControl,
  FormErrorMessage,
  FormHelperText,
  FormLabel,
  HStack,
  Select,
  Text,
  Textarea,
  VStack,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import React from "react";
import ConfirmDialog from "../common/ConfirmDialog";
import {
  INSTITUTION,
  TENANT,
  formatTenantStatusLabel,
  formatTenantUserStatusLabel,
  isTenantStatus,
} from "../../config/constants";
import {
  getStatusReasonOptions,
  type StatusReasonConfigType,
} from "../../services/configManagementService";
import { useTenantManagement } from "./hooks/useTenantManagement";

type InstitutionConfirmDialogsProps = Readonly<{
  tm: ReturnType<typeof useTenantManagement>;
}>;

const STATUS_REMARKS_MAX_LENGTH = 500;

/** Config holding the predefined reasons for a status change; null when none are asked for. */
function getStatusReasonConfigType(newStatus: string): StatusReasonConfigType | null {
  if (isTenantStatus(newStatus, TENANT.STATUS.SUSPENDED)) return "suspend-reasons";
  if (isTenantStatus(newStatus, TENANT.STATUS.DEACTIVATED)) return "deactivate-reasons";
  return null;
}

function getTenantStatusAction(newStatus: string): {
  verb: string;
  colorScheme: string;
} {
  if (isTenantStatus(newStatus, TENANT.STATUS.SUSPENDED)) {
    return { verb: "Suspend", colorScheme: "orange" };
  }
  if (isTenantStatus(newStatus, TENANT.STATUS.DEACTIVATED)) {
    return { verb: "Deactivate", colorScheme: "red" };
  }
  return { verb: "Activate", colorScheme: "blue" };
}

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

export default function InstitutionConfirmDialogs({ tm }: InstitutionConfirmDialogsProps) {
  const target = tm.statusUpdateTarget;
  const isOpen = tm.isStatusDialogOpen && Boolean(target);
  const isTenantTarget = target?.type === "tenant";
  const targetLabel = isTenantTarget ? INSTITUTION.toLowerCase() : "user";
  const statusLabel = formatStatusConfirmLabel(
    target?.type,
    tm.statusUpdateNewStatus,
  );
  const apiKeyNote = isTenantTarget
    ? getTenantStatusConfirmBody(target.currentStatus, tm.statusUpdateNewStatus)
    : null;

  // Institution status changes record a reason (Suspend / Deactivate) or a description (Activate).
  const reasonConfigType = isTenantTarget
    ? getStatusReasonConfigType(tm.statusUpdateNewStatus)
    : null;
  const reasonOptions = useQuery({
    queryKey: ["configs", reasonConfigType],
    queryFn: () => getStatusReasonOptions(reasonConfigType as StatusReasonConfigType),
    enabled: isOpen && reasonConfigType !== null,
  });
  const reasons = reasonOptions.data ?? [];
  const selectedReason = reasons.find((r) => r.code === tm.statusReason);
  const isActivation =
    isTenantTarget && isTenantStatus(tm.statusUpdateNewStatus, TENANT.STATUS.ACTIVE);
  const isDescriptionRequired =
    isActivation && isTenantStatus(target.currentStatus, TENANT.STATUS.DEACTIVATED);
  const areRemarksRequired = selectedReason?.remarksRequired ?? false;
  const hasRemarks = tm.statusRemarks.trim().length > 0;
  const isConfirmDisabled = reasonConfigType
    ? !selectedReason || (areRemarksRequired && !hasRemarks)
    : isDescriptionRequired && !hasRemarks;

  const tenantAction = getTenantStatusAction(tm.statusUpdateNewStatus);
  const remarksLabel = isActivation ? "Description" : "Remarks";
  const isRemarksMandatory = isActivation ? isDescriptionRequired : areRemarksRequired;
  let remarksHint: string | null = null;
  if (isDescriptionRequired) {
    remarksHint = "Required. Recorded with this status change.";
  } else if (reasonConfigType) {
    remarksHint = areRemarksRequired
      ? `Remarks are required when the reason is ${selectedReason?.label ?? "Other"}.`
      : "Required only when the reason is Other.";
  }

  const reasonFields = isTenantTarget ? (
    <>
      {reasonConfigType && (
        <FormControl isRequired isInvalid={reasonOptions.isError}>
          <FormLabel>Reason</FormLabel>
          <Select
            placeholder={reasonOptions.isLoading ? "Loading reasons…" : "Select a reason"}
            value={tm.statusReason}
            onChange={(e) => tm.setStatusReason(e.target.value)}
            isDisabled={reasonOptions.isLoading || tm.isSubmittingStatus}
          >
            {reasons.map((r) => (
              <option key={r.code} value={r.code}>
                {r.label}
              </option>
            ))}
          </Select>
          <FormErrorMessage>
            Couldn&apos;t load the reasons. Close the dialog and try again.
          </FormErrorMessage>
        </FormControl>
      )}
      <FormControl isRequired={isRemarksMandatory}>
        <FormLabel>
          {remarksLabel}
          {!isRemarksMandatory && (
            <Text as="span" fontWeight="normal" color="gray.500">
              {" "}
              (optional)
            </Text>
          )}
        </FormLabel>
        <Textarea
          value={tm.statusRemarks}
          onChange={(e) =>
            tm.setStatusRemarks(e.target.value.slice(0, STATUS_REMARKS_MAX_LENGTH))
          }
          maxLength={STATUS_REMARKS_MAX_LENGTH}
          rows={isActivation ? 4 : 3}
          placeholder={
            isDescriptionRequired
              ? `Why is this ${INSTITUTION.toLowerCase()} being reactivated?`
              : "Add context for this change"
          }
          isDisabled={tm.isSubmittingStatus}
        />
        <HStack justify={remarksHint ? "space-between" : "flex-end"} mt={2}>
          {remarksHint && <FormHelperText mt={0}>{remarksHint}</FormHelperText>}
          <FormHelperText mt={0}>
            {tm.statusRemarks.length}/{STATUS_REMARKS_MAX_LENGTH}
          </FormHelperText>
        </HStack>
      </FormControl>
    </>
  ) : null;

  const body =
    apiKeyNote || reasonFields ? (
      <VStack align="stretch" spacing={4}>
        <Text>Set {targetLabel} status to &quot;{statusLabel}&quot;?</Text>
        {apiKeyNote && <Text>{apiKeyNote}</Text>}
        {reasonFields}
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
        title={
          isTenantTarget
            ? `${tenantAction.verb} ${INSTITUTION.toLowerCase()}`
            : `Change ${targetLabel} status`
        }
        body={body}
        confirmLabel={isTenantTarget ? tenantAction.verb : "Update"}
        confirmColorScheme={isTenantTarget ? tenantAction.colorScheme : "blue"}
        isConfirmLoading={tm.isSubmittingStatus}
        isConfirmDisabled={isTenantTarget && isConfirmDisabled}
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
