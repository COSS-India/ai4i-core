// All state, data fetching, and mutations for the Services Management page
// (Service Registry / Create-Edit Service / View Service tabs).
import { useDisclosure } from "@chakra-ui/react";
import { useRouter } from "next/router";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchAllServicesMatchingFilters,
  fetchExistingServiceIds,
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
import { useAuth } from "./useAuth";
import { isRegistryReadOnlyUser } from "../utils/rbac";
import { useSessionExpiry } from "./useSessionExpiry";
import { showError } from "../utils/errorHandler";
import { showToast } from "../utils/toast";
import { useInferenceTypes } from "./useInferenceTypes";

/** Query keys of per-task service lists that must refresh after registry mutations. */
const SERVICE_QUERY_KEYS = [
  "asr-services",
  "tts-services",
  "ocr-services",
  "nmt-services",
  "nerServices",
  "llm-services",
  "transliteration-services",
  "speaker-diarization-services",
  "language-detection-services",
  "language-diarization-services",
  "audioLanguageDetectionServices",
];

const emptyServiceForm = (): Partial<Service> => ({
  name: "",
  serviceId: "",
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

const formatModelSubmissionDate = (value?: string | number | null): string => {
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

export function useServicesManagement() {
  const [services, setServices] = useState<Service[]>([]);
  const [models, setModels] = useState<ModelDetails[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [isViewingService, setIsViewingService] = useState(false);
  /** Service being edited in the Create Service tab; null = create mode */
  const [editingService, setEditingService] = useState<Service | null>(null);
  const [formData, setFormData] = useState<Partial<Service>>(emptyServiceForm);
  /** All existing serviceIds (unfiltered) — used to flag duplicates in the create form */
  const [existingServiceIds, setExistingServiceIds] = useState<string[]>([]);
  const [pricePerUnit, setPricePerUnit] = useState<string>("");
  const [unitSize, setUnitSize] = useState<string>("");
  const [selectedTiers, setSelectedTiers] = useState<string[]>([]);
  const [availableTiers, setAvailableTiers] = useState<Tier[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
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
  const fetchServices = useCallback(async (options?: { silent?: boolean }) => {
    if (!options?.silent) setIsLoading(true);
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
      if (!options?.silent) setIsLoading(false);
    }
  }, [filterTaskType, filterStatus]);

  /**
   * Keep registry + detail UI in sync after publish/unpublish.
   * PATCH /services only returns `{ serviceId }`, so callers must not replace
   * local state with that response. Prefer an optimistic patch, optionally
   * replaced by a full `getServiceById` payload when available.
   */
  const syncServicePublishStatus = useCallback(
    (serviceId: string, isPublished: boolean, freshService?: Service) => {
      const apply = (s: Service): Service => {
        if (s.serviceId !== serviceId) return s;
        if (freshService) return freshService;
        return {
          ...s,
          isPublished,
          ...(isPublished
            ? { publishedOn: Math.floor(Date.now() / 1000) }
            : {}),
        };
      };

      setServices((prev) => {
        const next = prev.map(apply);
        if (filterStatus === "published") {
          return next.filter((s) => s.isPublished === true);
        }
        if (filterStatus === "unpublished") {
          return next.filter((s) => s.isPublished !== true);
        }
        return next;
      });

      setSelectedService((prev) =>
        prev?.serviceId === serviceId ? apply(prev) : prev,
      );
    },
    [filterStatus],
  );

  useEffect(() => {
    fetchServices();
  }, [fetchServices]);

  // Fetch all existing serviceIds (unfiltered) for duplicate detection in the create form
  const loadExistingServiceIds = useCallback(async () => {
    try {
      const ids = await fetchExistingServiceIds();
      setExistingServiceIds(ids);
    } catch (error) {
      console.error("Failed to fetch existing service ids:", error);
    }
  }, []);

  useEffect(() => {
    loadExistingServiceIds();
  }, [loadExistingServiceIds]);

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
      if (
        router.query.tab ||
        router.query.modelId ||
        router.query.editServiceId
      ) {
        const q = { ...router.query } as Record<string, string>;
        delete q.tab;
        delete q.modelId;
        delete q.editServiceId;
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

  // Handle ?editServiceId= deep link (e.g. page refresh while editing a service)
  useEffect(() => {
    if (isRegistryReadOnly) return;
    const { editServiceId } = router.query;
    if (!editServiceId || typeof editServiceId !== "string") return;
    const currentEditId =
      editingService?.serviceId || editingService?.service_id;
    if (currentEditId === editServiceId) return;
    handleEditService(editServiceId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.query.editServiceId, isRegistryReadOnly]);

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

  // Invalidate all service-related queries to refresh service lists across all pages
  const invalidateServiceQueries = useCallback(() => {
    SERVICE_QUERY_KEYS.forEach((key) =>
      queryClient.invalidateQueries({ queryKey: [key] }),
    );
  }, [queryClient]);

  const resetCreateForm = () => {
    setFormData(emptyServiceForm());
    setPricePerUnit("");
    setUnitSize("");
    setSelectedTiers([]);
    setPreselectedModelFromQuery(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Check session expiry before submitting
    if (!checkSessionExpiry()) return;

    setIsSubmitting(true);

    try {
      if (editingService) {
        // Edit mode: PATCH only the fields the edit form allows changing
        await updateService({
          serviceId: editingService.serviceId || editingService.service_id,
          serviceDescription: formData.serviceDescription,
          endpoint: formData.endpoint,
          task_type: formData.task_type,
          costPerUnit: pricePerUnit ? Number(pricePerUnit) : undefined,
          unitSize: unitSize ? Number(unitSize) : undefined,
          tierIds: selectedTiers,
        });

        showToast({
          type: "success",
          message: "Service has been updated successfully.",
        });
      } else {
        // Use the user-provided serviceId.
        const serviceId = formData.serviceId?.trim() || "";

        // Prepare service data with the user-provided serviceId.
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

        await createService(serviceData);

        showToast({
          type: "success",
          message: "Service has been created successfully.",
        });
      }

      invalidateServiceQueries();

      // Reset form and leave edit mode
      setEditingService(null);
      resetCreateForm();

      await fetchServices();
      await loadExistingServiceIds();
      setRegistryEpoch((e) => e + 1);

      // Switch to list tab and clear tab/edit query params
      setActiveTab(0);
      router.replace(
        { pathname: "/services-management", query: {} },
        undefined,
        { shallow: true },
      );
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

  // Duplicate serviceId check — only in create mode (serviceId is read-only when editing)
  const serviceIdExists =
    !editingService &&
    !!formData.serviceId?.trim() &&
    existingServiceIds.includes(formData.serviceId.trim());
  const serviceIdError = serviceIdExists ? "Service Id already exists" : null;

  const canCreateService =
    !!formData.name?.trim() &&
    !!formData.serviceId?.trim() &&
    !serviceIdExists &&
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
      showError(error);
    }
  };

  /**
   * Load a service into the Create Service tab in edit mode, pre-populating
   * the shared form state with the service's current values.
   */
  const handleEditService = async (serviceId: string) => {
    // Check session expiry before loading the service into the edit form
    if (!checkSessionExpiry()) return;
    try {
      const service = await getServiceById(serviceId);
      const modelId = service.modelId || service.model_id || "";
      setFormData({
        name: service.name || "",
        serviceId: service.serviceId || service.service_id || "",
        serviceDescription:
          service.serviceDescription || service.description || "",
        publishedOn: service.publishedOn,
        modelId,
        modelName: service.model?.name || modelId,
        endpoint: service.endpoint || service.endpoint_url || "",
        task_type:
          service.model?.task?.type ||
          service.task?.type ||
          service.task_type ||
          "",
        modelSubmissionDate: "",
        modelVersion: service.modelVersion || service.model_version || "1.0",
      });
      setPricePerUnit(
        service.costPerUnit != null ? String(service.costPerUnit) : "",
      );
      setUnitSize(service.unitSize != null ? String(service.unitSize) : "");
      // Prefer tier IDs; fall back to mapping tier names via the fetched tier list
      const tierIds = service.tierIds?.length
        ? service.tierIds
        : (service.tierNames ?? service.tiers ?? [])
            .map((name) => availableTiers.find((t) => t.name === name)?.id)
            .filter((id): id is string => !!id);
      setSelectedTiers(tierIds);
      setEditingService(service);
      // Fill model name/submission date from the model record (read-only display)
      if (modelId) {
        handleModelNameChange(modelId);
      }
      setActiveTab(1);
      router.replace(
        {
          pathname: "/services-management",
          query: { tab: "1", editServiceId: serviceId },
        },
        undefined,
        { shallow: true },
      );
    } catch (error: any) {
      showError(error);
    }
  };

  const cancelEdit = () => {
    setEditingService(null);
    resetCreateForm();
    setActiveTab(0);
    router.replace({ pathname: "/services-management", query: {} }, undefined, {
      shallow: true,
    });
  };

  const handleCancelForm = () => {
    if (editingService) {
      cancelEdit();
    } else {
      resetCreateForm();
    }
  };

  const handleTabChange = (index: number) => {
    if (isRegistryReadOnly && index === 1) return;
    setActiveTab(index);
    if (index !== viewTabIndex) {
      setIsViewingService(false);
      setSelectedService(null);
      setSelectedServiceModelDeprecated(null);
    }
    if (index !== 1 && editingService) {
      setEditingService(null);
      resetCreateForm();
    }
    const q = { ...router.query } as Record<string, string>;
    if (index === 0) delete q.tab;
    else q.tab = String(index);
    if (index !== 1) delete q.editServiceId;
    router.replace({ pathname: "/services-management", query: q }, undefined, {
      shallow: true,
    });
  };

  const requestPublish = (service: Service) => {
    setConfirmPublishService(service);
    onPublishConfirmOpen();
  };

  const requestUnpublish = (service: Service) => {
    setConfirmUnpublishService(service);
    onUnpublishConfirmOpen();
  };

  const closePublishConfirm = () => {
    onPublishConfirmClose();
    setConfirmPublishService(null);
  };

  const closeUnpublishConfirm = () => {
    onUnpublishConfirmClose();
    setConfirmUnpublishService(null);
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
      // PATCH returns only `{ serviceId }` — do not treat it as a full Service
      await updateService({
        serviceId: service.serviceId,
        isPublished: true,
      });

      // Immediate UI update (list + detail) before any refetch
      syncServicePublishStatus(service.serviceId, true);

      showToast({
        type: "success",
        message: `${service.name || service.serviceId} has been published successfully.`,
      });

      invalidateServiceQueries();

      // Authoritative refresh for the mutated service, then silent list sync
      try {
        const fresh = await getServiceById(service.serviceId);
        syncServicePublishStatus(service.serviceId, true, fresh);
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn("Failed to refresh service after publish:", e);
      }

      void fetchServices({ silent: true });
    } catch (error: any) {
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
      // PATCH returns only `{ serviceId }` — do not treat it as a full Service
      await updateService({
        serviceId: service.serviceId,
        isPublished: false,
      });

      // Immediate UI update (list + detail) before any refetch
      syncServicePublishStatus(service.serviceId, false);

      showToast({
        type: "success",
        message: `${service.name || service.serviceId} has been unpublished successfully.`,
      });

      invalidateServiceQueries();

      // Authoritative refresh for the mutated service, then silent list sync
      try {
        const fresh = await getServiceById(service.serviceId);
        syncServicePublishStatus(service.serviceId, false, fresh);
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn("Failed to refresh service after unpublish:", e);
      }

      void fetchServices({ silent: true });
    } catch (error: any) {
      showError(error);
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
      invalidateServiceQueries();
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

  const handleSortNameAsc = () => {
    setSortBy("name");
    setNameSortDirection("asc");
  };

  const handleSortNameDesc = () => {
    setSortBy("name");
    setNameSortDirection("desc");
  };

  return {
    isRegistryReadOnly,
    viewTabIndex,
    activeTab,
    handleTabChange,

    // Registry tab
    registryTableItems,
    totalServicesCount: services.length,
    isLoading,
    tableKey: `${filterStatus}-${filterTaskType}-${registryEpoch}`,
    searchQuery,
    setSearchQuery,
    filterStatus,
    setFilterStatus,
    filterTaskType,
    setFilterTaskType,
    taskTypeNames,
    hasActiveFilters,
    clearAllFilters,
    nameSortDirection,
    handleSortNameAsc,
    handleSortNameDesc,
    handleViewService,
    handleEditService,
    handleDeleteClick,
    deletingServiceUuid,

    // Create/Edit form tab
    editingService,
    formData,
    handleInputChange,
    handleTaskTypeChange,
    handleModelNameChange,
    isLoadingModels,
    filteredModelsForDropdown,
    unitType,
    pricePerUnit,
    setPricePerUnit,
    unitSize,
    setUnitSize,
    selectedTiers,
    toggleTier,
    availableTiers,
    isCreateFormModelSelected,
    canCreateService,
    serviceIdError,
    isSubmitting,
    handleSubmit,
    handleCancelForm,

    // View tab
    selectedService,
    isViewingService,
    selectedServiceModelDeprecated,
    viewServiceUnitType,
    unpublishingServiceUuid,
    publishingServiceUuid,
    requestPublish,
    requestUnpublish,

    // Delete confirm dialog
    isOpen,
    onClose,
    handleDeleteConfirm,
    serviceToDelete,
    cancelRef,

    // Publish confirm dialog
    isPublishConfirmOpen,
    closePublishConfirm,
    handlePublishConfirm,
    confirmPublishService,
    cancelPublishRef,

    // Unpublish confirm dialog
    isUnpublishConfirmOpen,
    closeUnpublishConfirm,
    handleUnpublishConfirm,
    confirmUnpublishService,
    cancelUnpublishRef,
  };
}
