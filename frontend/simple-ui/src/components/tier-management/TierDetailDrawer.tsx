import { Button, HStack, Text } from "@chakra-ui/react";
import FormActions from "../common/FormActions";
import FormDrawer from "../common/FormDrawer";
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
import { INSTITUTIONS, formatModelTaskTypeLabel } from "../../config/constants";
import type { Tier } from "../../services/tierManagementService";
import { AssignedTenantsSection, type AssignedTenant } from "./AssignedTenantsSection";
import { ServicesMappedSection, type MappedService } from "./ServicesMappedSection";
import { TierForm } from "./TierForm";

export function TierDetailDrawer({
  isViewOpen,
  isCreateOpen,
  onViewClose,
  viewTier,
  taskTypeNames,
  unitByTaskType,
  cancelingTaskType,
  handleCancelPendingQuota,
  servicesForViewTier,
  isServicesForViewTierLoading,
  assignedTenantsForViewTier,
  isAssignedTenantsLoading,
}: {
  isViewOpen: boolean;
  isCreateOpen: boolean;
  onViewClose: () => void;
  viewTier: Tier | null;
  taskTypeNames: string[];
  unitByTaskType: Record<string, string>;
  cancelingTaskType: string | null;
  handleCancelPendingQuota: (modelTaskType: string) => void;
  servicesForViewTier: MappedService[];
  isServicesForViewTierLoading: boolean;
  assignedTenantsForViewTier: AssignedTenant[];
  isAssignedTenantsLoading: boolean;
}) {
  const pendingQuotas =
    viewTier?.quotas?.filter((q) => q.pendingLimit != null) ?? [];

  return (
    <FormDrawer
      isOpen={Boolean(isViewOpen && viewTier) && !isCreateOpen}
      onClose={onViewClose}
      size="wide"
      title={viewTier?.name || "Tier"}
      description="Tier details."
      footer={<FormActions hideSubmit cancelLabel="Close" onCancel={onViewClose} pt={0} />}
    >
      {viewTier ? <TierForm
        mode="view"
        formData={{
          name: viewTier.name,
          description: viewTier.description ?? "",
          rateLimit: viewTier.rateLimit != null ? String(viewTier.rateLimit) : "",
          quotas: (viewTier.quotas ?? []).map((q) => ({
            modelTaskType: q.modelTaskType,
            unit: q.unit ?? "",
            limit: String(q.limit ?? ""),
          })),
        }}
        onChange={() => undefined}
        taskTypeNames={taskTypeNames}
        unitByTaskType={unitByTaskType}
      /> : null}
      <FormSection title="Upcoming changes">
        {pendingQuotas.length ? (
          pendingQuotas.map((q) => (
            <HStack key={q.modelTaskType} justify="space-between" align="center">
              <ReadOnlyField label={`${formatModelTaskTypeLabel(q.modelTaskType)} Quota`}>
                {q.pendingLimit?.toLocaleString()} {q.unit} · effective next billing cycle
              </ReadOnlyField>
              <Button
                variant="link"
                size="xs"
                colorScheme="red"
                flexShrink={0}
                isLoading={cancelingTaskType === q.modelTaskType}
                isDisabled={
                  cancelingTaskType !== null && cancelingTaskType !== q.modelTaskType
                }
                onClick={() => handleCancelPendingQuota(q.modelTaskType)}
              >
                Cancel
              </Button>
            </HStack>
          ))
        ) : (
          <Text fontSize="sm" color="ink.400">
            No upcoming changes.
          </Text>
        )}
      </FormSection>
      <FormSection title={`Services mapped · ${isServicesForViewTierLoading ? "…" : servicesForViewTier.length}`}>
        <ServicesMappedSection
          services={servicesForViewTier}
          isLoading={isServicesForViewTierLoading}
        />
      </FormSection>
      <FormSection title={`${INSTITUTIONS} assigned · ${isAssignedTenantsLoading ? "…" : assignedTenantsForViewTier.length}`}>
        <AssignedTenantsSection
          tenants={assignedTenantsForViewTier}
          isLoading={isAssignedTenantsLoading}
        />
      </FormSection>
    </FormDrawer>
  );
}
