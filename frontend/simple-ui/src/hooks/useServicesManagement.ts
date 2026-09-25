// All state, data fetching, and mutations for the Services Management page
// (Service Registry / Create-Edit Service / View Service tabs).
import { useDisclosure } from "@chakra-ui/react";
import { useRouter } from "next/router";
import { isFormReturnHref } from "../components/common/FormPage";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDeferredColumnSort } from "../utils/tableSort";
import { resolveTaskType } from "../utils/platformService";
import {
  fetchAllServicesMatchingFilters,
  listServices,
  createService,
  getServiceById,
  updateService,
  deleteService,
  SERVICES_ALL_QUERY_KEY,
  SERVICES_ALL_STALE_MS,
  sanitizeService,
  resolveMaskedAuthToken,
  Service,
} from "../services/servicesManagementService";
import {
  getAllModels,
  getModelById,
  MODELS_ALL_QUERY_KEY,
  MODELS_ALL_STALE_MS,
} from "../services/modelManagementService";
import {
  fetchTiers,
  ACTIVE_TIERS_QUERY_KEY,
  ACTIVE_TIERS_STALE_MS,
} from "../services/tierManagementService";
import type { ModelDetails } from "../types/platform";
import {
  SERVICE_NAME_MAX_LEN,
  sanitizeServiceId,
  validateHardwareDescription,
  validatePricePerUnit,
  validateServiceDescription,
  validateServiceIdLength,
  validateServiceName,
} from "../components/services-management/serviceFormValidation";
import { useAuth } from "./useAuth";
import { isRegistryReadOnlyUser, userHasRole } from "../utils/rbac";
import { useSessionExpiry } from "./useSessionExpiry";
import { showError } from "../utils/errorHandler";
import { showToast } from "../utils/toast";
import { refreshUntil } from "../utils/postMutationRefresh";
import { useInferenceTypes } from "./useInferenceTypes";
import { SERVICE_TIER } from "../config/constants";

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
  "services-all",
  "services-for-tiers",
];

const emptyServiceForm = (): Partial<Service> => ({
  name: "",
  serviceId: "",
  serviceDescription: "",
  hardwareDescription: "",
  publishedOn: Math.floor(Date.now() / 1000),
  modelId: "",
  modelName: "",
  endpoint: "",
  task_type: "",
  modelSubmissionDate: "",
  modelVersion: "1.0",
  tiers: [],
});

export type ServiceTierFilterOption = { id: string; name: string };

/**
 * Tier options built from the loaded rows, not `availableTiers` — that list is
 * ACTIVE-only and task-type-scoped, so it can omit tiers badged in the Tiers
 * column. `tierNames` is positionally aligned with `tierIds` server-side.
 * `pinnedId` keeps the active selection listed when a refetch leaves no row
 * carrying it, so the filter stays clearable.
 */
const buildTierFilterOptions = (
  services: Service[],
  pinnedId: string,
  pinnedName?: string,
): ServiceTierFilterOption[] => {
  const byId = new Map<string, string>();
  for (const service of services) {
    const ids = service.tierIds ?? [];
    const names = service.tierNames ?? [];
    ids.forEach((id, index) => {
      if (!id) return;
      const key = String(id);
      const name = names[index];
      if (!byId.has(key) || (name && byId.get(key) === key)) {
        byId.set(key, name?.trim() || key);
      }
    });
  }
  if (
    pinnedId &&
    pinnedId !== SERVICE_TIER.FILTER.NONE &&
    !byId.has(pinnedId)
  ) {
    byId.set(pinnedId, pinnedName?.trim() || pinnedId);
  }
  return Array.from(byId, ([id, name]) => ({ id, name })).sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
  );
};

