// View Service: same form sections as create/edit, read-only, plus lifecycle actions.
import {
  Badge,
  Box,
  HStack,
  IconButton,
  SimpleGrid,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import { MdOutlineCheckCircle, MdOutlineUnpublished } from "react-icons/md";
import React from "react";
import FormActions from "../common/FormActions";
import FormDrawer from "../common/FormDrawer";
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
import {
  resolveHasAuthToken,
  type Service,
} from "../../services/servicesManagementService";
import { resolveTaskType } from "../../utils/platformService";
import ServiceFormTab from "./ServiceFormTab";
import {
  formatServiceListDate,
  serviceCreatedAtMillis,
  servicePublishedOnMillis,
  serviceUpdatedAtMillis,
} from "./serviceListColumns";

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
  onClose: () => void;
}

function optionalNumberToInput(value: number | null | undefined): string {
  if (value == null) return "";
  return String(value);
}

function serviceDetailLifecycleActions(options: {
  selectedService: Service;
  isRegistryReadOnly: boolean;
  publishBlocked: boolean;
  unpublishingServiceUuid: string | null;
  publishingServiceUuid: string | null;
  onRequestUnpublish: (service: Service) => void;
  onRequestPublish: (service: Service) => void;
}): React.ReactNode {
  if (options.isRegistryReadOnly) return undefined;
  const busy =
    options.unpublishingServiceUuid !== null ||
    options.publishingServiceUuid !== null;
  if (options.selectedService.isPublished === true) {
    return (
      <Tooltip label="Unpublish" placement="top" hasArrow>
        <IconButton
          aria-label="Unpublish"
          icon={<MdOutlineUnpublished />}
          size="sm"
          colorScheme="red"
          variant="outline"
          onClick={() => options.onRequestUnpublish(options.selectedService)}
          isLoading={
            options.unpublishingServiceUuid ===
            options.selectedService.serviceId
          }
          isDisabled={busy}
        />
      </Tooltip>
    );
  }
  const publishLabel = options.publishBlocked
    ? "This service cannot be published because its associated model is deprecated. Restore the model to ACTIVE before publishing."
    : "Publish";
  return (
    <Tooltip label={publishLabel} hasArrow placement="top">
      <Box as="span" display="inline-block">
        <IconButton
          aria-label="Publish"
          icon={<MdOutlineCheckCircle />}
          size="sm"
          colorScheme="green"
          variant="outline"
          onClick={() => options.onRequestPublish(options.selectedService)}
          isLoading={
            options.publishingServiceUuid === options.selectedService.serviceId
          }
          isDisabled={busy || options.publishBlocked}
        />
      </Box>
    </Tooltip>
  );
}

const ServiceDetailTab: React.FC<Readonly<ServiceDetailTabProps>> = ({
  selectedService,
  isRegistryReadOnly,
  isServiceModelDeprecated,
  selectedServiceModelDeprecated,
  viewServiceUnitType,
  unpublishingServiceUuid,
  publishingServiceUuid,
  onRequestUnpublish,
  onRequestPublish,
  onClose,
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
    <FormDrawer
      isOpen
      size="wide"
      onClose={onClose}
      title={title}
      description="Service configuration."
      actions={serviceDetailLifecycleActions({
        selectedService,
        isRegistryReadOnly,
        publishBlocked,
        unpublishingServiceUuid,
        publishingServiceUuid,
        onRequestUnpublish,
        onRequestPublish,
      })}
      footer={<FormActions hideSubmit cancelLabel="Close" onCancel={onClose} pt={0} />}
    >
      <VStack align="stretch" spacing={4}>
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
      </VStack>

      <ServiceFormTab
        mode="view"
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
        pricePerUnit={optionalNumberToInput(selectedService.costPerUnit)}
        onPricePerUnitChange={() => undefined}
        cachedInputPricePerUnit={optionalNumberToInput(
          selectedService.cachedInputCostPerUnit,
        )}
        onCachedInputPricePerUnitChange={() => undefined}
        outputPricePerUnit={optionalNumberToInput(
          selectedService.outputCostPerUnit,
        )}
        onOutputPricePerUnitChange={() => undefined}
        unitSize={optionalNumberToInput(selectedService.unitSize)}
        onUnitSizeChange={() => undefined}
        currency="INR"
        onCurrencyChange={() => undefined}
        selectedTiers={tierIds}
        onToggleTier={() => undefined}
        availableTiers={[]}
        isCreateFormModelSelected={Boolean(modelId)}
        isLlmTaskType={taskType.trim().toLowerCase() === "llm"}
        authToken=""
        onAuthTokenChange={() => undefined}
        hasAuthToken={resolveHasAuthToken(selectedService)}
        onSubmit={(e) => e.preventDefault()}
      />

      <FormSection title="Record">
        {/* Same helpers as the list columns so the panel and table agree. */}
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
          <ReadOnlyField label="Published On">
            {formatServiceListDate(servicePublishedOnMillis(selectedService))}
          </ReadOnlyField>
          <ReadOnlyField label="Created At">
            {formatServiceListDate(serviceCreatedAtMillis(selectedService))}
          </ReadOnlyField>
          <ReadOnlyField label="Updated At">
            {formatServiceListDate(serviceUpdatedAtMillis(selectedService))}
          </ReadOnlyField>
        </SimpleGrid>
      </FormSection>
    </FormDrawer>
  );
};

export default ServiceDetailTab;
