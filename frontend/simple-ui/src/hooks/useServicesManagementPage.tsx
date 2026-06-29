import {
  Badge,
  Box,
  HStack,
  IconButton,
  Text,
  Tooltip,
  useDisclosure,
} from "@chakra-ui/react";
import { ViewIcon, DeleteIcon } from "@chakra-ui/icons";
import { FaUpload, FaDownload } from "react-icons/fa";
import { useRouter } from "next/router";
import { useQueryClient } from "@tanstack/react-query";
import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import {
  fetchAllServicesMatchingFilters,
  createService,
  getServiceById,
  updateService,
  deleteService,
  type Service,
} from "../services/servicesManagementService";
import { getAllModels, getModelById } from "../services/modelManagementService";
import type { ModelDetails } from "../types/platform";
import { useAuth } from "./useAuth";
import { isRegistryReadOnlyUser } from "../utils/rbac";
import { useSessionExpiry } from "./useSessionExpiry";
import { showError } from "../utils/errorHandler";
import { showToast } from "../utils/toast";
import { useAdminTableSurface } from "../components/common/TableControls";
import type { AdminTableColumn } from "../components/common/AdminDataTable";
import {
  buildModelsForDropdown,
  EMPTY_CREATE_SERVICE_FORM,
  filterAndSortRegistryServices,
  formatModelSubmissionDate,
  getServiceTaskColor,
  invalidateInferenceServiceQueries,
  isModelVersionDeprecated,
  isServiceModelDeprecated,
  preselectModelFromUrlQuery,
  resolvePublishedFilter,
  shallowReplaceServicesRoutePreservingTab,
} from "../utils/servicesManagementPage";

