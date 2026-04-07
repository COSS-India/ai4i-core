// Services Management page with list, create, view, update, and delete functionality

import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormLabel,
  Heading,
  IconButton,
  Input,
  InputGroup,
  InputLeftElement,
  Select,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  Text,
  VStack,
  HStack,
  useColorModeValue,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  Textarea,
  SimpleGrid,
  Grid,
  useDisclosure,
  Tooltip,
} from "@chakra-ui/react";
import Head from "next/head";
import { SearchIcon, ViewIcon, DeleteIcon } from "@chakra-ui/icons";
import { FaUpload } from "react-icons/fa";
import { useRouter } from "next/router";
import { useQueryClient } from "@tanstack/react-query";
import React, { useState, useEffect, useRef, useMemo } from "react";
import ContentLayout from "../components/common/ContentLayout";
import {
  listServices,
  createService,
  getServiceById,
  updateService,
  deleteService,
  Service,
} from "../services/servicesManagementService";
import { getAllModels, getModelById } from "../services/modelManagementService";
import { useAuth } from "../hooks/useAuth";
import { useSessionExpiry } from "../hooks/useSessionExpiry";
import { extractErrorInfo } from "../utils/errorHandler";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";
import ConfirmDialog from "../components/common/ConfirmDialog";
import { TableFilterToolbar, TablePaginationBar, TableSortHeader } from "../components/common/TableControls";

