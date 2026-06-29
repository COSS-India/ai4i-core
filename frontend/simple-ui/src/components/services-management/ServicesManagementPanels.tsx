import {
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormLabel,
  HStack,
  Heading,
  IconButton,
  Input,
  Select,
  SimpleGrid,
  TabPanel,
  Text,
  Textarea,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import { FaUpload, FaDownload } from "react-icons/fa";
import React from "react";
import AdminDataTable, {
  TableSearchField,
  TableSelectField,
} from "../common/AdminDataTable";
import ConfirmDialog from "../common/ConfirmDialog";
import {
  MODEL_TASK_TYPE_LIST,
  formatModelTaskTypeLabel,
  PAGINATION,
  SERVICE_PUBLISH,
} from "../../constants";
import { EMPTY_CREATE_SERVICE_FORM } from "../../utils/servicesManagementPage";
import type { useServicesManagementPage } from "../../hooks/useServicesManagementPage";
import type { Service } from "../../services/servicesManagementService";

type PageState = ReturnType<typeof useServicesManagementPage>;

export function ServiceRegistryPanel(props: Readonly<PageState>) {
  const {
    cardBg,
    cardBorder,
    registryEpoch,
    registryTableItems,
    serviceColumns,
    filterStatus,
    filterTaskType,
    isLoading,
    services,
    hasActiveFilters,
    clearAllFilters,
    searchQuery,
    setSearchQuery,
    setFilterStatus,
    setFilterTaskType,
    handleViewService,
  } = props;

  return (
    <TabPanel px={0} pt={6}>
      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardHeader>
          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
            Service Registry
          </Heading>
        </CardHeader>
        <CardBody>
          <AdminDataTable
            key={`${filterStatus}-${filterTaskType}-${registryEpoch}`}
            items={registryTableItems}
            columns={serviceColumns}
            getRowKey={(service) => service.serviceId || service.service_id || ""}
            onRowClick={(service) =>
              handleViewService(service.serviceId || service.service_id || "")
            }
            paginate="client"
            pageSizeOptions={PAGINATION.TABLE_PAGE_SIZE_OPTIONS}
            isLoading={isLoading}
            loadingMessage="Loading services..."
            emptyMessage="No services in the registry yet."
            noResultsMessage="No results found. Try adjusting your search or filters."
            unfilteredCount={services.length}
            hasActiveFilters={hasActiveFilters}
            onClearFilters={clearAllFilters}
            filters={
              <VStack align="stretch" spacing={3} w="full">
                <HStack flexWrap="wrap" spacing={3} align="flex-end">
                  <TableSearchField
                    label="Search"
                    value={searchQuery}
                    onChange={setSearchQuery}
                    placeholder="Search by service name..."
                    formControlProps={{ w: { base: "full", md: "280px" } }}
                  />
                  <TableSelectField
                    label="Status"
                    value={filterStatus}
                    onChange={setFilterStatus}
                    formControlProps={{ w: { base: "full", sm: "140px" } }}
                  >
                    <option value="">All</option>
                    <option value={SERVICE_PUBLISH.FILTER.PUBLISHED}>
                      {SERVICE_PUBLISH.LABEL.PUBLISHED}
                    </option>
                    <option value={SERVICE_PUBLISH.FILTER.UNPUBLISHED}>
                      {SERVICE_PUBLISH.LABEL.UNPUBLISHED}
                    </option>
                  </TableSelectField>
                  <TableSelectField
                    label="Model Task Type"
                    value={filterTaskType}
                    onChange={setFilterTaskType}
                    formControlProps={{ w: { base: "full", sm: "160px" } }}
                  >
                    <option value="">All</option>
                    {MODEL_TASK_TYPE_LIST.map((t) => (
                      <option key={t} value={t}>
                        {formatModelTaskTypeLabel(t)}
                      </option>
                    ))}
                  </TableSelectField>
                </HStack>
                {hasActiveFilters && (
                  <HStack spacing={2} flexWrap="wrap">
                    {searchQuery.trim() && (
                      <Badge
                        colorScheme="blue"
                        fontSize="xs"
                        px={2}
                        py={1}
                        cursor="pointer"
                        onClick={() => setSearchQuery("")}
                        _hover={{ opacity: 0.8 }}
                      >
                        Search: &quot;{searchQuery.trim()}&quot; ×
                      </Badge>
                    )}
                    {filterStatus && (
                      <Badge
                        colorScheme="gray"
                        fontSize="xs"
                        px={2}
                        py={1}
                        cursor="pointer"
                        onClick={() => setFilterStatus("")}
                        _hover={{ opacity: 0.8 }}
                      >
                        Status:{" "}
                        {filterStatus === SERVICE_PUBLISH.FILTER.PUBLISHED
                          ? SERVICE_PUBLISH.LABEL.PUBLISHED
                          : SERVICE_PUBLISH.LABEL.UNPUBLISHED}{" "}
                        ×
                      </Badge>
                    )}
                    {filterTaskType && (
                      <Badge
                        colorScheme="gray"
                        fontSize="xs"
                        px={2}
                        py={1}
                        cursor="pointer"
                        onClick={() => setFilterTaskType("")}
                        _hover={{ opacity: 0.8 }}
                      >
                        Model Task Type: {formatModelTaskTypeLabel(filterTaskType)} ×
                      </Badge>
                    )}
                  </HStack>
                )}
              </VStack>
            }
          />
        </CardBody>
      </Card>
    </TabPanel>
  );
}

export function CreateServicePanel(props: Readonly<PageState>) {
  const {
    cardBg,
    cardBorder,
    formData,
    setFormData,
    handleSubmit,
    handleInputChange,
    handleModelNameChange,
    isLoadingModels,
    modelsForDropdown,
    isCreateFormModelSelected,
    canCreateService,
    isSubmitting,
    setPreselectedModelFromQuery,
  } = props;

  return (
    <TabPanel px={0} pt={6}>
      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardHeader>
          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
            Create New Service
          </Heading>
        </CardHeader>
        <CardBody>
          <form onSubmit={handleSubmit}>
            <VStack spacing={6} align="stretch">
              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Service Name </FormLabel>
                <Input
                  value={formData.name || ""}
                  onChange={(e) => handleInputChange("name", e.target.value)}
                  placeholder="Enter service name e.g. asr-conformer-gpu"
                  bg="white"
                />
                <Text fontSize="xs" color="gray.500" mt={1}>
                  Enter service name e.g. asr-conformer-gpu. Service ID will be auto-generated based
                  on this.
                </Text>
              </FormControl>

              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Service Description </FormLabel>
                <Textarea
                  value={formData.serviceDescription || ""}
                  onChange={(e) => handleInputChange("serviceDescription", e.target.value)}
                  placeholder="Provide a brief description of what this service does"
                  bg="white"
                  rows={4}
                />
              </FormControl>

              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Endpoint </FormLabel>
                <Input
                  value={formData.endpoint || ""}
                  onChange={(e) => handleInputChange("endpoint", e.target.value)}
                  placeholder="Enter endpoint URL, e.g. http://localhost:8088"
                  bg="white"
                />
                <Text fontSize="xs" color="gray.500" mt={1}>
                  Enter the full HTTP endpoint where this service is hosted.
                </Text>
              </FormControl>

              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Model Name </FormLabel>
                <Select
                  value={formData.modelId || ""}
                  onChange={(e) => handleModelNameChange(e.target.value)}
                  placeholder={
                    isLoadingModels
                      ? "Loading models..."
                      : "Select the model to be associated with this service"
                  }
                  bg="white"
                  isDisabled={isLoadingModels}
                >
                  {modelsForDropdown.map((model) => (
                    <option
                      key={model.modelId || model.model_id}
                      value={model.modelId || model.model_id}
                    >
                      {model.name || model.modelId || model.model_id}
                    </option>
                  ))}
                </Select>
                <Text fontSize="xs" color="gray.500" mt={1}>
                  Select the model to be associated with this service.
                </Text>
              </FormControl>

              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold">Model ID</FormLabel>
                  <Input
                    value={formData.modelId || ""}
                    bg={isCreateFormModelSelected ? "gray.50" : "white"}
                    isReadOnly
                    placeholder="Select a model above"
                  />
                </FormControl>

                <FormControl isRequired>
                  <FormLabel fontWeight="semibold">Model Task Type</FormLabel>
                  <Input
                    value={formData.task_type || ""}
                    placeholder="Select a model above"
                    bg={isCreateFormModelSelected ? "gray.50" : "white"}
                    isReadOnly
                  />
                </FormControl>
              </SimpleGrid>

              <FormControl>
                <FormLabel fontWeight="semibold">Model Submission Date </FormLabel>
                <Input
                  type="date"
                  value={(formData.modelSubmissionDate as string) || ""}
                  placeholder="Select a model above"
                  bg={isCreateFormModelSelected ? "gray.50" : "white"}
                  isReadOnly
                />
              </FormControl>

              <HStack justify="flex-end" spacing={4} pt={4}>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setFormData({ ...EMPTY_CREATE_SERVICE_FORM });
                    setPreselectedModelFromQuery(null);
                  }}
                >
                  Reset
                </Button>
                <Button
                  type="submit"
                  colorScheme="blue"
                  isLoading={isSubmitting}
                  loadingText="Creating..."
                  isDisabled={!canCreateService || isSubmitting}
                >
                  Create Service
                </Button>
              </HStack>
            </VStack>
          </form>
        </CardBody>
      </Card>
    </TabPanel>
  );
}

