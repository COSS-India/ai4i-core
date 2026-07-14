// Services Management page with list, create, view, update, and delete functionality

import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  FormControl,
  FormLabel,
  Heading,
  IconButton,
  Input,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  Portal,
  Select,
  Badge,
  Text,
  VStack,
  HStack,
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
import { ViewIcon, DeleteIcon, ChevronDownIcon } from "@chakra-ui/icons";
import { FaUpload, FaDownload } from "react-icons/fa";
import { useRouter } from "next/router";
import { useQueryClient } from "@tanstack/react-query";
import React, {
  useState,
  useEffect,
  useRef,
  useMemo,
  useCallback,
} from "react";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import {
  fetchAllServicesMatchingFilters,
  createService,
  getServiceById,
  updateService,
  deleteService,
  Service,
} from "../services/servicesManagementService";
import { getAllModels, getModelById } from "../services/modelManagementService";
import { fetchTiers } from "../services/tierManagementService";
import type { Tier } from "../types/tierManagement";
import type { ModelDetails } from "../types/platform";
import { useAuth } from "../hooks/useAuth";
import { isRegistryReadOnlyUser } from "../utils/rbac";
import { useSessionExpiry } from "../hooks/useSessionExpiry";
import { showError } from "../utils/errorHandler";
import { showToast } from "../utils/toast";
import ConfirmDialog from "../components/common/ConfirmDialog";
import { useAdminTableSurface } from "../components/common/TableControls";
import AdminDataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../components/common/AdminDataTable";
import { formatModelTaskTypeLabel } from "../config/constants";
import { useInferenceTypes } from "../hooks/useInferenceTypes";

