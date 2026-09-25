// View Service: same form sections as create/edit, read-only, plus lifecycle actions.
import {
  Badge,
  Box,
  HStack,
  IconButton,
  Tooltip,
} from "@chakra-ui/react";
import { MdOutlineCheckCircle, MdOutlineUnpublished } from "react-icons/md";
import React from "react";
import FormActions from "../common/FormActions";
import FormPage from "../common/FormPage";
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
import {
  resolveHasAuthToken,
  type Service,
} from "../../services/servicesManagementService";
import { resolveTaskType } from "../../utils/platformService";
import ServiceFormTab from "./ServiceFormTab";

interface ServiceDetailTabProps {
  selectedService: Service;
  isRegistryReadOnly: boolean;
  isServiceModelDeprecated: (service: Service | null | undefined) => boolean;
  selectedServiceModelDeprecated: boolean | null;
  viewServiceUnitType: string;
  unpublishingServiceUuid: string | null;
  publishingServiceUuid: string | null;
  onRequestUnpublish: (service: Service) => void;
  onRequestPublish: (service: Service) => void;
  onBack: () => void;
  onNavigateToList?: () => void;
}

const ServiceDetailTab: React.FC<ServiceDetailTabProps> = ({
  selectedService,
  isRegistryReadOnly,
  isServiceModelDeprecated,
  selectedServiceModelDeprecated,
  viewServiceUnitType,
  unpublishingServiceUuid,
  publishingServiceUuid,
  onRequestUnpublish,
  onRequestPublish,
  onBack,
  onNavigateToList,
}) => {
  const taskType = resolveTaskType(selectedService);
  const modelId = selectedService.modelId || selectedService.model_id || "";
  const tierIds = selectedService.tierIds?.length
    ? selectedService.tierIds
    : (selectedService.tierNames ?? []);
  const title =
    selectedService.name ||
    selectedService.serviceId ||
    selectedService.service_id ||
    "Service";
  const publishBlocked =
    isServiceModelDeprecated(selectedService) ||
    selectedServiceModelDeprecated === true;

  return (
    <FormPage
      title={title}
      description="Service configuration."
      parent={{
        label: "Services Management",
        href: "/services-management",
        onNavigate: onNavigateToList ?? onBack,
      }}
      actions={
        !isRegistryReadOnly ? (
          selectedService.isPublished === true ? (
            <Tooltip label="Unpublish" placement="top" hasArrow>
              <IconButton
                aria-label="Unpublish"
                icon={<MdOutlineUnpublished />}
                size="sm"
                colorScheme="red"
                variant="outline"
                onClick={() => onRequestUnpublish(selectedService)}
                isLoading={unpublishingServiceUuid === selectedService.serviceId}
                isDisabled={
                  unpublishingServiceUuid !== null || publishingServiceUuid !== null
                }
              />
            </Tooltip>
          ) : (
            <Tooltip
              label={
                publishBlocked
                  ? "This service cannot be published because its associated model is deprecated. Restore the model to ACTIVE before publishing."
                  : "Publish"
              }
              hasArrow
              placement="top"
            >
              <Box as="span" display="inline-block">
                <IconButton
                  aria-label="Publish"
                  icon={<MdOutlineCheckCircle />}
                  size="sm"
                  colorScheme="green"
                  variant="outline"
                  onClick={() => onRequestPublish(selectedService)}
                  isLoading={publishingServiceUuid === selectedService.serviceId}
                  isDisabled={
                    unpublishingServiceUuid !== null ||
                    publishingServiceUuid !== null ||
                    publishBlocked
                  }
                />
              </Box>
            </Tooltip>
          )
        ) : undefined
      }
      footer={<FormActions hideSubmit cancelLabel="Back" onCancel={onBack} pt={0} />}
    >
      <FormSection title="Availability">
        <ReadOnlyField label="Status">
          <HStack spacing={2}>
            {isRegistryReadOnly ? (
              <Badge colorScheme="gray" fontSize="xs" px={2} py={0.5}>
                Read-only
              </Badge>
            ) : null}
            <Badge
              colorScheme={selectedService.isPublished === true ? "green" : "gray"}
              fontSize="xs"
              px={2}
              py={0.5}
            >
              {selectedService.isPublished === true ? "Published" : "Unpublished"}
            </Badge>
          </HStack>
        </ReadOnlyField>
      </FormSection>

      <ServiceFormTab
        mode="view"
        hideActions
        editingService={selectedService}
        formData={{
          name: selectedService.name || "",
          serviceId: selectedService.serviceId || selectedService.service_id || "",
          serviceDescription:
            selectedService.serviceDescription || selectedService.description || "",
          hardwareDescription: selectedService.hardwareDescription || "",
          modelId,
          modelName: selectedService.model?.name || modelId,
          endpoint: selectedService.endpoint || selectedService.endpoint_url || "",
          task_type: taskType,
          modelSubmissionDate: selectedService.modelSubmissionDate,
        }}
        onInputChange={() => undefined}
        onTaskTypeChange={() => undefined}
        onModelNameChange={() => undefined}
        taskTypeNames={taskType ? [taskType] : []}
        isLoadingModels={false}
        filteredModelsForDropdown={[]}
        unitType={viewServiceUnitType}
        pricePerUnit={
          selectedService.costPerUnit != null ? String(selectedService.costPerUnit) : ""
        }
        onPricePerUnitChange={() => undefined}
        unitSize={selectedService.unitSize != null ? String(selectedService.unitSize) : ""}
        onUnitSizeChange={() => undefined}
        currency="INR"
        onCurrencyChange={() => undefined}
        selectedTiers={tierIds}
        onToggleTier={() => undefined}
        availableTiers={[]}
        isCreateFormModelSelected={Boolean(modelId)}
        canCreateService={false}
        isLlmTaskType={taskType.trim().toLowerCase() === "llm"}
        authToken=""
        onAuthTokenChange={() => undefined}
        hasAuthToken={resolveHasAuthToken(selectedService)}
        isSubmitting={false}
        onSubmit={(e) => e.preventDefault()}
        onCancel={onBack}
      />

      <FormSection title="Record">
        <ReadOnlyField label="Published On">
          {selectedService.publishedOn
            ? new Date(selectedService.publishedOn * 1000).toLocaleString()
            : "N/A"}
        </ReadOnlyField>
        {selectedService.created_at ? (
          <ReadOnlyField label="Created At">
            {new Date(selectedService.created_at).toLocaleString()}
          </ReadOnlyField>
        ) : null}
        {selectedService.updated_at ? (
          <ReadOnlyField label="Updated At">
            {new Date(selectedService.updated_at).toLocaleString()}
          </ReadOnlyField>
        ) : null}
      </FormSection>
    </FormPage>
  );
};

export default ServiceDetailTab;