function getPublishTooltipLabel(
  service: Service,
  selectedServiceModelDeprecated: boolean | null,
  isServiceModelDeprecated: (service: Service | null | undefined) => boolean,
): string {
  if (isServiceModelDeprecated(service) || selectedServiceModelDeprecated === true) {
    return "This service cannot be published because its associated model is deprecated. Restore the model to ACTIVE before publishing.";
  }
  return "Publish";
}

export function ViewServicePanel(props: Readonly<PageState>) {
  const {
    cardBg,
    cardBorder,
    isRegistryReadOnly,
    isEditingService,
    selectedService,
    selectedServiceModelDeprecated,
    isServiceModelDeprecated,
    unpublishingServiceUuid,
    publishingServiceUuid,
    setConfirmUnpublishService,
    onUnpublishConfirmOpen,
    setConfirmPublishService,
    onPublishConfirmOpen,
    getServiceTaskColor,
  } = props;

  if (!selectedService) return null;

  const taskType =
    selectedService?.model?.task?.type ||
    selectedService?.task?.type ||
    selectedService.task_type;

  return (
    <TabPanel px={0} pt={6}>
      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardHeader>
          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
            {selectedService.name || selectedService.serviceId || selectedService.service_id}
          </Heading>
        </CardHeader>
        <CardBody>
          {!isEditingService && (
            <VStack spacing={6} align="stretch">
              {isRegistryReadOnly && (
                <Badge colorScheme="gray" alignSelf="flex-start" fontSize="sm" px={2} py={1}>
                  Read-only
                </Badge>
              )}
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <Box>
                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                    Service ID
                  </Text>
                  <Text fontSize="md">
                    {selectedService.serviceId || selectedService.service_id || "N/A"}
                  </Text>
                </Box>
                <Box>
                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                    Name
                  </Text>
                  <Text fontSize="md">{selectedService.name || "N/A"}</Text>
                </Box>
              </SimpleGrid>

              <Box>
                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                  Description
                </Text>
                <Text fontSize="md">
                  {selectedService.serviceDescription || selectedService.description || "N/A"}
                </Text>
              </Box>

              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <Box>
                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                    Model Task Type
                  </Text>
                  <Badge colorScheme={getServiceTaskColor(taskType)} fontSize="sm" p={2}>
                    {taskType?.toUpperCase() || "N/A"}
                  </Badge>
                </Box>
                <Box>
                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                    Status (Publish/Unpublish)
                  </Text>
                  <HStack spacing={2} align="center" flexWrap="wrap">
                    <Badge
                      colorScheme={selectedService.isPublished === true ? "green" : "gray"}
                      fontSize="sm"
                      p={2}
                    >
                      {selectedService.isPublished === true ? "Published" : "Unpublished"}
                    </Badge>
                    {!isRegistryReadOnly &&
                      (selectedService.isPublished === true ? (
                        <Tooltip label="Unpublish" placement="top" hasArrow>
                          <IconButton
                            aria-label="Unpublish"
                            icon={<FaDownload />}
                            size="sm"
                            colorScheme="red"
                            variant="outline"
                            onClick={() => {
                              setConfirmUnpublishService(selectedService);
                              onUnpublishConfirmOpen();
                            }}
                            isLoading={unpublishingServiceUuid === selectedService.serviceId}
                            isDisabled={
                              unpublishingServiceUuid !== null || publishingServiceUuid !== null
                            }
                          />
                        </Tooltip>
                      ) : (
                        <Tooltip
                          label={getPublishTooltipLabel(
                            selectedService,
                            selectedServiceModelDeprecated,
                            isServiceModelDeprecated,
                          )}
                          hasArrow
                          placement="top"
                        >
                          <Box as="span" display="inline-block">
                            <IconButton
                              aria-label="Publish"
                              icon={<FaUpload />}
                              size="sm"
                              colorScheme="green"
                              variant="outline"
                              onClick={() => {
                                setConfirmPublishService(selectedService);
                                onPublishConfirmOpen();
                              }}
                              isLoading={publishingServiceUuid === selectedService.serviceId}
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

              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <Box>
                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                    Model ID
                  </Text>
                  <Text fontSize="md">
                    {selectedService.modelId || selectedService.model_id || "N/A"}
                  </Text>
                </Box>
                <Box>
                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                    Endpoint
                  </Text>
                  <Text fontSize="md" wordBreak="break-all">
                    {selectedService.endpoint || selectedService.endpoint_url || "N/A"}
                  </Text>
                </Box>
              </SimpleGrid>

              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <Box>
                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                    Hardware Description
                  </Text>
                  <Text fontSize="md">{selectedService.hardwareDescription || "N/A"}</Text>
                </Box>
                <Box>
                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                    Published On
                  </Text>
                  <Text fontSize="md">
                    {selectedService.publishedOn
                      ? new Date(selectedService.publishedOn * 1000).toLocaleString()
                      : "N/A"}
                  </Text>
                </Box>
              </SimpleGrid>

              {selectedService.created_at && (
                <Box>
                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                    Created At
                  </Text>
                  <Text fontSize="md">
                    {new Date(selectedService.created_at).toLocaleString()}
                  </Text>
                </Box>
              )}

              {selectedService.updated_at && (
                <Box>
                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                    Updated At
                  </Text>
                  <Text fontSize="md">
                    {new Date(selectedService.updated_at).toLocaleString()}
                  </Text>
                </Box>
              )}
            </VStack>
          )}
        </CardBody>
      </Card>
    </TabPanel>
  );
}

export function ServicesManagementConfirmDialogs(props: Readonly<PageState>) {
  const {
    isOpen,
    onClose,
    handleDeleteConfirm,
    serviceToDelete,
    deletingServiceUuid,
    cancelRef,
    isPublishConfirmOpen,
    onPublishConfirmClose,
    handlePublishConfirm,
    confirmPublishService,
    cancelPublishRef,
    publishingServiceUuid,
    isUnpublishConfirmOpen,
    onUnpublishConfirmClose,
    handleUnpublishConfirm,
    confirmUnpublishService,
    cancelUnpublishRef,
    unpublishingServiceUuid,
    setConfirmPublishService,
    setConfirmUnpublishService,
  } = props;

  return (
    <>
      <ConfirmDialog
        isOpen={isOpen}
        onClose={onClose}
        onConfirm={handleDeleteConfirm}
        title="Delete service"
        body={
          <>
            Are you sure you want to delete the service{" "}
            <strong>{serviceToDelete?.name || serviceToDelete?.service_id}</strong>? This action
            cannot be undone.
          </>
        }
        confirmColorScheme="red"
        isConfirmLoading={deletingServiceUuid === serviceToDelete?.serviceId}
        confirmLoadingText="Deleting..."
        leastDestructiveRef={cancelRef}
      />

      <ConfirmDialog
        isOpen={isPublishConfirmOpen}
        onClose={() => {
          onPublishConfirmClose();
          setConfirmPublishService(null);
        }}
        onConfirm={handlePublishConfirm}
        title="Publish service"
        body={
          <>
            Are you sure you want to publish{" "}
            <strong>{confirmPublishService?.name || confirmPublishService?.serviceId}</strong>? The
            service will be available for use.
          </>
        }
        confirmColorScheme="green"
        isConfirmLoading={publishingServiceUuid === confirmPublishService?.serviceId}
        confirmLoadingText="Publishing..."
        leastDestructiveRef={cancelPublishRef}
      />

      <ConfirmDialog
        isOpen={isUnpublishConfirmOpen}
        onClose={() => {
          onUnpublishConfirmClose();
          setConfirmUnpublishService(null);
        }}
        onConfirm={handleUnpublishConfirm}
        title="Unpublish service"
        body={
          <>
            Are you sure you want to unpublish{" "}
            <strong>{confirmUnpublishService?.name || confirmUnpublishService?.serviceId}</strong>?
            The service will no longer be available for use.
          </>
        }
        confirmColorScheme="red"
        isConfirmLoading={unpublishingServiceUuid === confirmUnpublishService?.serviceId}
        confirmLoadingText="Unpublishing..."
        leastDestructiveRef={cancelUnpublishRef}
      />
    </>
  );
}
