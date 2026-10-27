// All state, data fetching, and mutations for the Services Management page
// (Service Registry / Create-Edit Service / View Service tabs).
import { useDisclosure } from "@chakra-ui/react";
import { useRouter } from "next/router";
import { safeFormReturnHref } from "../components/common/FormPage";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  SERVICE_LIST_COLUMNS,
  serviceListCellKey,
  serviceListSortAccessors,
  type ServiceListColumnDef,
} from "../components/services-management/serviceListColumns";
import {
  applyServicePublishPatch,
  fetchRegistryServicesPage,
  filterServicesForPublishStatus,
  mergeServiceIdLists,
  resolveOptionalFilterValue,
  serviceIdsFromItems,
  shouldReplaceFullServiceIds,
} from "../components/services-management/serviceRegistryFetch";
import { useDeferredColumnSort } from "../utils/tableSort";
import { resolveTaskType } from "../utils/platformService";
import {
  fetchExistingServiceIds,
  getServiceListColumns,
  createService,
  getServiceById,
  updateService,
  deleteService,
  SERVICES_ALL_QUERY_KEY,
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
  sanitizeServiceId,
  parsePricePerUnit,
} from "../components/services-management/serviceFormValidation";
import {
  computeServiceFormGates,
  hasActiveClientServiceFilters,
  hasActiveServerServiceFilters,
} from "../components/services-management/serviceFormGates";
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
 * Tier options: every tier in `catalog` (ACTIVE, task-type-scoped), so a tier
 * with no service mapped yet is still filterable, plus any tier the loaded rows
 * carry that the catalog omits (inactive, other task type, or newer than the
 * cache), so every badge in the Tiers column is filterable too. `tierNames` is
 * positionally aligned with `tierIds` server-side. `pinnedId` keeps the active
 * selection listed when a refetch leaves no source carrying it, so the filter
 * stays clearable.
 */
