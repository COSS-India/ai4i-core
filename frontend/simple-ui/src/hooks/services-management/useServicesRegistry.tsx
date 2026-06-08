import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useDisclosure, Box, Badge, Text, HStack, IconButton, Tooltip } from "@chakra-ui/react";
import { ViewIcon, DeleteIcon } from "@chakra-ui/icons";
import { FaUpload, FaDownload } from "react-icons/fa";
import {
  fetchAllServicesMatchingFilters,
  updateService,
  deleteService,
  type Service,
} from "../../services/servicesManagementService";
import { getModelById } from "../../services/modelManagementService";
import { extractErrorInfo } from "../../utils/errorHandler";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import type { AdminTableColumn } from "../../components/common/AdminDataTable";
import {
  getTaskColor,
  invalidateServiceRegistryQueries,
  isServiceModelDeprecated,
} from "../../components/services-management/utils";
import type {
  FetchServicesRef,
  HandleViewServiceRef,
  RegistryPageContext,
  SelectedServiceSync,
} from "./shared";

type UseServicesRegistryParams = RegistryPageContext & {
  fetchServicesRef: FetchServicesRef;
  handleViewServiceRef: HandleViewServiceRef;
  selectedServiceSync: SelectedServiceSync;
};

export function useServicesRegistry({
  queryClient,
  isRegistryReadOnly,
  checkSessionExpiry,
  fetchServicesRef,
  handleViewServiceRef,
  selectedServiceSync,
}: UseServicesRegistryParams) {
  const toast = useToastWithDeduplication();
  const {
    selectedService,
    setSelectedService,
    setIsViewingService,
    setSelectedServiceModelDeprecated,
    setActiveTab,
  } = selectedServiceSync;

  const [services, setServices] = useState<Service[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [deletingServiceUuid, setDeletingServiceUuid] = useState<string | null>(null);
  const [publishingServiceUuid, setPublishingServiceUuid] = useState<string | null>(null);
  const [unpublishingServiceUuid, setUnpublishingServiceUuid] = useState<string | null>(null);
  const [registryEpoch, setRegistryEpoch] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [filterTaskType, setFilterTaskType] = useState<string>("");
  const [sortBy, setSortBy] = useState<"time" | "name">("time");
  const [nameSortDirection, setNameSortDirection] = useState<"asc" | "desc">("asc");
  const [confirmPublishService, setConfirmPublishService] = useState<Service | null>(null);
  const [confirmUnpublishService, setConfirmUnpublishService] = useState<Service | null>(null);
  const {
    isOpen: isPublishConfirmOpen,
    onOpen: onPublishConfirmOpen,
    onClose: onPublishConfirmClose,
  } = useDisclosure();
  const {
    isOpen: isUnpublishConfirmOpen,
    onOpen: onUnpublishConfirmOpen,
    onClose: onUnpublishConfirmClose,
  } = useDisclosure();
  const cancelPublishRef = useRef<HTMLButtonElement>(null);
  const cancelUnpublishRef = useRef<HTMLButtonElement>(null);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [serviceToDelete, setServiceToDelete] = useState<Service | null>(null);

  const registryTableItems = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = q
      ? services.filter((s) => (s.name ?? "").toLowerCase().includes(q))
      : services;
    if (sortBy === "time") return filtered;
    return [...filtered].sort((a, b) => {
      const nameCmp = (a.name ?? "").localeCompare(b.name ?? "", undefined, { sensitivity: "base" });
      if (nameCmp !== 0) return nameSortDirection === "asc" ? nameCmp : -nameCmp;
      return 0;
    });
  }, [services, searchQuery, sortBy, nameSortDirection]);

  const hasActiveFilters = filterStatus !== "" || filterTaskType !== "" || searchQuery.trim() !== "";
  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterStatus("");
    setFilterTaskType("");
  };

  const fetchServices = useCallback(async () => {
    setIsLoading(true);
    try {
      const isPublishedFilter =
        filterStatus === "published" ? true :
        filterStatus === "unpublished" ? false :
        undefined;

      const result = await fetchAllServicesMatchingFilters({
        taskType: filterTaskType || undefined,
        isPublished: isPublishedFilter,
      });
      setServices(result.items);
    } catch (error: unknown) {
      console.error("Failed to fetch services:", error);
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      setServices([]);
    } finally {
      setIsLoading(false);
    }
  }, [filterTaskType, filterStatus, toast]);

  useEffect(() => {
    fetchServicesRef.current = fetchServices;
  }, [fetchServices, fetchServicesRef]);

  useEffect(() => {
    fetchServices();
  }, [fetchServices]);

  const handlePublishService = async (service: Service) => {
    try {
      const modelId = service.modelId || service.model_id;
      if (modelId) {
        const modelDetails = await getModelById(modelId);
        const isDeprecated =
          modelDetails?.versionStatus &&
          typeof modelDetails.versionStatus === "string" &&
          modelDetails.versionStatus.toLowerCase() === "deprecated";
        if (isDeprecated) {
          toast({
            title: "Publish blocked",
            description:
              "This service cannot be published because its associated model version is deprecated. Please restore the model to ACTIVE before publishing the service.",
            status: "error",
            duration: 6000,
            isClosable: true,
          });
          return;
        }
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn("Failed to verify model status before publishing service:", e);
    }

    if (!service.serviceId) {
      toast({
        title: "Publish Failed",
        description: "Service ID is required",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      return;
    }

    setPublishingServiceUuid(service.serviceId);

    try {
      const updatedService = await updateService({
        serviceId: service.serviceId,
        isPublished: true,
      });

      toast({
        title: "Service published",
        description: `${service.name || service.serviceId} has been published successfully.`,
        status: "success",
        duration: 5000,
        isClosable: true,
      });

      invalidateServiceRegistryQueries(queryClient);

      await fetchServices();

      if (selectedService?.serviceId === service.serviceId) {
        setSelectedService(updatedService);
      }
    } catch (error: unknown) {
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setPublishingServiceUuid(null);
    }
  };

  const handleUnpublishService = async (service: Service) => {
    if (!service.serviceId) {
      toast({
        title: "Unpublish Failed",
        description: "Service ID is required",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      return;
    }

    setUnpublishingServiceUuid(service.serviceId);

    try {
      const updatedService = await updateService({
        serviceId: service.serviceId,
        isPublished: false,
      });

      toast({
        title: "Service unpublished",
        description: `${service.name || service.serviceId} has been unpublished successfully.`,
        status: "success",
        duration: 5000,
        isClosable: true,
      });

      invalidateServiceRegistryQueries(queryClient);

      await fetchServices();

      if (selectedService?.serviceId === service.serviceId) {
        setSelectedService(updatedService);
      }
    } catch (error: unknown) {
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setUnpublishingServiceUuid(null);
    }
  };

  const handlePublishConfirm = async () => {
    if (!confirmPublishService) return;
    const svc = confirmPublishService;
    onPublishConfirmClose();
    setConfirmPublishService(null);
    await handlePublishService(svc);
  };

  const handleUnpublishConfirm = async () => {
    if (!confirmUnpublishService) return;
    const svc = confirmUnpublishService;
    onUnpublishConfirmClose();
    setConfirmUnpublishService(null);
    await handleUnpublishService(svc);
  };

  const handleDeleteClick = (service: Service) => {
    setServiceToDelete(service);
    onOpen();
  };

  const handleDeleteConfirm = async () => {
    if (!checkSessionExpiry()) return;
    if (!serviceToDelete?.serviceId) {
      toast({
        title: "Delete Failed",
        description: "Service ID is required for deletion",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      onClose();
      return;
    }
    setDeletingServiceUuid(serviceToDelete.serviceId);
    try {
      await deleteService(serviceToDelete.serviceId);
      toast({
        title: "Service deleted",
        description: `${serviceToDelete.name || serviceToDelete.service_id} has been deleted successfully.`,
        status: "success",
        duration: 5000,
        isClosable: true,
      });
      invalidateServiceRegistryQueries(queryClient);
      await fetchServices();
      if (selectedService?.serviceId === serviceToDelete.serviceId) {
        setIsViewingService(false);
        setSelectedService(null);
        setSelectedServiceModelDeprecated(null);
        setActiveTab(0);
      }
    } catch (error: unknown) {
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setDeletingServiceUuid(null);
      setServiceToDelete(null);
      onClose();
    }
  };

  const serviceColumns = useMemo((): AdminTableColumn<Service>[] => {
    return [
      {
        id: "name",
        header: "Name",
        sortable: {
          label: "Name",
          direction: nameSortDirection,
          onAsc: () => {
            setSortBy("name");
            setNameSortDirection("asc");
          },
          onDesc: () => {
            setSortBy("name");
            setNameSortDirection("desc");
          },
          ascAriaLabel: "Sort services by name ascending",
          descAriaLabel: "Sort services by name descending",
        },
        cell: (service) => (
          <Text fontSize="sm" noOfLines={1} title={service.name}>
            {service.name || "N/A"}
          </Text>
        ),
      },
      {
        id: "task",
        header: "Model Task Type",
        cell: (service) => (
          <Badge
            colorScheme={getTaskColor(
              service.model?.task?.type || service.task?.type || service.task_type
            )}
            fontSize="sm"
            p={1}
          >
            {(service.model?.task?.type || service.task?.type || service.task_type)?.toUpperCase() ||
              "N/A"}
          </Badge>
        ),
      },
      {
        id: "status",
        header: "Status",
        cell: (service) => (
          <Badge
            colorScheme={service.isPublished === true ? "green" : "gray"}
            fontSize="sm"
            p={1}
          >
            {service.isPublished === true ? "Published" : "Unpublished"}
          </Badge>
        ),
      },
      {
        id: "created",
        header: "Created At",
        cell: (service) => (
          <Text fontSize="sm" color="gray.600">
            {service.createdAt ? new Date(service.createdAt).toLocaleDateString() : "N/A"}
          </Text>
        ),
      },
      {
        id: "actions",
        header: "Actions",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (service) => (
          <HStack spacing={1}>
            <Tooltip label="View" placement="top" hasArrow>
              <IconButton
                aria-label="View"
                icon={<ViewIcon />}
                size="sm"
                variant="ghost"
                colorScheme="blue"
                _hover={{ bg: "blue.50" }}
                onClick={() =>
                  handleViewServiceRef.current?.(service.serviceId || service.service_id || "")
                }
              />
            </Tooltip>
            {!isRegistryReadOnly &&
              (service.isPublished === true ? (
                <Tooltip label="Unpublish" placement="top" hasArrow>
                  <IconButton
                    aria-label="Unpublish"
                    icon={<FaDownload />}
                    size="sm"
                    variant="ghost"
                    colorScheme="red"
                    _hover={{ bg: "red.50" }}
                    onClick={() => {
                      setConfirmUnpublishService(service);
                      onUnpublishConfirmOpen();
                    }}
                    isLoading={unpublishingServiceUuid === service.serviceId}
                    isDisabled={
                      unpublishingServiceUuid !== null || publishingServiceUuid !== null
                    }
                  />
                </Tooltip>
              ) : (
                <Tooltip
                  label={
                    isServiceModelDeprecated(service)
                      ? "This service cannot be published because its associated model is deprecated. Restore the model to ACTIVE before publishing."
                      : "Publish"
                  }
                  hasArrow
                  placement="top"
                >
                  <Box as="span" display="inline-block">
                    <IconButton
                      aria-label="Publish"
                      icon={<FaUpload />}
                      size="sm"
                      variant="ghost"
                      colorScheme="green"
                      _hover={{ bg: "green.50" }}
                      onClick={() => {
                        setConfirmPublishService(service);
                        onPublishConfirmOpen();
                      }}
                      isLoading={publishingServiceUuid === service.serviceId}
                      isDisabled={
                        unpublishingServiceUuid !== null ||
                        publishingServiceUuid !== null ||
                        isServiceModelDeprecated(service)
                      }
                    />
                  </Box>
                </Tooltip>
              ))}
            {!isRegistryReadOnly && (
              <Tooltip label="Delete" placement="top" hasArrow>
                <IconButton
                  aria-label="Delete"
                  icon={<DeleteIcon />}
                  size="sm"
                  variant="ghost"
                  colorScheme="red"
                  _hover={{ bg: "red.50" }}
                  onClick={() => handleDeleteClick(service)}
                  isLoading={deletingServiceUuid === service.serviceId}
                  isDisabled={deletingServiceUuid !== null}
                />
              </Tooltip>
            )}
          </HStack>
        ),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    nameSortDirection,
    unpublishingServiceUuid,
    publishingServiceUuid,
    deletingServiceUuid,
    isRegistryReadOnly,
    handleViewServiceRef,
  ]);

  return {
    services,
    isLoading,
    deletingServiceUuid,
    publishingServiceUuid,
    unpublishingServiceUuid,
    registryEpoch,
    setRegistryEpoch,
    searchQuery,
    setSearchQuery,
    filterStatus,
    setFilterStatus,
    filterTaskType,
    setFilterTaskType,
    sortBy,
    nameSortDirection,
    confirmPublishService,
    setConfirmPublishService,
    confirmUnpublishService,
    setConfirmUnpublishService,
    isPublishConfirmOpen,
    onPublishConfirmOpen,
    onPublishConfirmClose,
    isUnpublishConfirmOpen,
    onUnpublishConfirmOpen,
    onUnpublishConfirmClose,
    cancelPublishRef,
    cancelUnpublishRef,
    registryTableItems,
    hasActiveFilters,
    clearAllFilters,
    isOpen,
    onClose,
    cancelRef,
    serviceToDelete,
    fetchServices,
    handlePublishConfirm,
    handleUnpublishConfirm,
    handleDeleteClick,
    handleDeleteConfirm,
    serviceColumns,
  };
}