/** Client-side tier filter: a service carries many tiers, so this is membership. */
const serviceMatchesTier = (service: Service, filterTierId: string): boolean => {
  if (filterTierId === SERVICE_TIER.FILTER.ALL) return true;
  const ids = (service.tierIds ?? []).filter(Boolean).map(String);
  if (filterTierId === SERVICE_TIER.FILTER.NONE) return ids.length === 0;
  return ids.includes(String(filterTierId));
};

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
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingModelDetails, setIsLoadingModelDetails] = useState(false);
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [isViewingService, setIsViewingService] = useState(false);
  /** Service being edited in the Edit Service tab; null in create-modal mode. */
  const [editingService, setEditingService] = useState<Service | null>(null);
  const [formData, setFormData] = useState<Partial<Service>>(emptyServiceForm);
  /** Typed token kept out of Service objects so list/detail never hold the secret. */
  const [authToken, setAuthToken] = useState("");
  const [hasAuthToken, setHasAuthToken] = useState(false);
  /**
   * The masked token the backend sent for the service being edited ("***").
   * It seeds `authToken` so the field shows the saved token instead of being
   * blank, and is compared against on submit so the mask is never saved back
   * over the real credential.
   */
  const [savedAuthTokenMask, setSavedAuthTokenMask] = useState("");
  const [pricePerUnit, setPricePerUnit] = useState<string>("");
  const [unitSize, setUnitSize] = useState<string>("");
  const [currency, setCurrency] = useState<string>("INR");
  const [selectedTiers, setSelectedTiers] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [createFormEpoch, setCreateFormEpoch] = useState(0);
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
  const [filterTier, setFilterTierValue] = useState<string>(
    SERVICE_TIER.FILTER.ALL,
  );
  /** The selected tier's option, kept so it stays listed across refetches. */
  const [pinnedTier, setPinnedTier] = useState<ServiceTierFilterOption | null>(
    null,
  );
  const {
    taskTypeNames,
    unitByTaskType,
    isLoading: isLoadingTaskTypes,
  } = useInferenceTypes();
  const didInitTaskTypeFilter = useRef(false);
  const [taskTypeFilterReady, setTaskTypeFilterReady] = useState(false);
  useEffect(() => {
    if (didInitTaskTypeFilter.current || isLoadingTaskTypes) return;
    didInitTaskTypeFilter.current = true;
    // Single enabled type → lock filter to it (no All). Multiple → default All ("").
    if (taskTypeNames.length === 1) setFilterTaskType(taskTypeNames[0]);
    setTaskTypeFilterReady(true);
  }, [isLoadingTaskTypes, taskTypeNames]);
  const registrySortAccessors = useMemo(
    () => ({
      name: (s: Service) => s.name ?? "",
      tiers: (s: Service) => (s.tierNames ?? s.tiers ?? []).join(", ").toLowerCase(),
      created: (s: Service) =>
        s.createdAt ? new Date(s.createdAt).getTime() : 0,
    }),
    [],
  );
  const registrySort = useDeferredColumnSort("name", registrySortAccessors);
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
  const {
    isOpen: isCreateOpen,
    onOpen: onCreateOpen,
    onClose: onCreateClose,
  } = useDisclosure();
  const cancelPublishRef = useRef<HTMLButtonElement>(null);
  const cancelUnpublishRef = useRef<HTMLButtonElement>(null);
  const { user } = useAuth();
  const isRegistryReadOnly = isRegistryReadOnlyUser(user?.roles);
  // View is always the second tab. Edit is a StandardModal, not a tab.
  const viewTabIndex = 1;

  // Name + tier filter, then sort, over the full fetched list. Tier is
  // client-side because GET /services takes no tier param.
  const registryTableItems = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    let filtered = q
      ? services.filter((s) => (s.name ?? "").toLowerCase().includes(q))
      : services;
    if (filterTier !== SERVICE_TIER.FILTER.ALL) {
      filtered = filtered.filter((s) => serviceMatchesTier(s, filterTier));
    }
    return registrySort.apply(filtered);
  }, [services, searchQuery, filterTier, registrySort]);

  const tierFilterOptions = useMemo(
    () => buildTierFilterOptions(services, filterTier, pinnedTier?.name),
    [services, filterTier, pinnedTier],
  );

  /** Remembers the label as it is picked, so a later refetch cannot orphan it. */
  const setFilterTier = useCallback(
    (next: string) => {
      setPinnedTier(
        next && next !== SERVICE_TIER.FILTER.NONE
          ? (tierFilterOptions.find((o) => o.id === next) ?? null)
          : null,
      );
      setFilterTierValue(next);
    },
    [tierFilterOptions],
  );

  const showTaskTypeAllOption = taskTypeNames.length > 1;
  const hasActiveFilters =
    filterStatus !== "" ||
    (showTaskTypeAllOption && filterTaskType !== "") ||
    filterTier !== SERVICE_TIER.FILTER.ALL ||
    searchQuery.trim() !== "";
  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterStatus("");
    setFilterTaskType(taskTypeNames.length === 1 ? taskTypeNames[0] : "");
    setFilterTier(SERVICE_TIER.FILTER.ALL);
  };

  const router = useRouter();
  const queryClient = useQueryClient();

  const { checkSessionExpiry } = useSessionExpiry();

  const { isOpen, onOpen, onClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [serviceToDelete, setServiceToDelete] = useState<Service | null>(null);

  // Check if user is GUEST or USER and redirect if so
  useEffect(() => {
    if (userHasRole(user?.roles, "GUEST") || userHasRole(user?.roles, "USER")) {
      showToast({
        type: "error",
        message: "You do not have access to Services Management.",
      });
      router.push("/");
    }
  }, [user, router]);
  // Model fetched by ID when navigating from a deprecated model's "Create Service" (not in active list)
  const [createReturnTo, setCreateReturnTo] = useState<string | null>(null);
  const [preselectedModelFromQuery, setPreselectedModelFromQuery] =
    useState<ModelDetails | null>(null);

  // Fetch all services for current task/publish filters (paginated API walk) for client search + pagination
  // Primitive dep (joined string), not the array — an unstable array ref would
  // re-create fetchServices every render and re-fire the fetch effect below.
  const enabledTaskTypesParam = taskTypeNames.length > 0 ? taskTypeNames.join(",") : undefined;

  const servicesAllQuery = useQuery({
    queryKey: SERVICES_ALL_QUERY_KEY,
    queryFn: listServices,
    staleTime: SERVICES_ALL_STALE_MS,
  });
  const existingServiceIds = useMemo(
    () =>
      (servicesAllQuery.data ?? [])
        .map((s) => s.serviceId || s.service_id || "")
        .filter((id): id is string => Boolean(id)),
    [servicesAllQuery.data],
  );

  const modelsQuery = useQuery({
    queryKey: MODELS_ALL_QUERY_KEY,
    queryFn: getAllModels,
    staleTime: MODELS_ALL_STALE_MS,
  });
  const models = useMemo(
    () =>
      (modelsQuery.data ?? []).filter(
        (model) =>
          model.versionStatus?.toLowerCase() === "active" || !model.versionStatus,
      ),
    [modelsQuery.data],
  );
  const isLoadingModels = modelsQuery.isLoading || isLoadingModelDetails;

  const tiersQuery = useQuery({
    queryKey: ACTIVE_TIERS_QUERY_KEY,
    queryFn: () => fetchTiers(undefined, "ACTIVE"),
    staleTime: ACTIVE_TIERS_STALE_MS,
    enabled: !isLoadingTaskTypes,
  });
  const availableTiers = useMemo(() => {
    const all = tiersQuery.data?.data ?? [];
    if (taskTypeNames.length === 0) return all;
    const enabled = new Set(taskTypeNames.map((n) => n.trim().toLowerCase()));
    return all.filter((t) =>
      t.quotas?.some((q) => enabled.has(q.modelTaskType.toLowerCase())),
    );
  }, [tiersQuery.data, taskTypeNames]);
  const tiersLoaded = tiersQuery.isSuccess;

  const fetchServices = useCallback(async (options?: {
    silent?: boolean;
    /** When false, return items without writing React state (for refreshUntil polls). */
    commit?: boolean;
    taskType?: string;
    status?: string;
  }): Promise<Service[]> => {
    const commit = options?.commit !== false;
    if (!options?.silent && commit) setIsLoading(true);
    try {
      const statusFilter = options?.status !== undefined ? options.status : filterStatus;
      const taskTypeFilter =
        options?.taskType !== undefined ? options.taskType : filterTaskType;
      const isPublishedFilter =
        statusFilter === "published"
          ? true
          : statusFilter === "unpublished"
            ? false
            : undefined;

      // Backend query-filters by the frontend-enabled task types (task_types=),
      // so the list comes back already scoped — no client-side filter here.
      const result = await fetchAllServicesMatchingFilters({
        taskType: taskTypeFilter || undefined,
        taskTypes: enabledTaskTypesParam,
        isPublished: isPublishedFilter,
      });
      if (commit) setServices(result.items);
      return result.items;
    } catch (error: any) {
      console.error("Failed to fetch services:", error);
      showError(error);
      if (commit) setServices([]);
      return [];
    } finally {
      if (!options?.silent && commit) setIsLoading(false);
    }
  }, [filterTaskType, filterStatus, enabledTaskTypesParam]);

  const serviceKey = (s: Pick<Service, "serviceId"> & { service_id?: string }) =>
    s.serviceId || s.service_id || "";

  const upsertLocalService = useCallback((service: Service) => {
    const clean = sanitizeService(service);
    const id = serviceKey(clean);
    if (!id) return;
    setServices((prev) => [
      clean,
      ...prev.filter((s) => serviceKey(s) !== id),
    ]);
    setSelectedService((prev) =>
      prev && serviceKey(prev) === id ? { ...prev, ...clean } : prev,
    );
    setRegistryEpoch((e) => e + 1);
  }, []);

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
    if (!taskTypeFilterReady) return;
    fetchServices();
  }, [fetchServices, taskTypeFilterReady]);

  /** AI4IDS-2949: block Create Service when the platform has no tiers. Edit remains allowed. */
  const isCreateServiceTabDisabled =
    !editingService && tiersLoaded && availableTiers.length === 0;

  // Sync URL tab param to activeTab.
  useEffect(() => {
    const t = router.query.tab;
    const hasEditDeepLink =
      typeof router.query.editServiceId === "string" &&
      !!router.query.editServiceId;
    const isCreateDeepLink = (t === "1" || t === "create") && !hasEditDeepLink;

    if (isCreateDeepLink && !isRegistryReadOnly) {
      if (isCreateServiceTabDisabled) {
        setActiveTab(0);
        const rawReturn = router.query.returnTo;
        const dest =
          typeof rawReturn === "string" && isFormReturnHref(rawReturn)
            ? rawReturn
            : null;
        if (dest) {
          setCreateReturnTo(null);
          void router.push(dest);
          return;
        }
        if (router.query.tab || router.query.modelId) {
          const q = { ...router.query } as Record<string, string>;
          delete q.tab;
          delete q.modelId;
          delete q.returnTo;
          router.replace(
            { pathname: "/services-management", query: q },
            undefined,
            { shallow: true },
          );
        }
        return;
      }
      onCreateOpen();
      if (router.query.tab) {
        const q = { ...router.query } as Record<string, string>;
        delete q.tab;
        router.replace(
          { pathname: "/services-management", query: q },
          undefined,
          { shallow: true },
        );
      }
      return;
    }

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
    // tab=1 without editServiceId already opened Create and returned.
    // tab=1 with editServiceId opens the edit modal; stay on the registry.
    if (t === "2") setActiveTab(viewTabIndex);
    else setActiveTab(0);
  }, [
    router.query.tab,
    router.query.editServiceId,
    router.query.modelId,
    isRegistryReadOnly,
    isCreateServiceTabDisabled,
    router,
    viewTabIndex,
    onCreateOpen,
  ]);

  // Handle query parameters for pre-selecting model from model-management page
  useEffect(() => {
    if (isRegistryReadOnly) return;
    const { modelId, tab } = router.query;
    if (!modelId || typeof modelId !== "string") return;

    const runPreselect = async () => {
      if (tab === "create" && isCreateServiceTabDisabled) {
        setActiveTab(0);
      }

      const stripModelIdFromUrl = () => {
        const nextQuery: Record<string, string> = {};
        const currentTab = router.query.tab;
        const currentReturn = router.query.returnTo;
        if (typeof currentTab === "string") {
          nextQuery.tab = currentTab;
        }
        if (typeof currentReturn === "string" && isFormReturnHref(currentReturn)) {
          nextQuery.returnTo = currentReturn;
        }
        router.replace(
          { pathname: "/services-management", query: nextQuery },
          undefined,
          { shallow: true },
        );
      };

      const inActiveList = models.some(
        (m) => (m.modelId || m.model_id) === modelId,
      );
      if (inActiveList && formData.modelId !== modelId) {
        handleModelNameChange(modelId);
        stripModelIdFromUrl();
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
        stripModelIdFromUrl();
      }
    };

    if (models.length > 0) {
      runPreselect();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.query, models, isCreateServiceTabDisabled]);

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

  const isLlmTaskType = (formData.task_type || "").trim().toLowerCase() === "llm";

  const handleTaskTypeChange = (taskType: string) => {
    setFormData((prev) => ({
      ...prev,
      task_type: taskType,
      modelId: "",
      modelName: "",
      modelSubmissionDate: "",
      modelVersion: "",
      // LLM: Service Name is derived from Service ID — clear free-text name
      name: taskType.trim().toLowerCase() === "llm" ? "" : prev.name,
      serviceId: "",
    }));
    if (taskType.trim().toLowerCase() !== "llm") {
      setAuthToken("");
      setHasAuthToken(false);
      setSavedAuthTokenMask("");
    }
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
        setIsLoadingModelDetails(true);
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

        const rawModelTaskType = resolveTaskType(modelDetails);
        // Select options use catalog `taskTypeNames` exactly — resolve
        // case-insensitively and ignore values outside the enabled set.
        const resolvedModelTaskType =
          taskTypeNames.find(
            (t) => t.trim().toLowerCase() === String(rawModelTaskType).trim().toLowerCase(),
          ) ?? "";

        setFormData((prev) => {
          const task_type = resolvedModelTaskType || prev.task_type || "";
          const taskIsLlm = task_type.trim().toLowerCase() === "llm";
          // Every task type pre-fills "{modelName}/"; the admin adds the suffix
          // ("[model-name]/[GPU]"), so two services on one model cannot clash.
          // LLM sanitizes tighter — its Service ID is sent as the name too.
          const sanitizeId = (s: string) => sanitizeServiceId(s, taskIsLlm);
          const modelPrefix = modelName ? `${sanitizeId(modelName)}/` : "";
          let nextServiceId = prev.serviceId || "";
          if (!editingService) {
            const prevPrefix = prev.modelName
              ? `${sanitizeId(prev.modelName)}/`
              : "";
            if (
              !nextServiceId ||
              nextServiceId === prevPrefix ||
              (prevPrefix && nextServiceId.startsWith(prevPrefix))
            ) {
              // Still on the auto-generated prefix pattern — swap prefix, keep suffix
              const suffix =
                prevPrefix && nextServiceId.startsWith(prevPrefix)
                  ? nextServiceId.slice(prevPrefix.length)
                  : "";
              nextServiceId = `${modelPrefix}${sanitizeId(suffix)}`;
            }
            // else: user hand-edited away from the previous model prefix — preserve
          }
          return {
            ...prev,
            modelId: modelId,
            modelName: modelName,
            modelSubmissionDate: modelSubmissionDate,
            modelVersion: modelVersion,
            task_type,
            ...(editingService ? {} : { serviceId: nextServiceId }),
          };
        });
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
        setIsLoadingModelDetails(false);
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
    setCreateFormEpoch((n) => n + 1);
    setFormData(emptyServiceForm());
    setAuthToken("");
    setHasAuthToken(false);
    setSavedAuthTokenMask("");
    setPricePerUnit("");
    setUnitSize("");
    setCurrency("INR");
    setSelectedTiers([]);
    setPreselectedModelFromQuery(null);
  };

  const openCreateModal = () => {
    if (isRegistryReadOnly || isCreateServiceTabDisabled) return;
    setCreateReturnTo(null);
    setEditingService(null);
    resetCreateForm();
    onCreateOpen();
  };

  const clearCreateEntryQuery = useCallback(() => {
    if (!router.query.returnTo && !router.query.modelId && !router.query.tab) return;
    const q = { ...router.query } as Record<string, string>;
    delete q.returnTo;
    delete q.modelId;
    delete q.tab;
    router.replace({ pathname: "/services-management", query: q }, undefined, {
      shallow: true,
    });
  }, [router]);

  const releaseCreateForm = () => {
    setCreateReturnTo(null);
    resetCreateForm();
    onCreateClose();
  };

  const closeCreateModal = () => {
    releaseCreateForm();
    clearCreateEntryQuery();
  };

  useEffect(() => {
    const raw = router.query.returnTo;
    if (typeof raw !== "string" || !isFormReturnHref(raw)) return;
    setCreateReturnTo(raw);
  }, [router.query.returnTo]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Check session expiry before submitting
    if (!checkSessionExpiry()) return;

    setIsSubmitting(true);

    try {
      let mutatedServiceId = "";
      let apiReturnedServiceId = "";
      const submittedTaskType = (formData.task_type || "").trim();
      const wasCreate = !editingService;

      if (editingService) {
        // Edit mode: PATCH only the fields the edit form allows changing
        const serviceId =
          editingService.serviceId || editingService.service_id || "";
        const updateData: Partial<Service> = {
          serviceId,
          serviceDescription: formData.serviceDescription,
          task_type: formData.task_type,
          costPerUnit: pricePerUnit ? Number(pricePerUnit) : undefined,
          unitSize: unitSize ? Number(unitSize) : undefined,
          tierIds: selectedTiers,
        };
        const storedEndpoint =
          editingService.endpoint || editingService.endpoint_url || "";
        if (formData.endpoint !== storedEndpoint) {
          updateData.endpoint = formData.endpoint;
        }
        const trimmedToken = authToken.trim();
        // An untouched field still holds the backend's mask ("***"); sending
        // it would overwrite the stored token with the mask.
        const tokenIsSavedMask =
          !!savedAuthTokenMask && trimmedToken === savedAuthTokenMask;
        if (
          (formData.task_type || "").trim().toLowerCase() === "llm" &&
          trimmedToken &&
          !tokenIsSavedMask
        ) {
          updateData.authToken = trimmedToken;
        }
        // PATCH returns only `{ serviceId }` — do not treat it as a full Service
        await updateService(updateData);
        mutatedServiceId = serviceId;
        apiReturnedServiceId = serviceId;
        upsertLocalService({
          ...editingService,
          ...updateData,
          serviceId,
          task_type: formData.task_type || editingService.task_type,
        });

        showToast({
          type: "success",
          message: "Service has been updated successfully.",
        });
      } else {
        // Use the user-provided serviceId.
        const serviceId = formData.serviceId?.trim() || "";
        const taskIsLlm =
          (formData.task_type || "").trim().toLowerCase() === "llm";
        // For LLM, Service ID is copied to Service Name
        const serviceName = taskIsLlm
          ? serviceId
          : formData.name?.trim() || "";

        // Prepare service data with the user-provided serviceId.
        // Do not send modelSubmissionDate because backend owns this field.
        const serviceFormData: Partial<Service> = { ...formData };
        delete serviceFormData.modelSubmissionDate;
        const tierIds = selectedTiers; // selectedTiers stores tier IDs directly

        const trimmedToken = authToken.trim();
        const serviceData: Partial<Service> = {
          ...serviceFormData,
          name: serviceName,
          serviceId: serviceId,
          publishedOn: Math.floor(Date.now() / 1000),
          // Trimmed so the length the user was validated against is the
          // length the backend measures.
          serviceDescription: formData.serviceDescription?.trim() || "",
          hardwareDescription: formData.hardwareDescription?.trim() || "",
          api_key: "",
          status: "active",
          costPerUnit: pricePerUnit ? Number(pricePerUnit) : undefined,
          unitSize: unitSize ? Number(unitSize) : undefined,
          tierIds,
          ...(taskIsLlm && trimmedToken ? { authToken: trimmedToken } : {}),
        };

        const created = await createService(serviceData);
        apiReturnedServiceId =
          created.serviceId || created.service_id || "";
        mutatedServiceId = apiReturnedServiceId || serviceId;
        upsertLocalService({
          ...serviceData,
          serviceId: mutatedServiceId,
          name: created.name || serviceName,
          isPublished: false,
          task_type: formData.task_type,
        } as Service);

        showToast({
          type: "success",
          message: "Service has been created successfully.",
        });
      }

      invalidateServiceQueries();
      setEditingService(null);
      resetCreateForm();
      setCreateReturnTo(null);
      setActiveTab(0);
      onCreateClose();
      router.replace(
        { pathname: "/services-management", query: {} },
        undefined,
        { shallow: true },
      );

      const targetId = mutatedServiceId;
      if (targetId) {
        // Only GET by id when the API returned a registry key — typed form
        // fallbacks can 404 and never satisfy refreshUntil.
        if (apiReturnedServiceId) {
          try {
            upsertLocalService(await getServiceById(apiReturnedServiceId));
          } catch (e) {
            console.warn("Failed to refresh service after create/update:", e);
          }
        }

        // Align list filters with the mutated row so refreshUntil can succeed
        // (creates are unpublished; task type may differ from the active filter).
        let listTaskType = filterTaskType;
        let listStatus = filterStatus;
        if (
          submittedTaskType &&
          filterTaskType &&
          submittedTaskType.toLowerCase() !== filterTaskType.toLowerCase()
        ) {
          listTaskType = submittedTaskType;
          setFilterTaskType(submittedTaskType);
        }
        if (wasCreate && filterStatus === "published") {
          listStatus = "";
          setFilterStatus("");
        }

        const items = await refreshUntil(
          () =>
            fetchServices({
              silent: true,
              commit: false,
              taskType: listTaskType,
              status: listStatus,
            }),
          (rows) => rows.some((s) => serviceKey(s) === targetId),
        );
        setServices(items);
      } else {
        await fetchServices({ silent: true });
      }
      await queryClient.invalidateQueries({ queryKey: SERVICES_ALL_QUERY_KEY });
    } catch (error: any) {
      showError(error);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Unit type is derived from task type (billing is server-driven via inference_types).
  const unitType = unitByTaskType[formData.task_type || ""] || "";

  const viewServiceTaskType = resolveTaskType(selectedService);
  const viewServiceUnitType =
    unitByTaskType[viewServiceTaskType] ||
    selectedService?.billingUnitType ||
    "";

  const filteredModelsForDropdown = formData.task_type
    ? modelsForDropdown.filter((model) => {
        const modelTaskType = resolveTaskType(model);
        return (
          modelTaskType.toLowerCase() === formData.task_type?.toLowerCase()
        );
      })
    : modelsForDropdown;

  const isUnitSizeValid = /^\d+$/.test(unitSize.trim()) && Number(unitSize) > 0;

  /**
   * Price bounds hold on PATCH as well as POST, so this one is not gated on
   * create mode the way the length rules below are.
   */
  const pricePerUnitError = validatePricePerUnit(pricePerUnit);

  // Duplicate serviceId check — only in create mode (serviceId is read-only when editing)
  const serviceIdExists =
    !editingService &&
    !!formData.serviceId?.trim() &&
    existingServiceIds.includes(formData.serviceId.trim());

  /**
   * ULCA length rules — create only. PATCH does not carry them, so an edit
   * of a pre-existing service that predates these limits stays submittable.
   */
  /**
   * Registry-state clash — surfaced immediately, since unlike the length
   * rules it cannot be stated up-front in hint text.
   */
  const serviceIdError = serviceIdExists ? "Service Id already exists" : null;

  /**
   * ULCA length/charset rules — create only. PATCH carries none of them, so
   * editing a service that predates these limits stays submittable.
   *
   * Each value doubles as the field's error message (the form reveals it
   * once that field has been blurred) and as a Create-button gate. A short
   * description looks filled in, so the disabled button alone would not say
   * which field is at fault.
   */
  const isCreateMode = !editingService;
  const serviceDescriptionError = isCreateMode
    ? validateServiceDescription(formData.serviceDescription)
    : null;
  // LLM derives its name from the Service ID, so the separate Service Name
  // field only exists — and only needs validating — for non-LLM tasks.
  const serviceNameError =
    isCreateMode && !isLlmTaskType ? validateServiceName(formData.name) : null;
  const hardwareDescriptionError = isCreateMode
    ? validateHardwareDescription(formData.hardwareDescription)
    : null;
  /**
   * Service ID length, plus the tighter name cap when the ID doubles as the
   * Service Name. Kept apart from `serviceIdError` so the duplicate clash
   * can show immediately while this one waits for blur.
   */
  const serviceIdLengthError = !isCreateMode
    ? null
    : (validateServiceIdLength(formData.serviceId) ??
      (isLlmTaskType &&
      (formData.serviceId || "").trim().length > SERVICE_NAME_MAX_LEN
        ? `Service ID must not exceed ${SERVICE_NAME_MAX_LEN} characters, because it is also used as the Service Name.`
        : null));

  const meetsCreateFieldRules =
    !serviceDescriptionError &&
    !serviceNameError &&
    !hardwareDescriptionError &&
    !serviceIdLengthError;

  // LLM: Service Name is derived from Service ID (not shown). Non-LLM: both required.
  const hasRequiredServiceIdentity = isLlmTaskType
    ? !!formData.serviceId?.trim()
    : !!formData.name?.trim() && !!formData.serviceId?.trim();

  const canCreateService =
    hasRequiredServiceIdentity &&
    !serviceIdExists &&
    meetsCreateFieldRules &&
    !!formData.modelId?.trim() &&
    !!formData.endpoint?.trim() &&
    !!formData.task_type?.trim() &&
    !pricePerUnitError &&
    !!currency.trim() &&
    isUnitSizeValid &&
    selectedTiers.length > 0;

  const isCreateFormModelSelected = !!formData.modelId?.trim();

  const handleViewService = async (serviceId: string) => {
    // Check session expiry before viewing service
    if (!checkSessionExpiry()) return;
    setSelectedServiceModelDeprecated(null);
    try {
      const service = await getServiceById(serviceId);
      if (editingService) {
        setEditingService(null);
        resetCreateForm();
      }
      setSelectedService(service);
      setIsViewingService(true);
      setActiveTab(viewTabIndex);
      const q = { ...router.query } as Record<string, string>;
      delete q.editServiceId;
      q.tab = "2";
      router.replace(
        { pathname: "/services-management", query: q },
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
   * Load a service into the Edit Service modal, pre-populating
   * the shared form state with the service's current values.
   */
  const handleEditService = async (serviceId: string) => {
    // Check session expiry before loading the service into the edit form
    if (!checkSessionExpiry()) return;
    try {
      onCreateClose();
      const service = await getServiceById(serviceId);
      const modelId = service.modelId || service.model_id || "";
      setFormData({
        name: service.name || "",
        serviceId: service.serviceId || service.service_id || "",
        serviceDescription:
          service.serviceDescription || service.description || "",
        // Read-only in edit; PATCH never resends it.
        hardwareDescription: service.hardwareDescription || "",
        publishedOn: service.publishedOn,
        modelId,
        modelName: service.model?.name || modelId,
        endpoint: service.endpoint || service.endpoint_url || "",
        task_type: resolveTaskType(service),
        modelSubmissionDate: "",
        modelVersion: service.modelVersion || service.model_version || "1.0",
      });
      const maskedAuthToken = resolveMaskedAuthToken(service);
      setAuthToken(maskedAuthToken);
      setSavedAuthTokenMask(maskedAuthToken);
      setHasAuthToken(!!service.hasAuthToken);
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
      setCreateFormEpoch((n) => n + 1);
      // Fill model name/submission date from the model record (read-only display)
      if (modelId) {
        handleModelNameChange(modelId);
      }
      setActiveTab(0);
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
    const isViewTab = index === viewTabIndex;
    setActiveTab(index);
    if (!isViewTab) {
      setIsViewingService(false);
      setSelectedService(null);
      setSelectedServiceModelDeprecated(null);
    }
    if (editingService) {
      setEditingService(null);
      resetCreateForm();
    }
    const q = { ...router.query } as Record<string, string>;
    delete q.tab;
    delete q.editServiceId;
    if (isViewTab) {
      q.tab = "2";
    }
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
    const deletedId = serviceToDelete.serviceId;
    setDeletingServiceUuid(deletedId);
    try {
      await deleteService(deletedId);
      setServices((prev) => prev.filter((s) => serviceKey(s) !== deletedId));
      setRegistryEpoch((e) => e + 1);
      showToast({
        type: "success",
        message: `${serviceToDelete.name || serviceToDelete.service_id} has been deleted successfully.`,
      });
      invalidateServiceQueries();
      if (selectedService?.serviceId === deletedId) {
        setIsViewingService(false);
        setSelectedService(null);
        setSelectedServiceModelDeprecated(null);
        setActiveTab(0);
      }
      await refreshUntil(
        () => fetchServices({ silent: true, commit: false }),
        (items) => !items.some((s) => serviceKey(s) === deletedId),
      ).then(setServices);
    } catch (error: any) {
      showError(error);
    } finally {
      setDeletingServiceUuid(null);
      setServiceToDelete(null);
      onClose();
    }
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
    // Remounts the table so client pagination returns to page 1 on a filter change.
    tableKey: `${filterStatus}-${filterTaskType}-${filterTier}-${registryEpoch}`,
    searchQuery,
    setSearchQuery,
    filterStatus,
    setFilterStatus,
    filterTaskType,
    setFilterTaskType,
    filterTier,
    setFilterTier,
    tierFilterOptions,
    taskTypeNames,
    hasActiveFilters,
    clearAllFilters,
    registrySort,
    handleViewService,
    handleEditService,
    handleDeleteClick,
    deletingServiceUuid,

    // Create/Edit form
    editingService,
    formData,
    handleInputChange,
    handleTaskTypeChange,
    handleModelNameChange,
    authToken,
    setAuthToken,
    hasAuthToken,
    savedAuthTokenMask,
    isLoadingModels,
    filteredModelsForDropdown,
    unitType,
    pricePerUnit,
    setPricePerUnit,
    pricePerUnitError,
    unitSize,
    setUnitSize,
    currency,
    setCurrency,
    selectedTiers,
    toggleTier,
    availableTiers,
    isCreateServiceTabDisabled,
    isCreateFormModelSelected,
    canCreateService,
    isLlmTaskType,
    serviceIdError,
    serviceIdLengthError,
    serviceDescriptionError,
    serviceNameError,
    hardwareDescriptionError,
    createFormEpoch,
    isSubmitting,
    handleSubmit,
    handleCancelForm,
    isCreateOpen,
    openCreateModal,
    closeCreateModal,
    releaseCreateForm,
    createReturnTo,

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
