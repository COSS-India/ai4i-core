import {
  FormControl,
  FormErrorMessage,
  FormLabel,
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
  type StatusReasonOption,
} from "../../services/configManagementService";
import { useTenantManagement } from "./hooks/useTenantManagement";

type TenantManagement = ReturnType<typeof useTenantManagement>;

type InstitutionConfirmDialogsProps = Readonly<{
  tm: TenantManagement;
}>;

const STATUS_REMARKS_MAX_LENGTH = 200;

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

type StatusReasonSelectProps = Readonly<{
  reasons: StatusReasonOption[];
  value: string;
  onChange: (code: string) => void;
  isLoading: boolean;
  isError: boolean;
  isDisabled: boolean;
}>;

function StatusReasonSelect({
  reasons,
  value,
  onChange,
  isLoading,
  isError,
  isDisabled,
}: StatusReasonSelectProps) {
  return (
    <FormControl isRequired isInvalid={isError}>
      <FormLabel>Reason</FormLabel>
      <Select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        isDisabled={isLoading || isDisabled}
      >
        {/* Prompt for the closed field only; not a choice in the open list. */}
        <option value="" disabled hidden>
          {isLoading ? "Loading reasons…" : "Select a reason"}
        </option>
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
  );
}

type StatusRemarksFieldProps = Readonly<{
  label: string;
  isRequired: boolean;
  placeholder?: string;
  rows: number;
  value: string;
  onChange: (value: string) => void;
  isDisabled: boolean;
}>;

function StatusRemarksField({
  label,
  isRequired,
  placeholder,
  rows,
  value,
  onChange,
  isDisabled,
}: StatusRemarksFieldProps) {
  return (
    <FormControl isRequired={isRequired}>
      <FormLabel>
        {label}
        {!isRequired && (
          <Text as="span" fontWeight="normal" color="gray.500">
            {" "}
            (optional)
          </Text>
        )}
      </FormLabel>
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value.slice(0, STATUS_REMARKS_MAX_LENGTH))}
        maxLength={STATUS_REMARKS_MAX_LENGTH}
        rows={rows}
        placeholder={placeholder}
        isDisabled={isDisabled}
      />
    </FormControl>
  );
}

/**
 * Institution status changes record a reason (Suspend / Deactivate) or a
 * description (Activate). Loads the reasons and works out what the dialog requires.
 */
function useTenantStatusForm(tm: TenantManagement, isOpen: boolean) {
  const target = tm.statusUpdateTarget;
  const newStatus = tm.statusUpdateNewStatus;
  const isTenantTarget = target?.type === "tenant";
  const reasonConfigType = isTenantTarget ? getStatusReasonConfigType(newStatus) : null;
  const reasonOptions = useQuery({
    queryKey: ["configs", reasonConfigType],
    queryFn: () => getStatusReasonOptions(reasonConfigType as StatusReasonConfigType),
    enabled: isOpen && reasonConfigType !== null,
  });
  const reasons = reasonOptions.data ?? [];
  const selectedReason = reasons.find((r) => r.code === tm.statusReason);
  const isActivation = isTenantTarget && isTenantStatus(newStatus, TENANT.STATUS.ACTIVE);
  // Every activation (from Suspended or Deactivated) needs a description.
  const isDescriptionRequired = isActivation;
  const areRemarksRequired = selectedReason?.remarksRequired ?? false;
  const hasRemarks = tm.statusRemarks.trim().length > 0;
  const isConfirmDisabled = reasonConfigType
    ? !selectedReason || (areRemarksRequired && !hasRemarks)
    : isDescriptionRequired && !hasRemarks;
  return {
    reasonConfigType,
    reasons,
    isLoadingReasons: reasonOptions.isLoading,
    isReasonsError: reasonOptions.isError,
    isActivation,
    isDescriptionRequired,
    areRemarksRequired,
    isConfirmDisabled,
  };
}

type TenantStatusFieldsProps = Readonly<{
  tm: TenantManagement;
  form: ReturnType<typeof useTenantStatusForm>;
}>;

function TenantStatusFields({ tm, form }: TenantStatusFieldsProps) {
  // Suspend / Deactivate ask for remarks only when the reason needs them (Other).
  const showRemarks = form.isActivation || form.areRemarksRequired;
  const isRemarksMandatory = form.isActivation
    ? form.isDescriptionRequired
    : form.areRemarksRequired;
  return (
    <>
      {form.reasonConfigType && (
        <StatusReasonSelect
          reasons={form.reasons}
          value={tm.statusReason}
          onChange={(code) => {
            tm.setStatusReason(code);
            // Remarks belong to the reason they were typed for.
            tm.setStatusRemarks("");
          }}
          isLoading={form.isLoadingReasons}
          isError={form.isReasonsError}
          isDisabled={tm.isSubmittingStatus}
        />
      )}
      {showRemarks && (
        <StatusRemarksField
          label={form.isActivation ? "Description" : "Remarks"}
          isRequired={isRemarksMandatory}
          placeholder={
            form.isActivation
              ? `Why is this ${INSTITUTION.toLowerCase()} being reactivated?`
              : undefined
          }
          rows={form.isActivation ? 4 : 3}
          value={tm.statusRemarks}
          onChange={tm.setStatusRemarks}
          isDisabled={tm.isSubmittingStatus}
        />
      )}
    </>
  );
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

  const tenantForm = useTenantStatusForm(tm, isOpen);
  const tenantAction = getTenantStatusAction(tm.statusUpdateNewStatus);
  const reasonFields = isTenantTarget ? <TenantStatusFields tm={tm} form={tenantForm} /> : null;

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
        isConfirmDisabled={isTenantTarget && tenantForm.isConfirmDisabled}
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