export function useServicesManagementPage() {
    const [services, setServices] = useState<Service[]>([]);
    const [models, setModels] = useState<ModelDetails[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoadingModels, setIsLoadingModels] = useState(false);
    const [selectedService, setSelectedService] = useState<Service | null>(null);
    const [isViewingService, setIsViewingService] = useState(false);
    const [isEditingService, setIsEditingService] = useState(false);
    const [formData, setFormData] = useState<Partial<Service>>({ ...EMPTY_CREATE_SERVICE_FORM });
    const [updateFormData, setUpdateFormData] = useState<Partial<Service>>({});
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [deletingServiceUuid, setDeletingServiceUuid] = useState<string | null>(null);
    const [publishingServiceUuid, setPublishingServiceUuid] = useState<string | null>(null);
    const [unpublishingServiceUuid, setUnpublishingServiceUuid] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState(0);
    const [registryEpoch, setRegistryEpoch] = useState(0);
    const [searchQuery, setSearchQuery] = useState("");
    const [filterStatus, setFilterStatus] = useState<string>("");
    const [filterTaskType, setFilterTaskType] = useState<string>("");
    const [sortBy, setSortBy] = useState<"time" | "name">("time");
    const [nameSortDirection, setNameSortDirection] = useState<"asc" | "desc">("asc");
    const [confirmPublishService, setConfirmPublishService] = useState<Service | null>(null);
    const [confirmUnpublishService, setConfirmUnpublishService] = useState<Service | null>(null);
    /** When viewing a service, true if its model is deprecated (fetched by modelId); null until we know */
    const [selectedServiceModelDeprecated, setSelectedServiceModelDeprecated] = useState<boolean | null>(null);
    const { isOpen: isPublishConfirmOpen, onOpen: onPublishConfirmOpen, onClose: onPublishConfirmClose } = useDisclosure();
    const { isOpen: isUnpublishConfirmOpen, onOpen: onUnpublishConfirmOpen, onClose: onUnpublishConfirmClose } = useDisclosure();
    const cancelPublishRef = useRef<HTMLButtonElement>(null);
    const cancelUnpublishRef = useRef<HTMLButtonElement>(null);
    const { user } = useAuth();
    const isRegistryReadOnly = isRegistryReadOnlyUser(user?.roles);
    const viewTabIndex = isRegistryReadOnly ? 1 : 2;



    // Client-side name filter + sort over the full fetched registry list.
    const registryTableItems = useMemo(
      () => filterAndSortRegistryServices(services, searchQuery, sortBy, nameSortDirection),
      [services, searchQuery, sortBy, nameSortDirection]
    );

    const hasActiveFilters = filterStatus !== "" || filterTaskType !== "" || searchQuery.trim() !== "";
    const clearAllFilters = () => {
      setSearchQuery("");
      setFilterStatus("");
      setFilterTaskType("");
    };

    const router = useRouter();
    const queryClient = useQueryClient();

    const { checkSessionExpiry } = useSessionExpiry();

    const { isOpen, onOpen, onClose } = useDisclosure();
    const cancelRef = useRef<HTMLButtonElement>(null);
    const [serviceToDelete, setServiceToDelete] = useState<Service | null>(null);

    // Check if user is GUEST or USER and redirect if so
    useEffect(() => {
      if (user?.roles?.includes('GUEST') || user?.roles?.includes('USER')) {
        showToast({
          type: "error",
          message: "You do not have access to Services Management.",
        });
        router.push('/');
      }
    }, [user, router]);
    // Model fetched by ID when navigating from a deprecated model's "Create Service" (not in active list)
    const [preselectedModelFromQuery, setPreselectedModelFromQuery] = useState<ModelDetails | null>(null);

    // Fetch all services for current task/publish filters (paginated API walk) for client search + pagination
    const fetchServices = useCallback(async () => {
      setIsLoading(true);
      try {
        const isPublishedFilter = resolvePublishedFilter(filterStatus);

        const result = await fetchAllServicesMatchingFilters({
          taskType: filterTaskType || undefined,
          isPublished: isPublishedFilter,
        });
        setServices(result.items);
      } catch (error: any) {
        console.error("Failed to fetch services:", error);
        showError(error);
        setServices([]);
      } finally {
        setIsLoading(false);
      }
    }, [filterTaskType, filterStatus]);

    useEffect(() => { fetchServices(); }, [fetchServices]);

    // Fetch models on component mount (for dropdown)
    useEffect(() => {
      const fetchModels = async () => {
        setIsLoadingModels(true);
        try {
          const fetchedModels = await getAllModels();
          // Filter to only show ACTIVE models
          const activeModels = fetchedModels.filter(
            (model) => model.versionStatus?.toLowerCase() === "active" || !model.versionStatus
          );
          setModels(activeModels);
        } catch (error: any) {
          console.error("Failed to fetch models:", error);
          // Don't show toast for models - it's not critical for the page to work
          setModels([]);
        } finally {
          setIsLoadingModels(false);
        }
      };

      fetchModels();
    }, []);

    // Sync URL tab param to activeTab (e.g. when header back clears tab=2, show list)
    useEffect(() => {
      const t = router.query.tab;
      if (isRegistryReadOnly && (t === "1" || t === "create")) {
        setActiveTab(0);
        if (router.query.tab || router.query.modelId) {
          const q = { ...router.query } as Record<string, string>;
          delete q.tab;
          delete q.modelId;
          router.replace({ pathname: "/services-management", query: q }, undefined, { shallow: true });
        }
        return;
      }
      if (t === "2") setActiveTab(viewTabIndex);
      else if (t === "1" || t === "create") setActiveTab(1);
      else if (t !== "1" && t !== "2") setActiveTab(0);
    }, [router.query.tab, isRegistryReadOnly, router, viewTabIndex]);

    // Handle query parameters for pre-selecting model from model-management page
    useEffect(() => {
      if (isRegistryReadOnly) return;
      const { modelId, tab } = router.query;
      if (!modelId || typeof modelId !== "string" || models.length === 0) return;

      void preselectModelFromUrlQuery(
        modelId,
        models,
        formData.modelId,
        {
          setActiveTab,
          setPreselectedModelFromQuery,
          handleModelNameChange,
          clearModelIdFromUrl: () => shallowReplaceServicesRoutePreservingTab(router),
        },
        { switchToCreateTab: tab === "create" },
      );
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [router.query, models]);

    const { cardBg, borderColor: cardBorder } = useAdminTableSurface();

    // Dropdown options: active models only (no deprecated). Include preselected from query only if not deprecated and not already in list.
    const modelsForDropdown = useMemo(
      () => buildModelsForDropdown(models, preselectedModelFromQuery),
      [models, preselectedModelFromQuery]
    );



    const handleInputChange = (
      field: keyof Service,
      value: string
    ) => {
      setFormData((prev) => ({
        ...prev,
        [field]: value,
      }));
    };

    // Handle model name selection and derive model metadata
    const handleModelNameChange = async (modelId: string) => {
      // Check session expiry before fetching model details
      if (!checkSessionExpiry()) return;
      if (modelId) {
        try {
          setIsLoadingModels(true);
          const modelDetails = await getModelById(modelId);

          // Extract task_type from model
          const taskType = modelDetails?.task?.type || modelDetails?.task_type || modelDetails?.taskType || "";

          // Extract model version (required field after migration)
          const modelVersion = modelDetails?.version || modelDetails?.modelVersion || "1.0";

          // Extract model submission date (if API returns it)
          const modelSubmissionDate = formatModelSubmissionDate(
            modelDetails?.submittedOn ?? modelDetails?.submitted_on ?? ""
          );

          // Get model name for display
          const modelName = modelDetails?.name || modelDetails?.modelId || modelDetails?.model_id || "";

          setFormData((prev) => ({
            ...prev,
            modelId: modelId,
            modelName: modelName,
            task_type: taskType,
            modelSubmissionDate: modelSubmissionDate,
            modelVersion: modelVersion,
          }));
        } catch (error: any) {
          console.error("Failed to fetch model details:", error);
          showToast({
            type: "warning",
            message: error instanceof Error ? error.message : "Failed to fetch model details",
          });
        } finally {
          setIsLoadingModels(false);
        }
      } else {
        // Clear fields if no model selected
        setFormData((prev) => ({
          ...prev,
          modelId: "",
          modelName: "",
          task_type: "",
          modelSubmissionDate: "",
          modelVersion: "",
        }));
      }
    };

    const handleSubmit = async (e: React.FormEvent) => {
      e.preventDefault();

      // Check session expiry before submitting
      if (!checkSessionExpiry()) return;

      setIsSubmitting(true);

      try {
        // Auto-generate serviceId from name and timestamp
        const timestamp = Date.now();
        const serviceId = `${formData.name?.toLowerCase().replaceAll(/\s+/g, '-') || 'service'}-${timestamp}`;

        // Prepare service data with auto-generated serviceId.
        // Do not send modelSubmissionDate because backend owns this field.
        const serviceFormData: Partial<Service> = { ...formData };
        delete serviceFormData.modelSubmissionDate;
        const serviceData: Partial<Service> = {
          ...serviceFormData,
          serviceId: serviceId,
          publishedOn: Math.floor(Date.now() / 1000),
          hardwareDescription: 'Default hardware', // Default value since field is removed
          api_key: '', // Default empty since field is removed
          status: 'active', // Default status
        };

        await createService(serviceData);

        invalidateInferenceServiceQueries(queryClient);

        showToast({
          type: "success",
          message: "Service has been created successfully.",
        });

        // Reset form
        setFormData({ ...EMPTY_CREATE_SERVICE_FORM });
        setPreselectedModelFromQuery(null);

        await fetchServices();
        setRegistryEpoch((e) => e + 1);

        // Switch to list tab
        setActiveTab(0);
      } catch (error: any) {
        showError(error);
      } finally {
        setIsSubmitting(false);
      }
    };

    const canCreateService =
      !!formData.name?.trim() &&
      !!formData.serviceDescription?.trim() &&
      !!formData.modelId?.trim() &&
      !!formData.endpoint?.trim();

    const isCreateFormModelSelected = !!formData.modelId?.trim();

    const handleViewService = async (serviceId: string) => {
      // Check session expiry before viewing service
      if (!checkSessionExpiry()) return;
      setSelectedServiceModelDeprecated(null);
      try {
        const service = await getServiceById(serviceId);
        setSelectedService(service);
        setUpdateFormData(service);
        setIsViewingService(true);
        setActiveTab(viewTabIndex);
        router.replace({ pathname: "/services-management", query: { ...router.query, tab: "2" } }, undefined, { shallow: true });
        // Fetch model to know if deprecated (detail API may not include model.versionStatus)
        const modelId = service.modelId || service.model_id;
        if (modelId) {
          try {
            const modelDetails = await getModelById(modelId);
            const deprecated =
              modelDetails?.versionStatus &&
              typeof modelDetails.versionStatus === "string" &&
              modelDetails.versionStatus.toLowerCase() === "deprecated";
            setSelectedServiceModelDeprecated(!!deprecated);
          } catch {
            setSelectedServiceModelDeprecated(false);
          }
        } else {
          setSelectedServiceModelDeprecated(false);
        }
      } catch (error: any) {
        const errorMessage = error instanceof Error ? error.message : "Failed to fetch service details";
        showError(error);
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

    const handlePublishService = async (service: Service) => {
      // Frontend safeguard: do not allow publishing if the associated model is deprecated
      try {
        const modelId = service.modelId || service.model_id;
        if (modelId) {
          const modelDetails = await getModelById(modelId);
          const isDeprecated = isModelVersionDeprecated(modelDetails?.versionStatus);
          if (isDeprecated) {
            showToast({
              type: "error",
              message:
                "This service cannot be published because its associated model version is deprecated. Please restore the model to ACTIVE before publishing the service.",
            });
            return;
          }
        }
      } catch (e) {
        // If model lookup fails, fall through and let backend validation (if any) handle it
        // Do not block publish solely due to a transient read error.
        // eslint-disable-next-line no-console
        console.warn("Failed to verify model status before publishing service:", e);
      }

      if (!service.serviceId) {
        showToast({
          type: "error",
          message: "Service ID is required",
        });
        return;
      }

      setPublishingServiceUuid(service.serviceId);

      try {
        // Update service to set isPublished = true using PATCH with only serviceId and isPublished
        const updatedService = await updateService({
          serviceId: service.serviceId,
          isPublished: true,
        });

        showToast({
          type: "success",
          message: `${service.name || service.serviceId} has been published successfully.`,
        });

        // Invalidate all service-related queries to refresh service lists across all pages
        invalidateInferenceServiceQueries(queryClient);

        // Refresh services list
        await fetchServices();

        // Update selected service if it's the one being published
        if (selectedService?.serviceId === service.serviceId) {
          setSelectedService(updatedService);
        }
      } catch (error: any) {
        const errorMessage = error instanceof Error ? error.message : "Failed to publish service";
        showError(error);
      } finally {
        setPublishingServiceUuid(null);
      }
    };

    const handleUnpublishService = async (service: Service) => {
      if (!service.serviceId) {
        showToast({
          type: "error",
          message: "Service ID is required",
        });
        return;
      }

      setUnpublishingServiceUuid(service.serviceId);

      try {
        // Update service to set isPublished = false using PATCH with only serviceId and isPublished
        const updatedService = await updateService({
          serviceId: service.serviceId,
          isPublished: false,
        });

        showToast({
          type: "success",
          message: `${service.name || service.serviceId} has been unpublished successfully.`,
        });

        // Invalidate all service-related queries to refresh service lists across all pages
        invalidateInferenceServiceQueries(queryClient);

        // Refresh services list
        await fetchServices();

        // Update selected service if it's the one being unpublished
        if (selectedService?.serviceId === service.serviceId) {
          setSelectedService(updatedService);
        }
      } catch (error: any) {
        const errorMessage = error instanceof Error ? error.message : "Failed to unpublish service";
        showError(error);
      } finally {
        setUnpublishingServiceUuid(null);
      }
    };

    const handleDeleteClick = (service: Service) => {
      setServiceToDelete(service);
      onOpen();
    };

    const handleDeleteConfirm = async () => {
      if (!checkSessionExpiry()) return;
      if (!serviceToDelete?.serviceId) {
        showToast({
          type: "error",
          message: "Service ID is required for deletion",
        });
        onClose();
        return;
      }
      setDeletingServiceUuid(serviceToDelete.serviceId);
      try {
        await deleteService(serviceToDelete.serviceId);
        showToast({
          type: "success",
          message: `${serviceToDelete.name || serviceToDelete.service_id} has been deleted successfully.`,
        });
        invalidateInferenceServiceQueries(queryClient);
        await fetchServices();
        if (selectedService?.serviceId === serviceToDelete.serviceId) {
          setIsViewingService(false);
          setSelectedService(null);
          setSelectedServiceModelDeprecated(null);
          setActiveTab(0);
        }
      } catch (error: any) {
        showError(error);
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
              colorScheme={getServiceTaskColor(
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
                    handleViewService(service.serviceId || service.service_id || "")
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
    ]);

    const handleMainTabChange = useCallback(
      (index: number) => {
        if (isRegistryReadOnly && index === 1) return;
        setActiveTab(index);
        if (index !== viewTabIndex) {
          setIsViewingService(false);
          setSelectedService(null);
          setSelectedServiceModelDeprecated(null);
        }
        const q = { ...router.query } as Record<string, string>;
        if (index === 0) delete q.tab;
        else q.tab = String(index);
        router.replace({ pathname: "/services-management", query: q }, undefined, { shallow: true });
      },
      [isRegistryReadOnly, viewTabIndex, router],
    );

  return {
    cardBg,
    cardBorder,
    isRegistryReadOnly,
    activeTab,
    setActiveTab,
    handleMainTabChange,
    viewTabIndex,
    isViewingService,
    setIsViewingService,
    selectedService,
    setSelectedService,
    setSelectedServiceModelDeprecated,
    router,
    registryTableItems,
    serviceColumns,
    filterStatus,
    filterTaskType,
    registryEpoch,
    isLoading,
    services,
    hasActiveFilters,
    clearAllFilters,
    searchQuery,
    setSearchQuery,
    setFilterStatus,
    setFilterTaskType,
    handleViewService,
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
    isEditingService,
    selectedServiceModelDeprecated,
    isServiceModelDeprecated,
    unpublishingServiceUuid,
    publishingServiceUuid,
    setConfirmUnpublishService,
    onUnpublishConfirmOpen,
    setConfirmPublishService,
    onPublishConfirmOpen,
    handleDeleteConfirm,
    isOpen,
    onClose,
    serviceToDelete,
    deletingServiceUuid,
    cancelRef,
    isPublishConfirmOpen,
    onPublishConfirmClose,
    handlePublishConfirm,
    confirmPublishService,
    cancelPublishRef,
    isUnpublishConfirmOpen,
    onUnpublishConfirmClose,
    handleUnpublishConfirm,
    confirmUnpublishService,
    cancelUnpublishRef,
    getServiceTaskColor,
  };

}