const ServicesManagementPage: React.FC = () => {
  const [services, setServices] = useState<Service[]>([]);
  const [models, setModels] = useState<ModelDetails[]>([]);
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
    modelName: "",
    endpoint: "",
    task_type: "",
    modelSubmissionDate: "",
    modelVersion: "1.0",
    tiers: [],
  });
  const [pricePerUnit, setPricePerUnit] = useState<string>("");
  const [unitSize, setUnitSize] = useState<string>("");
  const [selectedTiers, setSelectedTiers] = useState<string[]>([]);
  const [availableTiers, setAvailableTiers] = useState<Tier[]>([]);
  const [updateFormData, setUpdateFormData] = useState<Partial<Service>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [deletingServiceUuid, setDeletingServiceUuid] = useState<string | null>(
    null,
  );
  const [publishingServiceUuid, setPublishingServiceUuid] = useState<
    string | null
  >(null);
  const [unpublishingServiceUuid, setUnpublishingServiceUuid] = useState<
    string | null
  >(null);
  const [activeTab, setActiveTab] = useState(0);
  const [registryEpoch, setRegistryEpoch] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [filterTaskType, setFilterTaskType] = useState<string>("");
  const { taskTypeNames, unitByTaskType } = useInferenceTypes();
  const [sortBy, setSortBy] = useState<"time" | "name">("time");
  const [nameSortDirection, setNameSortDirection] = useState<"asc" | "desc">(
    "asc",
  );
  const [confirmPublishService, setConfirmPublishService] =
    useState<Service | null>(null);
  const [confirmUnpublishService, setConfirmUnpublishService] =
    useState<Service | null>(null);
  /** When viewing a service, true if its model is deprecated (fetched by modelId); null until we know */
  const [selectedServiceModelDeprecated, setSelectedServiceModelDeprecated] =
    useState<boolean | null>(null);
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
  const { user } = useAuth();
  const isRegistryReadOnly = isRegistryReadOnlyUser(user?.roles);
  const viewTabIndex = isRegistryReadOnly ? 1 : 2;

  const isServiceModelDeprecated = (
    service: Service | null | undefined,
  ): boolean => {
    if (!service) return false;
    const modelVersionStatus =
      (service.model as any)?.versionStatus ??
      (service.model as any)?.version_status ??
      (service as any).versionStatus ??
      (service as any).version_status;
    return (
      typeof modelVersionStatus === "string" &&
      modelVersionStatus.toLowerCase() === "deprecated"
    );
  };

  const formatModelSubmissionDate = (
    value?: string | number | null,
  ): string => {
    if (value == null || value === "") return "";

    let timestampMs: number;
    if (typeof value === "number") {
      timestampMs = value > 1e12 ? value : value * 1000;
    } else if (/^\d+$/.test(value)) {
      const parsed = Number(value);
      timestampMs = parsed > 1e12 ? parsed : parsed * 1000;
    } else {
      timestampMs = new Date(value).getTime();
    }

    if (Number.isNaN(timestampMs)) return "";
    return new Date(timestampMs).toISOString().slice(0, 10);
  };

  // Client-side name filter + sort over the full fetched registry list.
  const registryTableItems = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = q
      ? services.filter((s) => (s.name ?? "").toLowerCase().includes(q))
      : services;
    if (sortBy === "time") return filtered;
    return [...filtered].sort((a, b) => {
      const nameCmp = (a.name ?? "").localeCompare(b.name ?? "", undefined, {
        sensitivity: "base",
      });
      if (nameCmp !== 0)
        return nameSortDirection === "asc" ? nameCmp : -nameCmp;
      return 0;
    });
  }, [services, searchQuery, sortBy, nameSortDirection]);

  const hasActiveFilters =
    filterStatus !== "" || filterTaskType !== "" || searchQuery.trim() !== "";
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
    if (user?.roles?.includes("GUEST") || user?.roles?.includes("USER")) {
      showToast({
        type: "error",
        message: "You do not have access to Services Management.",
      });
      router.push("/");
    }
  }, [user, router]);
  // Model fetched by ID when navigating from a deprecated model's "Create Service" (not in active list)
  const [preselectedModelFromQuery, setPreselectedModelFromQuery] =
    useState<ModelDetails | null>(null);

  // Fetch all services for current task/publish filters (paginated API walk) for client search + pagination
  const fetchServices = useCallback(async () => {
    setIsLoading(true);
    try {
      const isPublishedFilter =
        filterStatus === "published"
          ? true
          : filterStatus === "unpublished"
            ? false
            : undefined;

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

  useEffect(() => {
    fetchServices();
  }, [fetchServices]);

  // Fetch models on component mount (for dropdown)
  useEffect(() => {
    const fetchModels = async () => {
      setIsLoadingModels(true);
      try {
        const fetchedModels = await getAllModels();
        // Filter to only show ACTIVE models
        const activeModels = fetchedModels.filter(
          (model) =>
            model.versionStatus?.toLowerCase() === "active" ||
            !model.versionStatus,
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

  // Fetch tiers for the Create Service form dropdown
  useEffect(() => {
    fetchTiers()
      .then((res) => setAvailableTiers(res.data))
      .catch(() => {});
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
        router.replace(
          { pathname: "/services-management", query: q },
          undefined,
          { shallow: true },
        );
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
    if (!modelId || typeof modelId !== "string") return;

    const runPreselect = async () => {
      // Switch to Create Service tab if specified
      if (tab === "create") {
        setActiveTab(1);
      }

      const inActiveList = models.some(
        (m) => (m.modelId || m.model_id) === modelId,
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
          { shallow: true },
        );
        return;
      }

      // Model not in active list - only add to dropdown if not deprecated (deprecated models must not appear in Create Service)
      if (!inActiveList) {
        try {
          const modelDetails = await getModelById(modelId);
          const isDeprecated =
            modelDetails?.versionStatus?.toLowerCase() === "deprecated";
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
          { shallow: true },
        );
      }
    };

    if (models.length > 0) {
      runPreselect();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.query, models]);

  const { cardBg, borderColor: cardBorder } = useAdminTableSurface();

  // Dropdown options: active models only (no deprecated). Include preselected from query only if not deprecated and not already in list.
  const preselectedNotDeprecated =
    preselectedModelFromQuery &&
    preselectedModelFromQuery.versionStatus?.toLowerCase() !== "deprecated";
  const modelsForDropdown =
    preselectedNotDeprecated &&
    !models.some(
      (m) =>
        (m.modelId || m.model_id) ===
        (preselectedModelFromQuery.modelId ||
          preselectedModelFromQuery.model_id),
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

  const handleInputChange = (field: keyof Service, value: string) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleTaskTypeChange = (taskType: string) => {
    setFormData((prev) => ({
      ...prev,
      task_type: taskType,
      modelId: "",
      modelName: "",
      modelSubmissionDate: "",
      modelVersion: "",
    }));
  };

  const toggleTier = (tier: string) => {
    setSelectedTiers((prev) =>
      prev.includes(tier) ? prev.filter((t) => t !== tier) : [...prev, tier],
    );
  };

  // Handle model name selection and derive model metadata
  const handleModelNameChange = async (modelId: string) => {
    // Check session expiry before fetching model details
    if (!checkSessionExpiry()) return;
    if (modelId) {
      try {
        setIsLoadingModels(true);
        const modelDetails = await getModelById(modelId);

        // Extract model version (required field after migration)
        const modelVersion =
          modelDetails?.version || modelDetails?.modelVersion || "1.0";

        // Extract model submission date (if API returns it)
        const modelSubmissionDate = formatModelSubmissionDate(
          modelDetails?.submittedOn ?? modelDetails?.submitted_on ?? "",
        );

        // Get model name for display
        const modelName =
          modelDetails?.name ||
          modelDetails?.modelId ||
          modelDetails?.model_id ||
          "";

        setFormData((prev) => ({
          ...prev,
          modelId: modelId,
          modelName: modelName,
          modelSubmissionDate: modelSubmissionDate,
          modelVersion: modelVersion,
        }));
      } catch (error: any) {
        console.error("Failed to fetch model details:", error);
        showToast({
          type: "warning",
          message:
            error instanceof Error
              ? error.message
              : "Failed to fetch model details",
        });
      } finally {
        setIsLoadingModels(false);
      }
    } else {
      // Clear model fields if no model selected (keep task_type)
      setFormData((prev) => ({
        ...prev,
        modelId: "",
        modelName: "",
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
      const serviceId = `${formData.name?.toLowerCase().replaceAll(/\s+/g, "-") || "service"}-${timestamp}`;

      // Prepare service data with auto-generated serviceId.
      // Do not send modelSubmissionDate because backend owns this field.
      const serviceFormData: Partial<Service> = { ...formData };
      delete serviceFormData.modelSubmissionDate;
      const tierIds = selectedTiers; // selectedTiers stores tier IDs directly

      const serviceData: Partial<Service> = {
        ...serviceFormData,
        serviceId: serviceId,
        publishedOn: Math.floor(Date.now() / 1000),
        hardwareDescription: "Default hardware",
        api_key: "",
        status: "active",
        costPerUnit: pricePerUnit ? Number(pricePerUnit) : undefined,
        unitSize: unitSize ? Number(unitSize) : undefined,
        tierIds,
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
      queryClient.invalidateQueries({
        queryKey: ["speaker-diarization-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["language-detection-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["language-diarization-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["audioLanguageDetectionServices"],
      });

      showToast({
        type: "success",
        message: "Service has been created successfully.",
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
        modelSubmissionDate: "",
        modelVersion: "1.0",
        tiers: [],
      });
      setPricePerUnit("");
      setUnitSize("");
      setSelectedTiers([]);
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

  const unitType = unitByTaskType[formData.task_type || ""] || "";

  const viewServiceTaskType =
    selectedService?.model?.task?.type ||
    selectedService?.task?.type ||
    selectedService?.task_type ||
    "";
  const viewServiceUnitType =
    unitByTaskType[viewServiceTaskType] ||
    selectedService?.billingUnitType ||
    "";

  const filteredModelsForDropdown = formData.task_type
    ? modelsForDropdown.filter((model) => {
        const modelTaskType =
          model?.task?.type ||
          (model as any).task_type ||
          (model as any).taskType ||
          "";
        return (
          modelTaskType.toLowerCase() === formData.task_type?.toLowerCase()
        );
      })
    : modelsForDropdown;

  const isUnitSizeValid = /^\d+$/.test(unitSize.trim()) && Number(unitSize) > 0;

  const canCreateService =
    !!formData.name?.trim() &&
    !!formData.serviceDescription?.trim() &&
    !!formData.modelId?.trim() &&
    !!formData.endpoint?.trim() &&
    !!formData.task_type?.trim() &&
    !!pricePerUnit.trim() &&
    isUnitSizeValid &&
    selectedTiers.length > 0;

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
      router.replace(
        {
          pathname: "/services-management",
          query: { ...router.query, tab: "2" },
        },
        undefined,
        { shallow: true },
      );
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
      const errorMessage =
        error instanceof Error
          ? error.message
          : "Failed to fetch service details";
      showError(error);
    }
  };

  const handleUpdateService = async (e: React.FormEvent) => {
    e.preventDefault();

    // Check session expiry before updating
    if (!checkSessionExpiry()) return;

    if (!selectedService?.serviceId) {
      showToast({
        type: "error",
        message: "Service ID is required for update",
      });
      return;
    }

    setIsUpdating(true);

    try {
      const updatedService = await updateService({
        ...updateFormData,
        serviceId: selectedService.serviceId,
      });

      // Invalidate all service-related queries to refresh service lists across all pages
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({
        queryKey: ["speaker-diarization-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["language-detection-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["language-diarization-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["audioLanguageDetectionServices"],
      });

      showToast({
        type: "success",
        message: "Service has been updated successfully",
      });

      setSelectedService(updatedService);
      setIsEditingService(false);

      // Refresh services list
      await fetchServices();
    } catch (error: any) {
      const errorMessage =
        error instanceof Error ? error.message : "Failed to update service";
      showError(error);
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
      console.warn(
        "Failed to verify model status before publishing service:",
        e,
      );
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
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({
        queryKey: ["speaker-diarization-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["language-detection-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["language-diarization-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["audioLanguageDetectionServices"],
      });

      // Refresh services list
      await fetchServices();

      // Update selected service if it's the one being published
      if (selectedService?.serviceId === service.serviceId) {
        setSelectedService(updatedService);
      }
    } catch (error: any) {
      const errorMessage =
        error instanceof Error ? error.message : "Failed to publish service";
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
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({
        queryKey: ["speaker-diarization-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["language-detection-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["language-diarization-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["audioLanguageDetectionServices"],
      });

      // Refresh services list
      await fetchServices();

      // Update selected service if it's the one being unpublished
      if (selectedService?.serviceId === service.serviceId) {
        setSelectedService(updatedService);
      }
    } catch (error: any) {
      const errorMessage =
        error instanceof Error ? error.message : "Failed to unpublish service";
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
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({
        queryKey: ["speaker-diarization-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["language-detection-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["language-diarization-services"],
      });
      queryClient.invalidateQueries({
        queryKey: ["audioLanguageDetectionServices"],
      });
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
            colorScheme={getTaskColor(
              service.model?.task?.type ||
                service.task?.type ||
                service.task_type,
            )}
            fontSize="sm"
            p={1}
          >
            {(
              service.model?.task?.type ||
              service.task?.type ||
              service.task_type
            )?.toUpperCase() || "N/A"}
          </Badge>
        ),
      },
      {
        id: "tiers",
        header: "Tiers",
        cell: (service) => {
          const names = service.tierNames;
          if (!names || names.length === 0) {
            return (
              <Text fontSize="sm" color="gray.400">
                —
              </Text>
            );
          }
          return (
            <HStack spacing={1} flexWrap="wrap">
              {names.map((name) => (
                <Badge
                  key={name}
                  colorScheme="gray"
                  fontSize="xs"
                  px={2}
                  py={0.5}
                >
                  {name}
                </Badge>
              ))}
            </HStack>
          );
        },
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
            {service.createdAt
              ? new Date(service.createdAt).toLocaleDateString()
              : "N/A"}
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
                  handleViewService(
                    service.serviceId || service.service_id || "",
                  )
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
                      unpublishingServiceUuid !== null ||
                      publishingServiceUuid !== null
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

  return (
    <>
      <Head>
        <title>Services Management - AI4I Platform</title>
        <meta name="description" content="Manage and configure services" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full">
          <ManagementPageHeader
            title="Services Management"
            description={
              isRegistryReadOnly
                ? "View services in the registry (read-only)"
                : "Manage and configure services"
            }
          />

          <Grid gap={8} w="full" mx="auto">
            <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px">
              <Tabs
                colorScheme="blue"
                variant="enclosed"
                index={activeTab}
                onChange={(index) => {
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
                  router.replace(
                    { pathname: "/services-management", query: q },
                    undefined,
                    { shallow: true },
                  );
                }}
              >
                <TabList>
                  <Tab fontWeight="semibold">Service Registry</Tab>
                  {!isRegistryReadOnly && (
                    <Tab fontWeight="semibold">Create Service</Tab>
                  )}
                  {isViewingService && (
                    <Tab fontWeight="semibold">View Service</Tab>
                  )}
                </TabList>

                <TabPanels>
                  {/* Service Registry Tab */}
                  <TabPanel px={0} pt={6}>
                    <Card
                      bg={cardBg}
                      borderColor={cardBorder}
                      borderWidth="1px"
                      boxShadow="none"
                    >
                      <CardHeader>
                        <Heading
                          size="md"
                          color="gray.700"
                          userSelect="none"
                          cursor="default"
                        >
                          Service Registry
                        </Heading>
                      </CardHeader>
                      <CardBody>
                        <AdminDataTable
                          key={`${filterStatus}-${filterTaskType}-${registryEpoch}`}
                          items={registryTableItems}
                          columns={serviceColumns}
                          getRowKey={(service) =>
                            service.serviceId || service.service_id || ""
                          }
                          onRowClick={(service) =>
                            handleViewService(
                              service.serviceId || service.service_id || "",
                            )
                          }
                          paginate="client"
                          pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
                          isLoading={isLoading}
                          loadingMessage="Loading services..."
                          emptyMessage="No services in the registry yet."
                          noResultsMessage="No results found. Try adjusting your search or filters."
                          unfilteredCount={services.length}
                          hasActiveFilters={hasActiveFilters}
                          onClearFilters={clearAllFilters}
                          filters={
                            <VStack align="stretch" spacing={3} w="full">
                              <HStack
                                flexWrap="wrap"
                                spacing={3}
                                align="flex-end"
                              >
                                <TableSearchField
                                  label="Search"
                                  value={searchQuery}
                                  onChange={setSearchQuery}
                                  placeholder="Search by service name..."
                                  formControlProps={{
                                    w: { base: "full", md: "280px" },
                                  }}
                                />
                                <TableSelectField
                                  label="Status"
                                  value={filterStatus}
                                  onChange={setFilterStatus}
                                  formControlProps={{
                                    w: { base: "full", sm: "140px" },
                                  }}
                                >
                                  <option value="">All</option>
                                  <option value="published">Published</option>
                                  <option value="unpublished">
                                    Unpublished
                                  </option>
                                </TableSelectField>
                                <TableSelectField
                                  label="Model Task Type"
                                  value={filterTaskType}
                                  onChange={setFilterTaskType}
                                  formControlProps={{
                                    w: { base: "full", sm: "160px" },
                                  }}
                                >
                                  <option value="">All</option>
                                  {taskTypeNames?.map((t) => (
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
                                      {filterStatus === "published"
                                        ? "Published"
                                        : "Unpublished"}{" "}
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
                                      Model Task Type:{" "}
                                      {formatModelTaskTypeLabel(filterTaskType)}{" "}
                                      ×
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

                  {/* Create Service Tab */}
                  {!isRegistryReadOnly && (
                    <TabPanel px={0} pt={6}>
                      <Card
                        bg={cardBg}
                        borderColor={cardBorder}
                        borderWidth="1px"
                        boxShadow="none"
                      >
                        <CardHeader>
                          <Heading
                            size="md"
                            color="gray.700"
                            userSelect="none"
                            cursor="default"
                          >
                            Create New Service
                          </Heading>
                        </CardHeader>
                        <CardBody>
                          <form onSubmit={handleSubmit}>
                            <VStack spacing={6} align="stretch">
                              {/* Service Name */}
                              <FormControl isRequired>
                                <FormLabel fontWeight="semibold">
                                  Service Name
                                </FormLabel>
                                <Input
                                  value={formData.name || ""}
                                  onChange={(e) =>
                                    handleInputChange("name", e.target.value)
                                  }
                                  placeholder="Enter service name e.g. asr-conformer-gpu"
                                  bg="white"
                                />
                                <Text fontSize="xs" color="gray.500" mt={1}>
                                  Enter service name e.g. asr-conformer-gpu.
                                  Service ID will be auto-generated based on
                                  this.
                                </Text>
                              </FormControl>

                              {/* Service Description */}
                              <FormControl isRequired>
                                <FormLabel fontWeight="semibold">
                                  Service Description
                                </FormLabel>
                                <Textarea
                                  value={formData.serviceDescription || ""}
                                  onChange={(e) =>
                                    handleInputChange(
                                      "serviceDescription",
                                      e.target.value,
                                    )
                                  }
                                  placeholder="Provide a brief description of what this service does"
                                  bg="white"
                                  rows={4}
                                />
                              </FormControl>

                              {/* Endpoint */}
                              <FormControl isRequired>
                                <FormLabel fontWeight="semibold">
                                  Endpoint
                                </FormLabel>
                                <Input
                                  value={formData.endpoint || ""}
                                  onChange={(e) =>
                                    handleInputChange(
                                      "endpoint",
                                      e.target.value,
                                    )
                                  }
                                  placeholder="Enter endpoint URL, e.g. http://localhost:8088"
                                  bg="white"
                                />
                                <Text fontSize="xs" color="gray.500" mt={1}>
                                  Enter the full HTTP endpoint where this
                                  service is hosted.
                                </Text>
                              </FormControl>

                              {/* Model Task Type | Model Name */}
                              <SimpleGrid
                                columns={{ base: 1, md: 2 }}
                                spacing={4}
                              >
                                <FormControl isRequired>
                                  <FormLabel fontWeight="semibold">
                                    Model Task Type
                                  </FormLabel>
                                  <Select
                                    value={formData.task_type || ""}
                                    onChange={(e) =>
                                      handleTaskTypeChange(e.target.value)
                                    }
                                    placeholder="Select a task type"
                                    bg="white"
                                  >
                                    {taskTypeNames?.map((t) => (
                                      <option key={t} value={t}>
                                        {formatModelTaskTypeLabel(t)}
                                      </option>
                                    ))}
                                  </Select>
                                </FormControl>

                                <FormControl isRequired>
                                  <FormLabel fontWeight="semibold">
                                    Model Name
                                  </FormLabel>
                                  <Select
                                    value={formData.modelId || ""}
                                    onChange={(e) =>
                                      handleModelNameChange(e.target.value)
                                    }
                                    placeholder={
                                      isLoadingModels
                                        ? "Loading models..."
                                        : !formData.task_type
                                          ? "Select a task type first"
                                          : "Select a model"
                                    }
                                    bg="white"
                                    isDisabled={
                                      isLoadingModels || !formData.task_type
                                    }
                                  >
                                    {filteredModelsForDropdown.map((model) => (
                                      <option
                                        key={model.modelId || model.model_id}
                                        value={model.modelId || model.model_id}
                                      >
                                        {model.name ||
                                          model.modelId ||
                                          model.model_id}
                                      </option>
                                    ))}
                                  </Select>
                                </FormControl>
                              </SimpleGrid>

                              {/* Unit type | Price per Unit | Currency | Tier */}
                              <SimpleGrid
                                columns={{ base: 2, md: 4 }}
                                spacing={4}
                              >
                                <FormControl>
                                  <FormLabel fontWeight="semibold">
                                    Unit type
                                  </FormLabel>
                                  <Input
                                    value={unitType}
                                    isReadOnly
                                    bg="gray.50"
                                    placeholder="—"
                                  />
                                </FormControl>

                                <FormControl isRequired>
                                  <FormLabel fontWeight="semibold">
                                    Price per Unit
                                  </FormLabel>
                                  <Input
                                    value={pricePerUnit}
                                    onChange={(e) =>
                                      setPricePerUnit(e.target.value)
                                    }
                                    placeholder="e.g. 600"
                                    type="number"
                                    min={0}
                                    bg="white"
                                  />
                                </FormControl>

                                <FormControl>
                                  <FormLabel fontWeight="semibold">
                                    Currency
                                  </FormLabel>
                                  <Input value="INR" isReadOnly bg="gray.50" />
                                </FormControl>

                                <FormControl>
                                  <FormLabel fontWeight="semibold">
                                    Tier{" "}
                                    <Box as="span" color="red.500">
                                      *
                                    </Box>
                                  </FormLabel>
                                  <Menu closeOnSelect={false} matchWidth>
                                    <MenuButton
                                      as={Button}
                                      type="button"
                                      rightIcon={<ChevronDownIcon />}
                                      w="full"
                                      maxW="full"
                                      textAlign="left"
                                      fontWeight="normal"
                                      variant="outline"
                                      bg="white"
                                      borderColor="inherit"
                                      _hover={{ borderColor: "gray.300" }}
                                      fontSize="sm"
                                      justifyContent="space-between"
                                    >
                                      <Text
                                        as="span"
                                        isTruncated
                                        display="block"
                                        minW={0}
                                      >
                                        {selectedTiers.length > 0
                                          ? selectedTiers
                                              .map(
                                                (id) =>
                                                  availableTiers.find(
                                                    (t) => t.id === id,
                                                  )?.name ?? id,
                                              )
                                              .join(", ")
                                          : "Select Tiers"}
                                      </Text>
                                    </MenuButton>
                                    <Portal>
                                      <MenuList maxH="280px" overflowY="auto">
                                        {availableTiers.map((tier) => (
                                          <MenuItem
                                            key={tier.id}
                                            onClick={() => toggleTier(tier.id)}
                                            closeOnSelect={false}
                                          >
                                            <Checkbox
                                              isChecked={selectedTiers.includes(
                                                tier.id,
                                              )}
                                              onChange={() =>
                                                toggleTier(tier.id)
                                              }
                                              onClick={(e) =>
                                                e.stopPropagation()
                                              }
                                              mr={2}
                                            />
                                            {tier.name}
                                          </MenuItem>
                                        ))}
                                      </MenuList>
                                    </Portal>
                                  </Menu>
                                </FormControl>
                              </SimpleGrid>

                              {/* Unit Size | Model ID | Model Submission Date */}
                              <Grid
                                templateColumns={{
                                  base: "1fr",
                                  md: "1fr 1.5fr 1.5fr",
                                }}
                                gap={4}
                              >
                                <FormControl isRequired>
                                  <FormLabel fontWeight="semibold">
                                    Unit Size
                                  </FormLabel>
                                  <Input
                                    value={unitSize}
                                    onChange={(e) =>
                                      setUnitSize(e.target.value)
                                    }
                                    placeholder="e.g. 100"
                                    type="number"
                                    min={1}
                                    step={1}
                                    bg="white"
                                  />
                                </FormControl>

                                <FormControl isRequired>
                                  <FormLabel fontWeight="semibold">
                                    Model ID
                                  </FormLabel>
                                  <Input
                                    value={formData.modelId || ""}
                                    bg={
                                      isCreateFormModelSelected
                                        ? "gray.50"
                                        : "white"
                                    }
                                    isReadOnly
                                    placeholder="Select a model above"
                                  />
                                </FormControl>

                                <FormControl>
                                  <FormLabel fontWeight="semibold">
                                    Model Submission Date
                                  </FormLabel>
                                  <Input
                                    type="date"
                                    value={
                                      (formData.modelSubmissionDate as string) ||
                                      ""
                                    }
                                    bg={
                                      isCreateFormModelSelected
                                        ? "gray.50"
                                        : "white"
                                    }
                                    isReadOnly
                                  />
                                </FormControl>
                              </Grid>

                              <HStack justify="flex-end" spacing={4} pt={4}>
                                <Button
                                  type="button"
                                  variant="outline"
                                  onClick={() => {
                                    setFormData({
                                      name: "",
                                      serviceDescription: "",
                                      publishedOn: Math.floor(
                                        Date.now() / 1000,
                                      ),
                                      modelId: "",
                                      modelName: "",
                                      endpoint: "",
                                      task_type: "",
                                      modelSubmissionDate: "",
                                      modelVersion: "1.0",
                                      tiers: [],
                                    });
                                    setPricePerUnit("");
                                    setUnitSize("");
                                    setSelectedTiers([]);
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
                  )}

                  {/* View Service Tab */}
                  {isViewingService && selectedService ? (
                    <TabPanel px={0} pt={6}>
                      <Card
                        bg={cardBg}
                        borderColor={cardBorder}
                        borderWidth="1px"
                        boxShadow="none"
                      >
                        <CardHeader>
                          <Heading
                            size="md"
                            color="gray.700"
                            userSelect="none"
                            cursor="default"
                          >
                            {selectedService.name ||
                              selectedService.serviceId ||
                              selectedService.service_id}
                          </Heading>
                        </CardHeader>
                        <CardBody>
                          {!isEditingService && (
                            // View Mode - Display service details
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
                              <SimpleGrid
                                columns={{ base: 1, md: 2 }}
                                spacing={4}
                              >
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Service ID
                                  </Text>
                                  <Text fontSize="md">
                                    {selectedService.serviceId ||
                                      selectedService.service_id ||
                                      "N/A"}
                                  </Text>
                                </Box>
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Name
                                  </Text>
                                  <Text fontSize="md">
                                    {selectedService.name || "N/A"}
                                  </Text>
                                </Box>
                              </SimpleGrid>

                              <Box>
                                <Text
                                  fontWeight="bold"
                                  color="gray.600"
                                  fontSize="sm"
                                  mb={1}
                                >
                                  Description
                                </Text>
                                <Text fontSize="md">
                                  {selectedService.serviceDescription ||
                                    selectedService.description ||
                                    "N/A"}
                                </Text>
                              </Box>

                              <SimpleGrid
                                columns={{ base: 1, md: 2 }}
                                spacing={4}
                              >
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Model Task Type
                                  </Text>
                                  <Badge
                                    colorScheme={getTaskColor(
                                      selectedService?.model?.task?.type ||
                                        selectedService?.task?.type ||
                                        selectedService.task_type,
                                    )}
                                    fontSize="sm"
                                    p={2}
                                  >
                                    {(
                                      selectedService?.model?.task?.type ||
                                      selectedService?.task?.type ||
                                      selectedService.task_type
                                    )?.toUpperCase() || "N/A"}
                                  </Badge>
                                </Box>
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Status (Publish/Unpublish)
                                  </Text>
                                  <HStack
                                    spacing={2}
                                    align="center"
                                    flexWrap="wrap"
                                  >
                                    <Badge
                                      colorScheme={
                                        selectedService.isPublished === true
                                          ? "green"
                                          : "gray"
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
                                        <Tooltip
                                          label="Unpublish"
                                          placement="top"
                                          hasArrow
                                        >
                                          <IconButton
                                            aria-label="Unpublish"
                                            icon={<FaDownload />}
                                            size="sm"
                                            colorScheme="red"
                                            variant="outline"
                                            onClick={() => {
                                              setConfirmUnpublishService(
                                                selectedService,
                                              );
                                              onUnpublishConfirmOpen();
                                            }}
                                            isLoading={
                                              unpublishingServiceUuid ===
                                              selectedService.serviceId
                                            }
                                            isDisabled={
                                              unpublishingServiceUuid !==
                                                null ||
                                              publishingServiceUuid !== null
                                            }
                                          />
                                        </Tooltip>
                                      ) : (
                                        <Tooltip
                                          label={
                                            isServiceModelDeprecated(
                                              selectedService,
                                            ) ||
                                            selectedServiceModelDeprecated ===
                                              true
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
                                              colorScheme="green"
                                              variant="outline"
                                              onClick={() => {
                                                setConfirmPublishService(
                                                  selectedService,
                                                );
                                                onPublishConfirmOpen();
                                              }}
                                              isLoading={
                                                publishingServiceUuid ===
                                                selectedService.serviceId
                                              }
                                              isDisabled={
                                                unpublishingServiceUuid !==
                                                  null ||
                                                publishingServiceUuid !==
                                                  null ||
                                                isServiceModelDeprecated(
                                                  selectedService,
                                                ) ||
                                                selectedServiceModelDeprecated ===
                                                  true
                                              }
                                            />
                                          </Box>
                                        </Tooltip>
                                      ))}
                                  </HStack>
                                </Box>
                              </SimpleGrid>

                              <SimpleGrid
                                columns={{ base: 1, md: 2 }}
                                spacing={4}
                              >
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Model ID
                                  </Text>
                                  <Text fontSize="md">
                                    {selectedService.modelId ||
                                      selectedService.model_id ||
                                      "N/A"}
                                  </Text>
                                </Box>
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Endpoint
                                  </Text>
                                  <Text fontSize="md" wordBreak="break-all">
                                    {selectedService.endpoint ||
                                      selectedService.endpoint_url ||
                                      "N/A"}
                                  </Text>
                                </Box>
                              </SimpleGrid>

                              <SimpleGrid
                                columns={{ base: 1, md: 2 }}
                                spacing={4}
                              >
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Hardware Description
                                  </Text>
                                  <Text fontSize="md">
                                    {selectedService.hardwareDescription ||
                                      "N/A"}
                                  </Text>
                                </Box>
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
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

                              <SimpleGrid
                                columns={{ base: 1, md: 2 }}
                                spacing={4}
                              >
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Unit Type
                                  </Text>
                                  <Text fontSize="md">
                                    {viewServiceUnitType || "N/A"}
                                  </Text>
                                </Box>
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Price per Unit
                                  </Text>
                                  <Text fontSize="md">
                                    {selectedService.costPerUnit ?? "N/A"}
                                  </Text>
                                </Box>
                              </SimpleGrid>

                              <SimpleGrid
                                columns={{ base: 1, md: 2 }}
                                spacing={4}
                              >
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Currency
                                  </Text>
                                  <Text fontSize="md">INR</Text>
                                </Box>
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Unit Size
                                  </Text>
                                  <Text fontSize="md">
                                    {selectedService.unitSize ?? "N/A"}
                                  </Text>
                                </Box>
                              </SimpleGrid>

                              <Box>
                                <Text
                                  fontWeight="bold"
                                  color="gray.600"
                                  fontSize="sm"
                                  mb={1}
                                >
                                  Tier
                                </Text>
                                {selectedService.tierNames &&
                                selectedService.tierNames.length > 0 ? (
                                  <HStack spacing={1} flexWrap="wrap">
                                    {selectedService.tierNames.map((name) => (
                                      <Badge
                                        key={name}
                                        colorScheme="gray"
                                        fontSize="xs"
                                        px={2}
                                        py={0.5}
                                      >
                                        {name}
                                      </Badge>
                                    ))}
                                  </HStack>
                                ) : (
                                  <Text fontSize="md">N/A</Text>
                                )}
                              </Box>

                              {selectedService.created_at && (
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Created At
                                  </Text>
                                  <Text fontSize="md">
                                    {new Date(
                                      selectedService.created_at,
                                    ).toLocaleString()}
                                  </Text>
                                </Box>
                              )}

                              {selectedService.updated_at && (
                                <Box>
                                  <Text
                                    fontWeight="bold"
                                    color="gray.600"
                                    fontSize="sm"
                                    mb={1}
                                  >
                                    Updated At
                                  </Text>
                                  <Text fontSize="md">
                                    {new Date(
                                      selectedService.updated_at,
                                    ).toLocaleString()}
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
            <strong>
              {serviceToDelete?.name || serviceToDelete?.service_id}
            </strong>
            ? This action cannot be undone.
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
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
            <strong>
              {confirmPublishService?.name || confirmPublishService?.serviceId}
            </strong>
            ? The service will be available for use.
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="green"
        isConfirmLoading={
          publishingServiceUuid === confirmPublishService?.serviceId
        }
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
            <strong>
              {confirmUnpublishService?.name ||
                confirmUnpublishService?.serviceId}
            </strong>
            ? The service will no longer be available for use.
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={
          unpublishingServiceUuid === confirmUnpublishService?.serviceId
        }
        confirmLoadingText="Unpublishing..."
        leastDestructiveRef={cancelUnpublishRef}
      />
    </>
  );
};

export default ServicesManagementPage;