const ServicesManagementPage: React.FC = () => {
  const [services, setServices] = useState<Service[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [isViewingService, setIsViewingService] = useState(false);
  const [isEditingService, setIsEditingService] = useState(false);
  const [formData, setFormData] = useState<Partial<Service>>({
    name: "",
    serviceDescription: "",
    publishedOn: Math.floor(Date.now() / 1000),
    modelId: "",
    modelName: "", // Store selected model name for display
    endpoint: "",
    task_type: "",
    modelVersion: "1.0",
  });
  const [updateFormData, setUpdateFormData] = useState<Partial<Service>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [deletingServiceUuid, setDeletingServiceUuid] = useState<string | null>(null);
  const [publishingServiceUuid, setPublishingServiceUuid] = useState<string | null>(null);
  const [unpublishingServiceUuid, setUnpublishingServiceUuid] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [listPage, setListPage] = useState(1);
  const [listPageSize, setListPageSize] = useState(25);
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
  const toast = useToastWithDeduplication();
  const { user } = useAuth();

  const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

  const isServiceModelDeprecated = (service: Service | null | undefined): boolean => {
    if (!service) return false;
    const modelVersionStatus =
      (service.model as any)?.versionStatus ??
      (service.model as any)?.version_status ??
      (service as any).versionStatus ??
      (service as any).version_status;
    return typeof modelVersionStatus === "string" && modelVersionStatus.toLowerCase() === "deprecated";
  };

  /** Parse timestamp safely for SQL-like ordering */
  const getSortTimestamp = (value?: string | number | null): number => {
    if (value == null) return 0;
    if (typeof value === "number") return value > 1e12 ? value : value * 1000;
    const t = new Date(value).getTime();
    return Number.isNaN(t) ? 0 : t;
  };

  const taskTypeOptions = useMemo(() => {
    const types = new Set<string>();
    services.forEach((s) => {
      const t = s.model?.task?.type || s.task?.type || s.task_type;
      if (t) types.add(String(t).toUpperCase());
    });
    return Array.from(types).sort();
  }, [services]);

  const filteredServices = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = services.filter((s) => {
      if (q) {
        if (!(s.name ?? "").toLowerCase().includes(q)) return false;
      }
      if (filterStatus) {
        const published = s.isPublished === true;
        if (filterStatus === "published" && !published) return false;
        if (filterStatus === "unpublished" && published) return false;
      }
      if (filterTaskType) {
        const task = (s.model?.task?.type ?? s.task?.type ?? s.task_type ?? "").toString().toUpperCase();
        if (task !== filterTaskType) return false;
      }
      return true;
    });
    return [...filtered].sort((a, b) => {
      const createdA = getSortTimestamp(a.created_at);
      const createdB = getSortTimestamp(b.created_at);
      const updatedA = getSortTimestamp(a.updated_at);
      const updatedB = getSortTimestamp(b.updated_at);
      const nameCmp = (a.name ?? "").localeCompare(b.name ?? "", undefined, { sensitivity: "base" });

      // Default mode: mirror SQL ordering exactly -> ORDER BY created_at DESC, updated_at DESC.
      if (sortBy === "time") {
        if (createdB !== createdA) return createdB - createdA;
        if (updatedB !== updatedA) return updatedB - updatedA;
        return 0;
      }

      // Name mode is applied only when user clicks one of the name arrows.
      if (nameCmp !== 0) return nameSortDirection === "asc" ? nameCmp : -nameCmp;
      // Mirror SQL ordering exactly -> ORDER BY created_at DESC, updated_at DESC.
      if (createdB !== createdA) return createdB - createdA;
      if (updatedB !== updatedA) return updatedB - updatedA;
      return 0;
    });
  }, [services, searchQuery, filterStatus, filterTaskType, sortBy, nameSortDirection]);

  const totalServices = filteredServices.length;
  const totalPages = Math.max(1, Math.ceil(totalServices / listPageSize));
  const startRow = totalServices === 0 ? 0 : (listPage - 1) * listPageSize + 1;
  const endRow = Math.min(listPage * listPageSize, totalServices);
  const paginatedServices = filteredServices.slice((listPage - 1) * listPageSize, listPage * listPageSize);

  useEffect(() => {
    if (listPage > totalPages && totalPages >= 1) setListPage(totalPages);
  }, [totalServices, listPageSize, listPage, totalPages]);

  const hasActiveFilters = filterStatus !== "" || filterTaskType !== "" || searchQuery.trim() !== "";
  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterStatus("");
    setFilterTaskType("");
    setListPage(1);
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
      toast({
        title: "Access Denied",
        description: "You do not have access to Services Management.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      router.push('/');
    }
  }, [user, router, toast]);
  // Model fetched by ID when navigating from a deprecated model's "Create Service" (not in active list)
  const [preselectedModelFromQuery, setPreselectedModelFromQuery] = useState<any | null>(null);

  // Fetch services on component mount
  useEffect(() => {
    const fetchServices = async () => {
      setIsLoading(true);
      try {
        const fetchedServices = await listServices();
        setServices(fetchedServices);
      } catch (error: any) {
        console.error("Failed to fetch services:", error);
        
        // Use centralized error handler
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
    };

    fetchServices();
  }, [toast]);

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
    if (t === "2") setActiveTab(2);
    else if (t === "1" || t === "create") setActiveTab(1);
    else if (t !== "1" && t !== "2") setActiveTab(0);
  }, [router.query.tab]);

  // Handle query parameters for pre-selecting model from model-management page
  useEffect(() => {
    const { modelId, tab } = router.query;
    if (!modelId || typeof modelId !== "string") return;

    const runPreselect = async () => {
      // Switch to Create Service tab if specified
      if (tab === "create") {
        setActiveTab(1);
      }

      const inActiveList = models.some(
        (m) => (m.modelId || m.model_id) === modelId
      );
      if (inActiveList && formData.modelId !== modelId) {
        handleModelNameChange(modelId);
        // Preserve current tab (e.g. ?tab=create) while clearing modelId from URL
        const { tab: currentTab } = router.query;
        const nextQuery: Record<string, string> = {};
        if (typeof currentTab === "string") {
          nextQuery.tab = currentTab;
        }
        router.replace(
          { pathname: "/services-management", query: nextQuery },
          undefined,
          { shallow: true }
        );
        return;
      }

      // Model not in active list - only add to dropdown if not deprecated (deprecated models must not appear in Create Service)
      if (!inActiveList) {
        try {
          const modelDetails = await getModelById(modelId);
          const isDeprecated = modelDetails?.versionStatus?.toLowerCase() === "deprecated";
          if (modelDetails && !isDeprecated) {
            setPreselectedModelFromQuery(modelDetails);
            if (formData.modelId !== modelId) {
              handleModelNameChange(modelId);
            }
          }
        } catch (e) {
          console.error("Failed to load preselected model:", e);
        }
        const { tab: currentTab } = router.query;
        const nextQuery: Record<string, string> = {};
        if (typeof currentTab === "string") {
          nextQuery.tab = currentTab;
        }
        router.replace(
          { pathname: "/services-management", query: nextQuery },
          undefined,
          { shallow: true }
        );
      }
    };

    if (models.length > 0) {
      runPreselect();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.query, models]);

  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const tableBg = useColorModeValue("white", "gray.800");
  const tableHeaderBg = useColorModeValue("gray.50", "gray.700");
  const tableRowHoverBg = useColorModeValue("gray.50", "gray.700");

  // Dropdown options: active models only (no deprecated). Include preselected from query only if not deprecated and not already in list.
  const preselectedNotDeprecated =
    preselectedModelFromQuery &&
    preselectedModelFromQuery.versionStatus?.toLowerCase() !== "deprecated";
  const modelsForDropdown =
    preselectedNotDeprecated &&
    !models.some(
      (m) =>
        (m.modelId || m.model_id) ===
        (preselectedModelFromQuery.modelId || preselectedModelFromQuery.model_id)
    )
      ? [preselectedModelFromQuery, ...models]
      : models;

  const getTaskColor = (taskType?: string) => {
    if (!taskType) return "gray";
    switch (taskType.toLowerCase()) {
      case "asr":
        return "orange";
      case "nmt":
        return "green";
      case "tts":
        return "blue";
      case "llm":
        return "purple";
      default:
        return "gray";
    }
  };

  const getStatusColor = (status?: string) => {
    if (!status) return "gray";
    switch (status.toLowerCase()) {
      case "active":
        return "green";
      case "inactive":
        return "red";
      case "pending":
        return "yellow";
      default:
        return "gray";
    }
  };

  const handleInputChange = (
    field: keyof Service,
    value: string
  ) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  // Handle model name selection and derive modelId, task_type, and modelVersion
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
        
        // Get model name for display
        const modelName = modelDetails?.name || modelDetails?.modelId || modelDetails?.model_id || "";
        
        setFormData((prev) => ({
          ...prev,
          modelId: modelId,
          modelName: modelName,
          task_type: taskType,
          modelVersion: modelVersion,
        }));
      } catch (error: any) {
        console.error("Failed to fetch model details:", error);
        toast({
          title: "Failed to Load Model",
          description: error instanceof Error ? error.message : "Failed to fetch model details",
          status: "warning",
          duration: 3000,
          isClosable: true,
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
      const serviceId = `${formData.name?.toLowerCase().replace(/\s+/g, '-') || 'service'}-${timestamp}`;
      
      // Prepare service data with auto-generated serviceId
      const serviceData: Partial<Service> = {
        ...formData,
        serviceId: serviceId,
        publishedOn: Math.floor(Date.now() / 1000),
        hardwareDescription: 'Default hardware', // Default value since field is removed
        api_key: '', // Default empty since field is removed
        status: 'active', // Default status
      };

      const createdService = await createService(serviceData);

      // Invalidate all service-related queries to refresh service lists across all pages
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({ queryKey: ["speaker-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-detection-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["audioLanguageDetectionServices"] });

      toast({
        title: "Service created",
        description: "Service has been created successfully.",
        status: "success",
        duration: 5000,
        isClosable: true,
      });

      // Reset form
      setFormData({
        name: "",
        serviceDescription: "",
        publishedOn: Math.floor(Date.now() / 1000),
        modelId: "",
        modelName: "",
        endpoint: "",
        task_type: "",
        modelVersion: "1.0",
      });
      setPreselectedModelFromQuery(null);

      // Refresh services list
      const fetchedServices = await listServices();
      setServices(fetchedServices);

      // Switch to list tab
      setActiveTab(0);
    } catch (error: any) {
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const canCreateService =
    !!formData.name?.trim() &&
    !!formData.serviceDescription?.trim() &&
    !!formData.modelId?.trim() &&
    !!formData.endpoint?.trim();

  const handleViewService = async (serviceId: string) => {
    // Check session expiry before viewing service
    if (!checkSessionExpiry()) return;
    setSelectedServiceModelDeprecated(null);
    try {
      const service = await getServiceById(serviceId);
      setSelectedService(service);
      setUpdateFormData(service);
      setIsViewingService(true);
      setActiveTab(2);
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
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const handleUpdateService = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Check session expiry before updating
    if (!checkSessionExpiry()) return;
    
    if (!selectedService?.uuid) {
      toast({
        title: "Update Failed",
        description: "Service UUID is required for update",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      return;
    }

    setIsUpdating(true);

    try {
      const updatedService = await updateService({
        ...updateFormData,
        uuid: selectedService.uuid,
      });

      // Invalidate all service-related queries to refresh service lists across all pages
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({ queryKey: ["speaker-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-detection-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["audioLanguageDetectionServices"] });

      toast({
        title: "Service Updated",
        description: "Service has been updated successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      setSelectedService(updatedService);
      setIsEditingService(false);

      // Refresh services list
      const fetchedServices = await listServices();
      setServices(fetchedServices);
    } catch (error: any) {
      const errorMessage = error instanceof Error ? error.message : "Failed to update service";
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsUpdating(false);
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
      // If model lookup fails, fall through and let backend validation (if any) handle it
      // Do not block publish solely due to a transient read error.
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

    setPublishingServiceUuid(service.uuid || service.serviceId);

    try {
      // Update service to set isPublished = true using PATCH with only serviceId and isPublished
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

      // Invalidate all service-related queries to refresh service lists across all pages
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({ queryKey: ["speaker-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-detection-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["audioLanguageDetectionServices"] });

      // Refresh services list
      const fetchedServices = await listServices();
      setServices(fetchedServices);

      // Update selected service if it's the one being published
      if (selectedService?.uuid === service.uuid) {
        setSelectedService(updatedService);
      }
    } catch (error: any) {
      const errorMessage = error instanceof Error ? error.message : "Failed to publish service";
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

    setUnpublishingServiceUuid(service.uuid || service.serviceId);

    try {
      // Update service to set isPublished = false using PATCH with only serviceId and isPublished
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

      // Invalidate all service-related queries to refresh service lists across all pages
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({ queryKey: ["speaker-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-detection-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["audioLanguageDetectionServices"] });

      // Refresh services list
      const fetchedServices = await listServices();
      setServices(fetchedServices);

      // Update selected service if it's the one being unpublished
      if (selectedService?.uuid === service.uuid) {
        setSelectedService(updatedService);
      }
    } catch (error: any) {
      const errorMessage = error instanceof Error ? error.message : "Failed to unpublish service";
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

  const handleDeleteClick = (service: Service) => {
    setServiceToDelete(service);
    onOpen();
  };

  const handleDeleteConfirm = async () => {
    if (!checkSessionExpiry()) return;
    if (!serviceToDelete?.uuid) {
      toast({
        title: "Delete Failed",
        description: "Service UUID is required for deletion",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      onClose();
      return;
    }
    setDeletingServiceUuid(serviceToDelete.uuid);
    try {
      await deleteService(serviceToDelete.uuid);
      toast({
        title: "Service deleted",
        description: `${serviceToDelete.name || serviceToDelete.service_id} has been deleted successfully.`,
        status: "success",
        duration: 5000,
        isClosable: true,
      });
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({ queryKey: ["speaker-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-detection-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["audioLanguageDetectionServices"] });
      const fetchedServices = await listServices();
      setServices(fetchedServices);
      if (selectedService?.uuid === serviceToDelete.uuid) {
        setIsViewingService(false);
        setSelectedService(null);
        setSelectedServiceModelDeprecated(null);
        setActiveTab(0);
      }
    } catch (error: any) {
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

  return (
    <>
      <Head>
        <title>Services Management - AI4I Platform</title>
        <meta name="description" content="Manage and configure services" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full">
          {/* Page Header */}
          <Box textAlign="center" mb={2}>
            <Heading size="lg" color="gray.800" mb={1} userSelect="none" cursor="default" tabIndex={-1}>
              Services Management
            </Heading>
            <Text color="gray.600" fontSize="sm" userSelect="none" cursor="default">
              Manage and configure services
            </Text>
          </Box>

          <Grid gap={8} w="full" mx="auto">
            <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px">
              <Tabs
                colorScheme="blue"
                variant="enclosed"
                index={activeTab}
                onChange={(index) => {
                  setActiveTab(index);
                  if (index !== 2) {
                    setIsViewingService(false);
                    setSelectedService(null);
                    setSelectedServiceModelDeprecated(null);
                  }
                  const q = { ...router.query } as Record<string, string>;
                  if (index === 0) delete q.tab;
                  else q.tab = String(index);
                  router.replace({ pathname: "/services-management", query: q }, undefined, { shallow: true });
                }}
              >
                <TabList>
                  <Tab fontWeight="semibold">Service Registry</Tab>
                  <Tab fontWeight="semibold">Create Service</Tab>
                  {isViewingService && (
                    <Tab fontWeight="semibold">View Service</Tab>
                  )}
                </TabList>

                <TabPanels>
                  {/* Service Registry Tab */}
                  <TabPanel px={0} pt={6}>
                    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                      <CardHeader>
                        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
                          Service Registry
                        </Heading>
                      </CardHeader>
                      <CardBody>
                        {isLoading ? (
                          <Box textAlign="center" py={8}>
                            <Text color="gray.500">Loading services...</Text>
                          </Box>
                        ) : (
                          <>
                          <VStack align="stretch" spacing={4} mb={4}>
                            <TableFilterToolbar
                              hasActiveFilters={hasActiveFilters}
                              onClear={clearAllFilters}
                              align="flex-end"
                            >
                              <FormControl w={{ base: "full", md: "280px" }}>
                                <FormLabel fontSize="sm" fontWeight="medium" mb={1}>Search</FormLabel>
                                <InputGroup>
                                  <InputLeftElement pointerEvents="none">
                                    <SearchIcon color="gray.400" />
                                  </InputLeftElement>
                                  <Input
                                    placeholder="Search by service name..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    bg={cardBg}
                                    pl={10}
                                    size="sm"
                                  />
                                </InputGroup>
                              </FormControl>
                              <FormControl w={{ base: "full", sm: "140px" }}>
                                <FormLabel fontSize="sm" fontWeight="medium" mb={1}>Status</FormLabel>
                                <Select
                                  size="sm"
                                  value={filterStatus}
                                  onChange={(e) => { setFilterStatus(e.target.value); setListPage(1); }}
                                  bg={cardBg}
                                >
                                  <option value="">All</option>
                                  <option value="published">Published</option>
                                  <option value="unpublished">Unpublished</option>
                                </Select>
                              </FormControl>
                              <FormControl w={{ base: "full", sm: "160px" }}>
                                <FormLabel fontSize="sm" fontWeight="medium" mb={1}>Task type</FormLabel>
                                <Select
                                  size="sm"
                                  value={filterTaskType}
                                  onChange={(e) => { setFilterTaskType(e.target.value); setListPage(1); }}
                                  bg={cardBg}
                                >
                                  <option value="">All</option>
                                  {taskTypeOptions.map((t) => (
                                    <option key={t} value={t}>{t}</option>
                                  ))}
                                </Select>
                              </FormControl>
                            </TableFilterToolbar>
                            {hasActiveFilters && (
                              <HStack spacing={2} flexWrap="wrap">
                                {searchQuery.trim() && (
                                  <Badge colorScheme="blue" fontSize="xs" px={2} py={1} cursor="pointer" onClick={() => { setSearchQuery(""); setListPage(1); }} _hover={{ opacity: 0.8 }}>
                                    Search: &quot;{searchQuery.trim()}&quot; ×
                                  </Badge>
                                )}
                                {filterStatus && (
                                  <Badge colorScheme="gray" fontSize="xs" px={2} py={1} cursor="pointer" onClick={() => { setFilterStatus(""); setListPage(1); }} _hover={{ opacity: 0.8 }}>
                                    Status: {filterStatus === "published" ? "Published" : "Unpublished"} ×
                                  </Badge>
                                )}
                                {filterTaskType && (
                                  <Badge colorScheme="gray" fontSize="xs" px={2} py={1} cursor="pointer" onClick={() => { setFilterTaskType(""); setListPage(1); }} _hover={{ opacity: 0.8 }}>
                                    Task: {filterTaskType} ×
                                  </Badge>
                                )}
                              </HStack>
                            )}
                          </VStack>

                          {filteredServices.length === 0 ? (
                            <Box textAlign="center" py={8}>
                              <Text color="gray.500">
                                No results found.
                                {services.length === 0 ? " No services in the registry yet." : " Try adjusting your search or filters."}
                              </Text>
                            </Box>
                          ) : (
                          <Box maxH="60vh" overflowY="auto" overflowX="hidden">
                            <Table variant="simple" bg={tableBg} size="sm" w="100%">
                              <Thead bg={tableHeaderBg}>
                                <Tr>
                                  <Th>
                                    <TableSortHeader
                                      label="Name"
                                      direction={nameSortDirection}
                                      onAsc={() => {
                                        setSortBy("name");
                                        setNameSortDirection("asc");
                                        setListPage(1);
                                      }}
                                      onDesc={() => {
                                        setSortBy("name");
                                        setNameSortDirection("desc");
                                        setListPage(1);
                                      }}
                                      ascAriaLabel="Sort services by name ascending"
                                      descAriaLabel="Sort services by name descending"
                                    />
                                  </Th>
                                  <Th>Task Type</Th>
                                  <Th>Status</Th>
                                  <Th>Actions</Th>
                                </Tr>
                              </Thead>
                              <Tbody>
                                {paginatedServices.map((service) => (
                                  <Tr
                                    key={service.uuid || service.service_id}
                                    _hover={{ bg: tableRowHoverBg, cursor: "pointer" }}
                                    onClick={() => handleViewService(service.serviceId || service.service_id || "")}
                                  >
                                    <Td>
                                      <Text fontSize="sm" noOfLines={1} title={service.name}>{service.name || "N/A"}</Text>
                                    </Td>
                                    <Td>
                                      <Badge
                                        colorScheme={getTaskColor(service.model?.task?.type || service.task?.type || service.task_type)}
                                        fontSize="sm"
                                        p={1}
                                      >
                                        {(service.model?.task?.type || service.task?.type || service.task_type)?.toUpperCase() || "N/A"}
                                      </Badge>
                                    </Td>
                                    <Td>
                                      <Badge
                                        colorScheme={service.isPublished === true ? "green" : "gray"}
                                        fontSize="sm"
                                        p={1}
                                      >
                                        {service.isPublished === true ? "Published" : "Unpublished"}
                                      </Badge>
                                    </Td>
                                    <Td onClick={(e) => e.stopPropagation()}>
                                      <HStack spacing={1}>
                                        <Tooltip label="View" placement="top" hasArrow>
                                          <IconButton
                                            aria-label="View"
                                            icon={<ViewIcon />}
                                            size="sm"
                                            variant="ghost"
                                            colorScheme="blue"
                                            _hover={{ bg: "blue.50" }}
                                            onClick={() => handleViewService(service.serviceId || service.service_id || "")}
                                          />
                                        </Tooltip>
                                        {service.isPublished === true ? (
                                          <Tooltip label="Unpublish" placement="top" hasArrow>
                                            <IconButton
                                              aria-label="Unpublish"
                                              icon={<FaUpload />}
                                              size="sm"
                                              variant="ghost"
                                              colorScheme="red"
                                              _hover={{ bg: "red.50" }}
                                              onClick={() => { setConfirmUnpublishService(service); onUnpublishConfirmOpen(); }}
                                              isLoading={unpublishingServiceUuid === service.uuid}
                                              isDisabled={unpublishingServiceUuid !== null || publishingServiceUuid !== null}
                                            />
                                          </Tooltip>
                                        ) : (
                                          <Tooltip
                                            label={isServiceModelDeprecated(service) ? "This service cannot be published because its associated model is deprecated. Restore the model to ACTIVE before publishing." : "Publish"}
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
                                                onClick={() => { setConfirmPublishService(service); onPublishConfirmOpen(); }}
                                                isLoading={publishingServiceUuid === service.uuid}
                                                isDisabled={
                                                  unpublishingServiceUuid !== null ||
                                                  publishingServiceUuid !== null ||
                                                  isServiceModelDeprecated(service)
                                                }
                                              />
                                            </Box>
                                          </Tooltip>
                                        )}
                                        <Tooltip label="Delete" placement="top" hasArrow>
                                          <IconButton
                                            aria-label="Delete"
                                            icon={<DeleteIcon />}
                                            size="sm"
                                            variant="ghost"
                                            colorScheme="red"
                                            _hover={{ bg: "red.50" }}
                                            onClick={() => handleDeleteClick(service)}
                                            isLoading={deletingServiceUuid === service.uuid}
                                            isDisabled={deletingServiceUuid !== null}
                                          />
                                        </Tooltip>
                                      </HStack>
                                    </Td>
                                  </Tr>
                                ))}
                              </Tbody>
                            </Table>
                          </Box>
                          )}
                        </>
                        )}
                        {!isLoading && filteredServices.length > 0 && (
                          <TablePaginationBar
                            startRow={startRow}
                            endRow={endRow}
                            totalItems={totalServices}
                            page={listPage}
                            totalPages={totalPages}
                            pageSize={listPageSize}
                            pageSizeOptions={PAGE_SIZE_OPTIONS}
                            onPageSizeChange={(value) => {
                              setListPageSize(value);
                              setListPage(1);
                            }}
                            onFirst={() => setListPage(1)}
                            onPrev={() => setListPage((p) => Math.max(1, p - 1))}
                            onNext={() => setListPage((p) => Math.min(totalPages, p + 1))}
                            onLast={() => setListPage(totalPages)}
                            canPrev={listPage > 1}
                            canNext={listPage < totalPages}
                            borderColor={cardBorder}
                            bg={cardBg}
                          />
                        )}
                      </CardBody>
                    </Card>
                  </TabPanel>

                  {/* Create Service Tab */}
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
                              <FormLabel fontWeight="semibold">
                                Service Name{" "}
                                
                              </FormLabel>
                              <Input
                                value={formData.name || ""}
                                onChange={(e) => handleInputChange("name", e.target.value)}
                                placeholder="Enter service name e.g. asr-conformer-gpu"
                                bg="white"
                              />
                              <Text fontSize="xs" color="gray.500" mt={1}>
                                Enter service name e.g. asr-conformer-gpu. Service ID will be auto-generated based on this.
                              </Text>
                            </FormControl>

                            <FormControl isRequired>
                              <FormLabel fontWeight="semibold">
                                Service Description{" "}
                                
                              </FormLabel>
                              <Textarea
                                value={formData.serviceDescription || ""}
                                onChange={(e) => handleInputChange("serviceDescription", e.target.value)}
                                placeholder="Provide a brief description of what this service does"
                                bg="white"
                                rows={4}
                              />
                            </FormControl>

                            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                              <FormControl isRequired>
                                <FormLabel fontWeight="semibold">
                                  Model Name{" "}
                               
                                </FormLabel>
                                <Select
                                  value={formData.modelId || ""}
                                  onChange={(e) => handleModelNameChange(e.target.value)}
                                  placeholder={isLoadingModels ? "Loading models..." : "Select a model"}
                                  bg="white"
                                  isDisabled={isLoadingModels}
                                >
                                  {modelsForDropdown.map((model) => (
                                    <option key={model.modelId || model.model_id} value={model.modelId || model.model_id}>
                                      {model.name || model.modelId || model.model_id}
                                    </option>
                                  ))}
                                </Select>
                                <Text fontSize="xs" color="gray.500" mt={1}>
                                  Select the model to be associated with this service.
                                </Text>
                              </FormControl>

                              <FormControl isRequired>
                              <FormLabel fontWeight="semibold">
                                Endpoint{" "}
                                
                              </FormLabel>
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
                            </SimpleGrid>

                            {/* Auto-generated fields (read-only labels) */}
                            {formData.modelId && (
                              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                                <Box>
                                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                                    Model ID
                                  </Text>
                                  <Box px={3} py={2} bg="gray.50" borderRadius="md" borderWidth="1px" borderColor="gray.200">
                                    <Text fontSize="sm" color="gray.700">{formData.modelId || "—"}</Text>
                                  </Box>
                                  <Text fontSize="xs" color="gray.500" mt={1}>
                                    Auto-generated from selected model
                                  </Text>
                                </Box>
                                <Box>
                                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                                    Task type
                                  </Text>
                                  <Box px={3} py={2} bg="gray.50" borderRadius="md" borderWidth="1px" borderColor="gray.200">
                                    <Text fontSize="sm" color="gray.700">{formData.task_type || "—"}</Text>
                                  </Box>
                                  <Text fontSize="xs" color="gray.500" mt={1}>
                                    Auto-derived from selected model
                                  </Text>
                                </Box>
                              </SimpleGrid>
                            )}

                            <HStack justify="flex-end" spacing={4} pt={4}>
                              <Button
                                type="button"
                                variant="outline"
                                onClick={() => {
                                  setFormData({
                                    name: "",
                                    serviceDescription: "",
                                    publishedOn: Math.floor(Date.now() / 1000),
                                    modelId: "",
                                    modelName: "",
                                    endpoint: "",
                                    task_type: "",
                                    modelVersion: "1.0",
                                  });
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

                  {/* View Service Tab */}
                  {isViewingService && selectedService ? (
                    <TabPanel px={0} pt={6}>
                      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                        <CardHeader>
                          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
                            {selectedService.name || selectedService.serviceId || selectedService.service_id}
                          </Heading>
                        </CardHeader>
                        <CardBody>
                          {!isEditingService && (
                            // View Mode - Display service details
                            <VStack spacing={6} align="stretch">
                              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                                <Box>
                                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                    Service ID
                                  </Text>
                                  <Text fontSize="md">{selectedService.serviceId || selectedService.service_id || "N/A"}</Text>
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
                                <Text fontSize="md">{selectedService.serviceDescription || selectedService.description || "N/A"}</Text>
                              </Box>

                              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                                <Box>
                                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                    Task Type
                                  </Text>
                                  <Badge
                                    colorScheme={getTaskColor(selectedService?.model?.task?.type || selectedService?.task?.type || selectedService.task_type)}
                                    fontSize="sm"
                                    p={2}
                                  >
                                    {(selectedService?.model?.task?.type || selectedService?.task?.type || selectedService.task_type)?.toUpperCase() || "N/A"}
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
                                    {selectedService.isPublished === true ? (
                                      <Tooltip label="Unpublish" placement="top" hasArrow>
                                        <IconButton
                                          aria-label="Unpublish"
                                          icon={<FaUpload />}
                                          size="sm"
                                          colorScheme="red"
                                          variant="outline"
                                          onClick={() => { setConfirmUnpublishService(selectedService); onUnpublishConfirmOpen(); }}
                                          isLoading={unpublishingServiceUuid === selectedService.uuid}
                                          isDisabled={unpublishingServiceUuid !== null || publishingServiceUuid !== null}
                                        />
                                      </Tooltip>
                                    ) : (
                                      <Tooltip
                                        label={isServiceModelDeprecated(selectedService) || selectedServiceModelDeprecated === true ? "This service cannot be published because its associated model is deprecated. Restore the model to ACTIVE before publishing." : "Publish"}
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
                                            onClick={() => { setConfirmPublishService(selectedService); onPublishConfirmOpen(); }}
                                            isLoading={publishingServiceUuid === selectedService.uuid}
                                            isDisabled={
                                              unpublishingServiceUuid !== null ||
                                              publishingServiceUuid !== null ||
                                              isServiceModelDeprecated(selectedService) ||
                                              selectedServiceModelDeprecated === true
                                            }
                                          />
                                        </Box>
                                      </Tooltip>
                                    )}
                                  </HStack>
                                </Box>
                              </SimpleGrid>

                              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                                <Box>
                                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                    Model ID
                                  </Text>
                                  <Text fontSize="md">{selectedService.modelId || selectedService.model_id || "N/A"}</Text>
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

                              {selectedService.uuid && (
                                <Box>
                                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                    UUID
                                  </Text>
                                  <Text fontSize="sm" fontFamily="mono" color="gray.500">
                                    {selectedService.uuid}
                                  </Text>
                                </Box>
                              )}

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
                          {/* Editing disabled for services after creation - edit form removed */}
                        </CardBody>
                      </Card>
                    </TabPanel>
                  ) : null}
                </TabPanels>
              </Tabs>
            </Card>
          </Grid>
        </VStack>
      </ContentLayout>

      <ConfirmDialog
        isOpen={isOpen}
        onClose={onClose}
        onConfirm={handleDeleteConfirm}
        title="Delete service"
        body={
          <>
            Are you sure you want to delete the service{" "}
            <strong>{serviceToDelete?.name || serviceToDelete?.service_id}</strong>?
            This action cannot be undone.
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={deletingServiceUuid === serviceToDelete?.uuid}
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
            <strong>{confirmPublishService?.name || confirmPublishService?.serviceId}</strong>?
            The service will be available for use.
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="green"
        isConfirmLoading={publishingServiceUuid === confirmPublishService?.uuid}
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
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={unpublishingServiceUuid === confirmUnpublishService?.uuid}
        confirmLoadingText="Unpublishing..."
        leastDestructiveRef={cancelUnpublishRef}
      />
    </>
  );
};

export default ServicesManagementPage;