const buildTierFilterOptions = (
  catalog: ServiceTierFilterOption[],
  services: Service[],
  pinnedId: string,
  pinnedName?: string,
): ServiceTierFilterOption[] => {
  const byId = new Map<string, string>();
  for (const tier of catalog) {
    if (tier.id) byId.set(String(tier.id), tier.name?.trim() || String(tier.id));
  }
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

/** Whether the edit form changed the stored Hardware Description; false on create. */
const isHardwareDescriptionEdited = (
  form: Partial<Service>,
  editing: Service | null,
): boolean =>
  !!editing &&
  (form.hardwareDescription || "").trim() !==
    (editing.hardwareDescription || "").trim();

/**
 * Hardware Description is editable on edit too, but only validated there
 * once changed — a stored value that predates the length rule must not
 * block an unrelated edit.
 */
const shouldValidateHardwareDescription = (
  form: Partial<Service>,
  editing: Service | null,
): boolean => !editing || isHardwareDescriptionEdited(form, editing);

/**
 * PATCH field for Hardware Description, sent only when changed. A cleared
 * field goes as null, not "": the backend treats null as "clear" but 422s
 * on "" alongside an endpoint change.
 */
const hardwareDescriptionUpdate = (
  form: Partial<Service>,
  editing: Service,
): Partial<Service> => {
  if (!isHardwareDescriptionEdited(form, editing)) return {};
  return { hardwareDescription: form.hardwareDescription?.trim() || null };
};

type ServiceFormPrices = {
  pricePerUnit: string;
  cachedInputPricePerUnit: string;
  outputPricePerUnit: string;
  unitSize: string;
  isLlmTaskType: boolean;
};

function llmPriceFields(
  prices: ServiceFormPrices,
): Pick<Service, "cachedInputCostPerUnit" | "outputCostPerUnit"> {
  if (!prices.isLlmTaskType) return {};
  return {
    cachedInputCostPerUnit: parsePricePerUnit(prices.cachedInputPricePerUnit),
    outputCostPerUnit: parsePricePerUnit(prices.outputPricePerUnit),
  };
}

function buildServiceUpdatePayload(options: {
  editingService: Service;
  formData: Partial<Service>;
  prices: ServiceFormPrices;
  authToken: string;
  savedAuthTokenMask: string;
  selectedTiers: string[];
}): Partial<Service> {
  const {
    editingService,
    formData,
    prices,
    authToken,
    savedAuthTokenMask,
    selectedTiers,
  } = options;
  const serviceId =
    editingService.serviceId || editingService.service_id || "";
  const updateData: Partial<Service> = {
    serviceId,
    serviceDescription: formData.serviceDescription,
    task_type: formData.task_type,
    costPerUnit: parsePricePerUnit(prices.pricePerUnit),
    ...llmPriceFields(prices),
    ...hardwareDescriptionUpdate(formData, editingService),
    unitSize: prices.unitSize ? Number(prices.unitSize) : undefined,
    tierIds: selectedTiers,
  };
  const storedEndpoint =
    editingService.endpoint || editingService.endpoint_url || "";
  if (formData.endpoint !== storedEndpoint) {
    updateData.endpoint = formData.endpoint;
  }
  const trimmedToken = authToken.trim();
  const tokenIsSavedMask =
    !!savedAuthTokenMask && trimmedToken === savedAuthTokenMask;
  const isLlm = (formData.task_type || "").trim().toLowerCase() === "llm";
  if (isLlm && trimmedToken && !tokenIsSavedMask) {
    updateData.authToken = trimmedToken;
  }
  return updateData;
}

function buildServiceCreatePayload(options: {
  formData: Partial<Service>;
  prices: ServiceFormPrices;
  authToken: string;
  selectedTiers: string[];
}): Partial<Service> {
  const { formData, prices, authToken, selectedTiers } = options;
  const serviceId = formData.serviceId?.trim() || "";
  const taskIsLlm = (formData.task_type || "").trim().toLowerCase() === "llm";
  const serviceName = taskIsLlm ? serviceId : formData.name?.trim() || "";
  const serviceFormData: Partial<Service> = { ...formData };
  delete serviceFormData.modelSubmissionDate;
  const trimmedToken = authToken.trim();
  const serviceData: Partial<Service> = {
    ...serviceFormData,
    name: serviceName,
    serviceId,
    publishedOn: Math.floor(Date.now() / 1000),
    serviceDescription: formData.serviceDescription?.trim() || undefined,
    hardwareDescription: formData.hardwareDescription?.trim() || undefined,
    api_key: "",
    status: "active",
    costPerUnit: parsePricePerUnit(prices.pricePerUnit),
    ...llmPriceFields(prices),
    unitSize: prices.unitSize ? Number(prices.unitSize) : undefined,
    tierIds: selectedTiers,
  };
  if (taskIsLlm && trimmedToken) {
    serviceData.authToken = trimmedToken;
  }
  return serviceData;
}

/** Keep auto-filled `{modelName}` / `{modelName}/{suffix}` in sync when the model changes. */
function nextAutoServiceId(options: {
  previousServiceId: string;
  previousModelName: string | undefined;
  modelName: string;
  taskIsLlm: boolean;
}): string {
  const sanitizeId = (value: string) =>
    sanitizeServiceId(value, options.taskIsLlm);
  const modelPrefix = options.modelName ? sanitizeId(options.modelName) : "";
  const nextServiceId = options.previousServiceId || "";
  const prevPrefix = options.previousModelName
    ? sanitizeId(options.previousModelName)
    : "";
  const hasPrevSuffix =
    Boolean(prevPrefix) && nextServiceId.startsWith(`${prevPrefix}/`);
  if (nextServiceId && nextServiceId !== prevPrefix && !hasPrevSuffix) {
    return nextServiceId;
  }
  const suffix = hasPrevSuffix
    ? nextServiceId.slice(prevPrefix.length)
    : "";
  return `${modelPrefix}${sanitizeId(suffix)}`;
}

function formDataAfterModelSelect(options: {
  prev: Partial<Service>;
  modelId: string;
  modelName: string;
  modelSubmissionDate: string;
  modelVersion: string;
  resolvedModelTaskType: string;
  isEditing: boolean;
}): Partial<Service> {
  const task_type =
    options.resolvedModelTaskType || options.prev.task_type || "";
  const next: Partial<Service> = {
    ...options.prev,
    modelId: options.modelId,
    modelName: options.modelName,
    modelSubmissionDate: options.modelSubmissionDate,
    modelVersion: options.modelVersion,
    task_type,
  };
  if (options.isEditing) return next;
  next.serviceId = nextAutoServiceId({
    previousServiceId: options.prev.serviceId || "",
    previousModelName: options.prev.modelName,
    modelName: options.modelName,
    taskIsLlm: task_type.trim().toLowerCase() === "llm",
  });
  return next;
}

function clearModelFormFields(prev: Partial<Service>): Partial<Service> {
  return {
    ...prev,
    modelId: "",
    modelName: "",
    modelSubmissionDate: "",
    modelVersion: "",
  };
}

function resolveCatalogTaskType(
  rawModelTaskType: string,
  taskTypeNames: readonly string[],
): string {
  const normalized = String(rawModelTaskType).trim().toLowerCase();
  return (
    taskTypeNames.find((name) => name.trim().toLowerCase() === normalized) ?? ""
  );
}

function omitQueryKeys(
  query: Record<string, string | string[] | undefined>,
  keys: readonly string[],
): Record<string, string> {
  const drop = new Set(keys);
  const next: Record<string, string> = {};
  for (const [key, value] of Object.entries(query)) {
    if (drop.has(key) || typeof value !== "string") continue;
    if (key === "returnTo") {
      const path = safeFormReturnHref(value);
      if (!path) continue;
      next[key] = path;
      continue;
    }
    next[key] = value;
  }
  return next;
}

function editFormStateFromService(
  service: Service,
  availableTiers: readonly { id: string; name: string }[],
): {
  formData: Partial<Service>;
  tierIds: string[];
  modelId: string;
} {
  const modelId = service.modelId || service.model_id || "";
  const tierIds = service.tierIds?.length
    ? service.tierIds
    : (service.tierNames ?? service.tiers ?? [])
        .map((name) => availableTiers.find((tier) => tier.name === name)?.id)
        .filter((id): id is string => Boolean(id));
  return {
    modelId,
    tierIds,
    formData: {
      name: service.name || "",
      serviceId: service.serviceId || service.service_id || "",
      serviceDescription:
        service.serviceDescription || service.description || "",
      hardwareDescription: service.hardwareDescription || "",
      publishedOn: service.publishedOn,
      modelId,
      modelName: service.model?.name || modelId,
      endpoint: service.endpoint || service.endpoint_url || "",
      task_type: resolveTaskType(service),
      modelSubmissionDate: "",
      modelVersion: service.modelVersion || service.model_version || "1.0",
    },
  };
}

function isDeprecatedVersionStatus(status: unknown): boolean {
  return (
    typeof status === "string" && status.toLowerCase() === "deprecated"
  );
}

type ServicesQuery = Record<string, string | string[] | undefined>;

function replaceServicesQuery(
  replace: (url: { pathname: string; query: Record<string, string> }, as: undefined, opts: { shallow: boolean }) => void,
  query: Record<string, string>,
): void {
  replace(
    { pathname: "/services-management", query },
    undefined,
    { shallow: true },
  );
}

type TabSyncActions = {
  query: ServicesQuery;
  onCreateOpen: () => void;
  setActiveTab: (tab: number) => void;
  bumpCreateRouteGen: () => void;
  clearCreateReturnTo: () => void;
  replace: (url: { pathname: string; query: Record<string, string> }, as: undefined, opts: { shallow: boolean }) => void;
  replaceHref: (href: string) => void;
};

function openCreateFromDeepLink(actions: TabSyncActions): void {
  actions.onCreateOpen();
  if (!actions.query.tab) return;
  replaceServicesQuery(actions.replace, omitQueryKeys(actions.query, ["tab"]));
}

function blockCreateWhenNoTiers(actions: TabSyncActions): void {
  actions.setActiveTab(0);
  showToast({ type: "warning", message: "No tiers configured" });
  const rawReturn = actions.query.returnTo;
  const dest =
    typeof rawReturn === "string" ? safeFormReturnHref(rawReturn) : null;
  actions.bumpCreateRouteGen();
  if (dest) {
    actions.clearCreateReturnTo();
    actions.replaceHref(dest);
    return;
  }
  if (!actions.query.tab && !actions.query.modelId) return;
  replaceServicesQuery(
    actions.replace,
    omitQueryKeys(actions.query, ["tab", "modelId", "returnTo"]),
  );
}

function blockCreateForReadOnly(actions: TabSyncActions): void {
  actions.bumpCreateRouteGen();
  actions.setActiveTab(0);
  if (
    !actions.query.tab &&
    !actions.query.modelId &&
    !actions.query.editServiceId
  ) {
    return;
  }
  replaceServicesQuery(
    actions.replace,
    omitQueryKeys(actions.query, ["tab", "modelId", "editServiceId"]),
  );
}

/** Apply `?tab=` / create deep-link side effects for the registry page. */
function syncServicesTabFromQuery(options: {
  query: ServicesQuery;
  isRegistryReadOnly: boolean;
  isCreateServiceTabDisabled: boolean;
  viewTabIndex: number;
  onCreateOpen: () => void;
  setActiveTab: (tab: number) => void;
  bumpCreateRouteGen: () => void;
  clearCreateReturnTo: () => void;
  replace: (url: { pathname: string; query: Record<string, string> }, as: undefined, opts: { shallow: boolean }) => void;
  replaceHref: (href: string) => void;
}): void {
  const t = options.query.tab;
  const hasEditDeepLink =
    typeof options.query.editServiceId === "string" &&
    Boolean(options.query.editServiceId);
  const isCreateDeepLink = (t === "1" || t === "create") && !hasEditDeepLink;
  const actions: TabSyncActions = options;

  if (isCreateDeepLink && !options.isRegistryReadOnly) {
    if (options.isCreateServiceTabDisabled) {
      blockCreateWhenNoTiers(actions);
      return;
    }
    openCreateFromDeepLink(actions);
    return;
  }

  if (options.isRegistryReadOnly && (t === "1" || t === "create")) {
    blockCreateForReadOnly(actions);
    return;
  }

  if (t === "2") options.setActiveTab(options.viewTabIndex);
  else options.setActiveTab(0);
}

function modelIdInList(
  models: readonly ModelDetails[],
  modelId: string,
): boolean {
  return models.some((model) => (model.modelId || model.model_id) === modelId);
}

async function loadNonDeprecatedModel(
  modelId: string,
): Promise<ModelDetails | null> {
  const modelDetails = await getModelById(modelId);
  if (!modelDetails) return null;
  if (isDeprecatedVersionStatus(modelDetails.versionStatus)) return null;
  return modelDetails;
}

function stripModelIdQueryParam(options: {
  isActive: () => boolean;
  pathname: string;
  currentQuery: ServicesQuery;
  replace: (url: { pathname: string; query: Record<string, string> }, as: undefined, opts: { shallow: boolean }) => void;
}): void {
  if (!options.isActive()) return;
  if (options.pathname !== "/services-management") return;
  if (typeof options.currentQuery.modelId !== "string") return;
  replaceServicesQuery(
    options.replace,
    omitQueryKeys(options.currentQuery, ["modelId"]),
  );
}

async function preselectModelFromQueryParam(options: {
  modelId: string;
  models: readonly ModelDetails[];
  isActive: () => boolean;
  currentFormModelId: string | undefined;
  applyModel: (modelId: string) => void;
  setPreselectedModel: (model: ModelDetails) => void;
  stripModelId: () => void;
}): Promise<void> {
  if (modelIdInList(options.models, options.modelId)) {
    if (options.currentFormModelId !== options.modelId) {
      options.applyModel(options.modelId);
    }
    options.stripModelId();
    return;
  }
  try {
    const modelDetails = await loadNonDeprecatedModel(options.modelId);
    if (!options.isActive()) return;
    if (modelDetails) {
      options.setPreselectedModel(modelDetails);
      if (options.currentFormModelId !== options.modelId) {
        options.applyModel(options.modelId);
      }
    }
  } catch (e) {
    if (!options.isActive()) return;
    console.error("Failed to load preselected model:", e);
  }
  options.stripModelId();
}

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
  // LLM only: pricePerUnit is then the input token price.
  const [cachedInputPricePerUnit, setCachedInputPricePerUnit] = useState<string>("");
  const [outputPricePerUnit, setOutputPricePerUnit] = useState<string>("");
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
  const [registryPage, setRegistryPage] = useState(1);
  const [registryPageSize, setRegistryPageSize] = useState(25);
  const [serverFilters, setServerFilters] = useState<Record<string, string>>({});
  const [serverTotal, setServerTotal] = useState(0);
  const { user, isLoading: authLoading } = useAuth();
  const columnsQuery = useQuery({
    queryKey: ["service-list-columns", user?.user_id],
    queryFn: getServiceListColumns,
    enabled: Boolean(user?.user_id),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  useEffect(() => {
    if (!columnsQuery.isError || !columnsQuery.error) return;
    showError(columnsQuery.error);
  }, [columnsQuery.isError, columnsQuery.error]);
  const serviceListCatalogue: readonly ServiceListColumnDef[] =
    columnsQuery.data?.columns ?? SERVICE_LIST_COLUMNS;
  const serviceListUsesServer = columnsQuery.data?.source === "api";
  const registrySortAccessors = useMemo(
    () => serviceListSortAccessors(serviceListCatalogue),
    [serviceListCatalogue],
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
  const isRegistryReadOnly = isRegistryReadOnlyUser(user?.roles);
  // View is always the second tab. Edit is a StandardModal, not a tab.
  const viewTabIndex = 1;

  // Offline catalogue: name + tier filter, then sort, over the full fetched list.
  // When GET /services/columns is available, filters and sort are query params
  // and the rows are already one server page.
  const registryTableItems = useMemo(() => {
    if (serviceListUsesServer) return services;
    const q = searchQuery.trim().toLowerCase();
    let filtered = q
      ? services.filter((s) => (s.name ?? "").toLowerCase().includes(q))
      : services;
    if (filterTier !== SERVICE_TIER.FILTER.ALL) {
      filtered = filtered.filter((s) => serviceMatchesTier(s, filterTier));
    }
    return registrySort.apply(filtered);
  }, [services, searchQuery, filterTier, registrySort, serviceListUsesServer]);

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

  const tierFilterOptions = useMemo(
    () =>
      buildTierFilterOptions(
        availableTiers,
        services,
        filterTier,
        pinnedTier?.name,
      ),
    [availableTiers, services, filterTier, pinnedTier],
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
  const taskFilterColumnId = serviceListCatalogue.find(
    (column) => serviceListCellKey(column.id) === "task",
  )?.id;
  const statusFilterColumnId = serviceListCatalogue.find(
    (column) => serviceListCellKey(column.id) === "status",
  )?.id;
  const hasActiveFilters = serviceListUsesServer
    ? hasActiveServerServiceFilters(
        serverFilters,
        taskFilterColumnId,
        taskTypeNames,
      )
    : hasActiveClientServiceFilters({
        filterStatus,
        filterTaskType,
        filterTier,
        searchQuery,
        showTaskTypeAllOption,
        allTierValue: SERVICE_TIER.FILTER.ALL,
      });
  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterStatus("");
    setFilterTaskType(taskTypeNames.length === 1 ? taskTypeNames[0] : "");
    setFilterTier(SERVICE_TIER.FILTER.ALL);
    setServerFilters({});
    setRegistryPage(1);
  };
  const setServerFilterValue = useCallback((columnId: string, value: string) => {
    setRegistryPage(1);
    setServerFilters((prev) => ({ ...prev, [columnId]: value }));
  }, []);

  const router = useRouter();
  const routerRef = useRef(router);
  routerRef.current = router;
  const routerQueryRef = useRef(router.query);
  routerQueryRef.current = router.query;
  /** Invalidates in-flight create-entry URL writes after Cancel, breadcrumb, or success. */
  const createRouteGenRef = useRef(0);
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

  /**
   * Service ids from the last registry fetch that was not narrowed by the
   * table's task-type or publish filter. That fetch is still limited to task
   * types enabled in the UI.
   */
  const [fullServiceIds, setFullServiceIds] = useState<string[] | null>(null);

  /**
   * Unfiltered ids for the create-form duplicate check. An id registered under
   * a task type the registry does not list would otherwise pass here and only
   * fail as a 409 on submit.
   */
  const allServiceIdsQuery = useQuery({
    queryKey: ["all-service-ids"],
    queryFn: fetchExistingServiceIds,
    enabled: isCreateOpen && !editingService,
    staleTime: 30 * 1000,
  });

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

  const commitFetchedServices = useCallback(
    (
      items: Service[],
      total: number,
      statusFilter: string,
      taskTypeFilter: string,
    ) => {
      setServices(items);
      if (serviceListUsesServer) {
        setServerTotal(total);
        return;
      }
      const ids = serviceIdsFromItems(items);
      if (
        shouldReplaceFullServiceIds(statusFilter, taskTypeFilter, taskTypeNames)
      ) {
        setFullServiceIds(ids);
        return;
      }
      setFullServiceIds((prev) => mergeServiceIdLists(prev, ids));
    },
    [serviceListUsesServer, taskTypeNames],
  );

  const fetchServices = useCallback(async (options?: {
    silent?: boolean;
    /** When false, return items without writing React state (for refreshUntil polls). */
    commit?: boolean;
    taskType?: string;
    status?: string;
  }): Promise<Service[]> => {
    const commit = options?.commit !== false;
    const showLoading = Boolean(commit && !options?.silent);
    if (showLoading) setIsLoading(true);
    try {
      const statusFilter = resolveOptionalFilterValue(
        options?.status,
        filterStatus,
      );
      const taskTypeFilter = resolveOptionalFilterValue(
        options?.taskType,
        filterTaskType,
      );
      const page = await fetchRegistryServicesPage(
        {
          filterStatus,
          filterTaskType,
          enabledTaskTypesParam,
          taskTypeNames,
          serviceListUsesServer,
          serverFilters,
          taskFilterColumnId,
          statusFilterColumnId,
          serviceListCatalogue,
          registryPage,
          registryPageSize,
          sortMode: registrySort.mode,
          sortKey: registrySort.sort.key,
          sortDirection: registrySort.sort.direction,
        },
        options,
      );
      if (commit) {
        commitFetchedServices(
          page.items,
          page.total,
          statusFilter,
          taskTypeFilter,
        );
      }
      return page.items;
    } catch (error: any) {
      console.error("Failed to fetch services:", error);
      showError(error);
      if (commit) setServices([]);
      return [];
    } finally {
      if (showLoading) setIsLoading(false);
    }
  }, [
    commitFetchedServices,
    filterTaskType,
    filterStatus,
    enabledTaskTypesParam,
    taskTypeNames,
    serviceListUsesServer,
    serverFilters,
    taskFilterColumnId,
    statusFilterColumnId,
    serviceListCatalogue,
    registryPage,
    registryPageSize,
    registrySort.mode,
    registrySort.sort.key,
    registrySort.sort.direction,
  ]);

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
      const serverStatus = statusFilterColumnId
        ? serverFilters[statusFilterColumnId]
        : "";
      const publishedOnly =
        filterStatus === "published" || serverStatus === "true";
      const unpublishedOnly =
        filterStatus === "unpublished" || serverStatus === "false";
      setServices((prev) =>
        filterServicesForPublishStatus(prev, {
          serviceId,
          isPublished,
          freshService,
          publishedOnly,
          unpublishedOnly,
        }),
      );
      setSelectedService((prev) => {
        if (prev?.serviceId !== serviceId) return prev;
        return applyServicePublishPatch(
          prev,
          serviceId,
          isPublished,
          freshService,
        );
      });
    },
    [filterStatus, serverFilters, statusFilterColumnId],
  );

  useEffect(() => {
    if (!taskTypeFilterReady || !columnsQuery.isFetched) return;
    fetchServices();
  }, [fetchServices, taskTypeFilterReady, columnsQuery.isFetched]);

  /** AI4IDS-2949: block Create Service when the platform has no tiers. Edit remains allowed. */
  const isCreateServiceTabDisabled =
    !editingService && tiersLoaded && availableTiers.length === 0;

  // Sync URL tab param to activeTab.
  useEffect(() => {
    syncServicesTabFromQuery({
      query: router.query,
      isRegistryReadOnly,
      isCreateServiceTabDisabled,
      viewTabIndex,
      onCreateOpen,
      setActiveTab,
      bumpCreateRouteGen: () => {
        createRouteGenRef.current += 1;
      },
      clearCreateReturnTo: () => setCreateReturnTo(null),
      replace: (url, as, opts) => {
        void router.replace(url, as, opts);
      },
      replaceHref: (href) => {
        void router.replace(href);
      },
    });
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

  // Handle query parameters for pre-selecting model from model-management page.
  // Only `modelId` is removed. `returnTo` and `editServiceId` stay so Cancel and edit deep links survive.
  useEffect(() => {
    if (isRegistryReadOnly) return;
    const { modelId, tab } = router.query;
    if (!modelId || typeof modelId !== "string") return;
    if ((tab === "create" || tab === "1") && isCreateServiceTabDisabled) return;
    if (models.length === 0) return;

    const gen = createRouteGenRef.current;
    let cancelled = false;
    const isActive = () => !cancelled && gen === createRouteGenRef.current;
    const stripModelId = () =>
      stripModelIdQueryParam({
        isActive,
        pathname: routerRef.current.pathname,
        currentQuery: routerQueryRef.current,
        replace: (url, as, opts) => {
          void routerRef.current.replace(url, as, opts);
        },
      });

    void preselectModelFromQueryParam({
      modelId,
      models,
      isActive,
      currentFormModelId: formData.modelId,
      applyModel: handleModelNameChange,
      setPreselectedModel: setPreselectedModelFromQuery,
      stripModelId,
    });
    return () => {
      cancelled = true;
    };
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
    !isDeprecatedVersionStatus(preselectedModelFromQuery.versionStatus);
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
    if (!checkSessionExpiry()) return;
    if (!modelId) {
      setFormData(clearModelFormFields);
      return;
    }
    try {
      setIsLoadingModelDetails(true);
      const modelDetails = await getModelById(modelId);
      const modelVersion =
        modelDetails?.version || modelDetails?.modelVersion || "1.0";
      const modelSubmissionDate = formatModelSubmissionDate(
        modelDetails?.submittedOn ?? modelDetails?.submitted_on ?? "",
      );
      const modelName =
        modelDetails?.name ||
        modelDetails?.modelId ||
        modelDetails?.model_id ||
        "";
      const resolvedModelTaskType = resolveCatalogTaskType(
        resolveTaskType(modelDetails),
        taskTypeNames,
      );
      setFormData((prev) =>
        formDataAfterModelSelect({
          prev,
          modelId,
          modelName,
          modelSubmissionDate,
          modelVersion,
          resolvedModelTaskType,
          isEditing: Boolean(editingService),
        }),
      );
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
    setCachedInputPricePerUnit("");
    setOutputPricePerUnit("");
    setUnitSize("");
    setCurrency("INR");
    setSelectedTiers([]);
    setPreselectedModelFromQuery(null);
  };

  const openCreateModal = () => {
    if (isRegistryReadOnly || isCreateServiceTabDisabled) return;
    createRouteGenRef.current += 1;
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
    createRouteGenRef.current += 1;
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
    if (typeof raw !== "string") return;
    const path = safeFormReturnHref(raw);
    if (!path) return;
    setCreateReturnTo(path);
  }, [router.query.returnTo]);

  const formPrices = (): ServiceFormPrices => ({
    pricePerUnit,
    cachedInputPricePerUnit,
    outputPricePerUnit,
    unitSize,
    isLlmTaskType,
  });

  const alignFiltersAfterMutation = (options: {
    submittedTaskType: string;
    wasCreate: boolean;
  }): { listTaskType: string; listStatus: string } => {
    let listTaskType = filterTaskType;
    let listStatus = filterStatus;
    const serverTask = taskFilterColumnId
      ? serverFilters[taskFilterColumnId]
      : "";
    const serverStatus = statusFilterColumnId
      ? serverFilters[statusFilterColumnId]
      : "";
    const { submittedTaskType, wasCreate } = options;
    const activeTask = serverTask || filterTaskType;
    if (
      submittedTaskType &&
      activeTask &&
      submittedTaskType.toLowerCase() !== activeTask.toLowerCase()
    ) {
      listTaskType = submittedTaskType;
      setFilterTaskType(submittedTaskType);
      if (taskFilterColumnId) {
        setServerFilters((prev) => ({
          ...prev,
          [taskFilterColumnId]: submittedTaskType,
        }));
      }
      setRegistryPage(1);
    }
    if (
      wasCreate &&
      (filterStatus === "published" || serverStatus === "true")
    ) {
      listStatus = "";
      setFilterStatus("");
      if (statusFilterColumnId) {
        setServerFilters((prev) => ({
          ...prev,
          [statusFilterColumnId]: "",
        }));
      }
      setRegistryPage(1);
    }
    return { listTaskType, listStatus };
  };

  const refreshRegistryAfterMutation = async (options: {
    targetId: string;
    apiReturnedServiceId: string;
    submittedTaskType: string;
    wasCreate: boolean;
  }) => {
    const { targetId, apiReturnedServiceId, submittedTaskType, wasCreate } =
      options;
    if (!targetId) {
      await fetchServices({ silent: true });
      return;
    }
    if (apiReturnedServiceId) {
      try {
        upsertLocalService(await getServiceById(apiReturnedServiceId));
      } catch (err) {
        console.warn("Failed to refresh service after create/update:", err);
      }
    }
    const { listTaskType, listStatus } = alignFiltersAfterMutation({
      submittedTaskType,
      wasCreate,
    });
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
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!checkSessionExpiry()) return;

    setIsSubmitting(true);

    try {
      let mutatedServiceId = "";
      let apiReturnedServiceId = "";
      const submittedTaskType = (formData.task_type || "").trim();
      const wasCreate = !editingService;
      const prices = formPrices();

      if (editingService) {
        const updateData = buildServiceUpdatePayload({
          editingService,
          formData,
          prices,
          authToken,
          savedAuthTokenMask,
          selectedTiers,
        });
        const serviceId = updateData.serviceId || "";
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
        const serviceData = buildServiceCreatePayload({
          formData,
          prices,
          authToken,
          selectedTiers,
        });
        const created = await createService(serviceData);
        apiReturnedServiceId =
          created.serviceId || created.service_id || "";
        mutatedServiceId =
          apiReturnedServiceId || serviceData.serviceId || "";
        upsertLocalService({
          ...serviceData,
          serviceId: mutatedServiceId,
          name: created.name || serviceData.name,
          isPublished: false,
          task_type: formData.task_type,
        } as Service);
        showToast({
          type: "success",
          message: "Service has been created successfully.",
        });
      }

      invalidateServiceQueries();
      createRouteGenRef.current += 1;
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

      await refreshRegistryAfterMutation({
        targetId: mutatedServiceId,
        apiReturnedServiceId,
        submittedTaskType,
        wasCreate,
      });
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

  const filteredModelsForDropdown = useMemo(() => {
    const selectedTask = (formData.task_type || "").toLowerCase();
    if (!selectedTask) return modelsForDropdown;
    return modelsForDropdown.filter(
      (model) => resolveTaskType(model).toLowerCase() === selectedTask,
    );
  }, [formData.task_type, modelsForDropdown]);

  // Union the registry ids so a clash still shows while the unfiltered list loads.
  const existingServiceIds = useMemo(() => {
    const ids = new Set(fullServiceIds ?? []);
    for (const id of allServiceIdsQuery.data ?? []) ids.add(id);
    return ids;
  }, [fullServiceIds, allServiceIdsQuery.data]);

  const {
    pricePerUnitError,
    cachedInputPricePerUnitError,
    outputPricePerUnitError,
    serviceIdError,
    serviceDescriptionError,
    serviceNameError,
    hardwareDescriptionError,
    serviceIdLengthError,
    canCreateService,
    isCreateFormModelSelected,
  } = computeServiceFormGates({
    formData,
    editingService,
    isLlmTaskType,
    pricePerUnit,
    cachedInputPricePerUnit,
    outputPricePerUnit,
    unitSize,
    currency,
    selectedTiers,
    existingServiceIds,
    shouldValidateHardware: shouldValidateHardwareDescription(
      formData,
      editingService,
    ),
  });

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
        const cachedModel = (modelsQuery.data ?? []).find(
          (model) => model.modelId === modelId,
        );
        if (cachedModel) {
          setSelectedServiceModelDeprecated(
            isDeprecatedVersionStatus(cachedModel.versionStatus),
          );
        } else {
          try {
            const modelDetails = await getModelById(modelId);
            setSelectedServiceModelDeprecated(
              isDeprecatedVersionStatus(modelDetails?.versionStatus),
            );
          } catch {
            setSelectedServiceModelDeprecated(false);
          }
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
    if (!checkSessionExpiry()) return;
    try {
      onCreateClose();
      const service = await getServiceById(serviceId);
      const { formData: nextForm, tierIds, modelId } = editFormStateFromService(
        service,
        availableTiers,
      );
      setFormData(nextForm);
      const maskedAuthToken = resolveMaskedAuthToken(service);
      setAuthToken(maskedAuthToken);
      setSavedAuthTokenMask(maskedAuthToken);
      setHasAuthToken(Boolean(service.hasAuthToken));
      setPricePerUnit(
        service.costPerUnit != null ? String(service.costPerUnit) : "",
      );
      setCachedInputPricePerUnit(
        service.cachedInputCostPerUnit != null
          ? String(service.cachedInputCostPerUnit)
          : "",
      );
      setOutputPricePerUnit(
        service.outputCostPerUnit != null
          ? String(service.outputCostPerUnit)
          : "",
      );
      setUnitSize(service.unitSize != null ? String(service.unitSize) : "");
      setSelectedTiers(tierIds);
      setEditingService(service);
      setCreateFormEpoch((n) => n + 1);
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
        if (isDeprecatedVersionStatus(modelDetails?.versionStatus)) {
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
    totalServicesCount: serviceListUsesServer ? serverTotal : services.length,
    isLoading: isLoading || authLoading || columnsQuery.isLoading,
    // Remounts the client-paged table so pagination returns to page 1 on a filter change.
    tableKey: serviceListUsesServer
      ? `server-${registryEpoch}`
      : `${filterStatus}-${filterTaskType}-${filterTier}-${registryEpoch}`,
    serviceListCatalogue,
    serviceListUsesServer,
    registryPage,
    registryPageSize,
    setRegistryPage,
    setRegistryPageSize: (size: number) => {
      setRegistryPageSize(size);
      setRegistryPage(1);
    },
    serverFilters,
    setServerFilterValue,
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
    cachedInputPricePerUnit,
    setCachedInputPricePerUnit,
    cachedInputPricePerUnitError,
    outputPricePerUnit,
    setOutputPricePerUnit,
    outputPricePerUnitError,
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
