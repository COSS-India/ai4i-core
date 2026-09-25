// View Service tab: read-only detail view with publish/unpublish actions
import {
  Badge,
  Box,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
  IconButton,
  SimpleGrid,
  Text,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import { ArrowBackIcon } from "@chakra-ui/icons";
import { MdOutlineCheckCircle, MdOutlineUnpublished } from "react-icons/md";
import React from "react";
import {
  resolveHasAuthToken,
  type Service,
} from "../../services/servicesManagementService";
import { resolveTaskType } from "../../utils/platformService";
import ServiceFormTab from "./ServiceFormTab";

interface ServiceDetailTabProps {
  cardBg: string;
  cardBorder: string;
  selectedService: Service;
  isRegistryReadOnly: boolean;
  getTaskColor: (taskType?: string) => string;
  isServiceModelDeprecated: (service: Service | null | undefined) => boolean;
  selectedServiceModelDeprecated: boolean | null;
  viewServiceUnitType: string;
  unpublishingServiceUuid: string | null;
  publishingServiceUuid: string | null;
  onRequestUnpublish: (service: Service) => void;
  onRequestPublish: (service: Service) => void;
  onBack: () => void;
}

const ServiceDetailTab: React.FC<ServiceDetailTabProps> = ({
  cardBg,
  cardBorder,
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
}) => {
  const taskType = resolveTaskType(selectedService);
  const modelId = selectedService.modelId || selectedService.model_id || "";
  const tierIds = selectedService.tierIds?.length
    ? selectedService.tierIds
    : (selectedService.tierNames ?? []);
  return (
    <Card
      bg={cardBg}
      borderColor={cardBorder}
      borderWidth="1px"
      boxShadow="none"
    >
      <CardHeader>
        <HStack spacing={2} minW={0}>
          <IconButton
            aria-label="Back"
            icon={<ArrowBackIcon />}
            size="sm"
            variant="ghost"
            onClick={onBack}
            flexShrink={0}
          />
          <Heading size="md" color="ink.800" userSelect="none" cursor="default" isTruncated>
            {selectedService.name ||
              selectedService.serviceId ||
              selectedService.service_id}
          </Heading>
        </HStack>
      </CardHeader>
      <CardBody>
        {/* View Mode - Display service details */}
        <VStack spacing={6} align="stretch">
          {isRegistryReadOnly && (
            <Badge
              colorScheme="gray"
              alignSelf="flex-start"
              fontSize="sm"
              px={2}
              py={1}
            >
              Read-only
            </Badge>
          )}
          <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
            <Box>
              <Text fontWeight="bold" color="ink.600" fontSize="sm" mb={1}>
                Status (Publish/Unpublish)
              </Text>
              <HStack spacing={2} align="center" flexWrap="wrap">
                <Badge
                  colorScheme={
                    selectedService.isPublished === true ? "green" : "gray"
                  }
                  fontSize="sm"
                  p={2}
                >
                  {selectedService.isPublished === true
                    ? "Published"
                    : "Unpublished"}
                </Badge>
                {!isRegistryReadOnly &&
                  (selectedService.isPublished === true ? (
                    <Tooltip label="Unpublish" placement="top" hasArrow>
                      <IconButton
                        aria-label="Unpublish"
                        icon={<MdOutlineUnpublished />}
                        size="sm"
                        colorScheme="red"
                        variant="outline"
                        onClick={() => onRequestUnpublish(selectedService)}
                        isLoading={
                          unpublishingServiceUuid === selectedService.serviceId
                        }
                        isDisabled={
                          unpublishingServiceUuid !== null ||
                          publishingServiceUuid !== null
                        }
                      />
                    </Tooltip>
                  ) : (
                    <Tooltip
                      label={
                        isServiceModelDeprecated(selectedService) ||
                        selectedServiceModelDeprecated === true
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
                          isLoading={
                            publishingServiceUuid === selectedService.serviceId
                          }
                          isDisabled={
                            unpublishingServiceUuid !== null ||
                            publishingServiceUuid !== null ||
                            isServiceModelDeprecated(selectedService) ||
                            selectedServiceModelDeprecated === true
                          }
                        />
                      </Box>
                    </Tooltip>
                  ))}
              </HStack>
            </Box>
          </SimpleGrid>

          <ServiceFormTab
            mode="view"
            embedded={false}
            hideActions
            cardBg={cardBg}
            cardBorder={cardBorder}
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
            onCancel={() => undefined}
          />

          <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
            <Box>
              <Text fontWeight="bold" color="ink.600" fontSize="sm" mb={1}>
                Published On
              </Text>
              <Text fontSize="md">
                {selectedService.publishedOn
                  ? new Date(
                      selectedService.publishedOn * 1000,
                    ).toLocaleString()
                  : "N/A"}
              </Text>
            </Box>
          </SimpleGrid>

          {selectedService.created_at && (
            <Box>
              <Text fontWeight="bold" color="ink.600" fontSize="sm" mb={1}>
                Created At
              </Text>
              <Text fontSize="md">
                {new Date(selectedService.created_at).toLocaleString()}
              </Text>
            </Box>
          )}

          {selectedService.updated_at && (
            <Box>
              <Text fontWeight="bold" color="ink.600" fontSize="sm" mb={1}>
                Updated At
              </Text>
              <Text fontSize="md">
                {new Date(selectedService.updated_at).toLocaleString()}
              </Text>
            </Box>
          )}
        </VStack>
      </CardBody>
    </Card>
  );
};

export default ServiceDetailTab;
