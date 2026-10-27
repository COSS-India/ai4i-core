// Logs Dashboard - View telemetry traces via unified traces/search API
// AI4IDS-3527: one search field applies as you type or on Enter; sort/page hit the API;
// nothing is searched, filtered or sorted in the browser.

import {
  Box,
  Button,
  Checkbox,
  FormControl,
  HStack,
  Switch,
  Text,
  Tooltip,
  VStack,
  Flex,
  IconButton,
  Card,
  CardBody,
  SimpleGrid,
  Stat,
  StatLabel,
  StatNumber,
  Alert,
  AlertIcon,
  AlertDescription,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  MenuDivider,
  Portal,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  RepeatIcon,
  CheckIcon,
  CloseIcon,
  ChevronDownIcon,
  SettingsIcon,
} from "@chakra-ui/icons";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import { useAuth, forceFrontendSessionEnd } from "../hooks/useAuth";
import { useRouter } from "next/router";
import { getTenantIdFromToken } from "../utils/helpers";
import {
  searchTelemetryTraces,
  getTelemetryTraceColumns,
  resolveTelemetryTenantId,
  TelemetryTraceRecord,
  TelemetryTraceSortBy,
} from "../services/observabilityService";
import { showToast } from "../utils/toast";
import {
  INSTITUTION,
  INSTITUTIONS,
  INSTITUTION_ARTICLE,
  isTenantStatus,
  TENANT,
  formatModelTaskTypeLabel,
} from "../config/constants";
import { useInferenceTypes } from "../hooks/useInferenceTypes";
import { useTenantsList } from "../hooks/useTenantsList";
import DataTable, {
  useAdminTableSurface,
  type DataTableColumn,
  type DataTableSortState,
} from "../components/common/table";
import TelemetryTraceDetailModal from "@/components/observability/TelemetryTraceDetailModal";
import { getPlatformName } from "../config/runtimeConfig";
import { FIELD_HINTS } from "../config/fieldHints";
import FieldLabel from "../components/common/FieldLabel";
import { isPlatformAdminUser, isTenantAdminUser, userHasRole } from "../utils/rbac";
import {
  AUTO_REFRESH_MS,
  DEFAULT_COLUMN_KEYS,
  FALLBACK_COLUMN_DEFS,
  SORTABLE_API_KEYS,
  buildColumnsQueryParam,
  convertToISOFormat,
  defaultTimeRange,
  formatDateTimeLocal,
  LOG_TIME_PRESETS,
  rangeForTimePreset,
  type LogTimePreset,
  formatMetadataCell,
  isAdminOnlyColumnKey,
  isFailureStatus,
  isSuccessStatus,
  KEYWORD_MAX_LENGTH,
  END_USER_MAX_LENGTH,
  normalizeColumnDefs,
  parseMetadataFilter,
  parseStatusCodeFilter,
  readStoredColumns,
  writeStoredColumns,
} from "../utils/logsDashboard";

const LOG_SEARCH_FIELDS = ["service", "statusCode", "endUser", "metadata"] as const;
type LogSearchField = (typeof LOG_SEARCH_FIELDS)[number];

type DraftFilters = {
  q: string;
  /** Comma-separated search fields. Empty means every field (keyword search). */
  searchScope: string;
  timePreset: LogTimePreset;
  taskType: string;
  level: string;
  serviceId: string;
  statusCode: string;
  endUser: string;
  metadata: string;
  startTime: string;
  endTime: string;
  selectedTenantId: string;
};

function selectedSearchFields(scope: string): Set<LogSearchField> {
  const selected = new Set<LogSearchField>();
  for (const part of scope.split(",")) {
    const field = part.trim();
    if ((LOG_SEARCH_FIELDS as readonly string[]).includes(field)) {
      selected.add(field as LogSearchField);
    }
  }
  return selected;
}

function withSearchText(draft: DraftFilters, value: string): DraftFilters {
  return { ...draft, q: value };
}

function searchFieldCopy(field: LogSearchField | undefined): { placeholder: string; hint: string } {
  if (field === "service") {
    return { placeholder: FIELD_HINTS.logs.service.placeholder, hint: FIELD_HINTS.logs.service.tip };
  }
  if (field === "statusCode") {
    return { placeholder: FIELD_HINTS.logs.statusCode.placeholder, hint: FIELD_HINTS.logs.statusCode.tip };
  }
  if (field === "endUser") {
    return { placeholder: FIELD_HINTS.logs.endUser.placeholder, hint: FIELD_HINTS.logs.endUser.tip };
  }
  if (field === "metadata") {
    return { placeholder: FIELD_HINTS.logs.metadata.placeholder, hint: FIELD_HINTS.logs.metadata.tip };
  }
  return { placeholder: FIELD_HINTS.logs.search.placeholder, hint: FIELD_HINTS.logs.search.tip };
}

function appliedFromDraft(next: DraftFilters): AppliedFilters | null {
  const text = next.q.trim();
  const fields = selectedSearchFields(next.searchScope);
  const searchingAll = fields.size === 0;
  const q = searchingAll ? text : "";
  const serviceId = fields.has("service") ? text : "";
  const endUser = fields.has("endUser") ? text : "";
  const metadataRaw = fields.has("metadata") ? text : "";
  const statusRaw = fields.has("statusCode") ? text : "";
  if (q.length > KEYWORD_MAX_LENGTH || endUser.length > END_USER_MAX_LENGTH) return null;
  const meta = parseMetadataFilter(metadataRaw);
  if (meta && "error" in meta) return null;
  const codes = parseStatusCodeFilter(statusRaw);
  if (codes && "error" in codes) return null;
  return {
    q,
    taskType: next.taskType,
    level: next.level,
    serviceId,
    statusCode: codes && "value" in codes ? codes.value : "",
    user: endUser,
    metadataKey: meta && "key" in meta ? meta.key : "",
    metadataValue: meta && "key" in meta ? meta.value : "",
    startTime: next.startTime,
    endTime: next.endTime,
    selectedTenantId: next.selectedTenantId,
  };
}

function sameApplied(left: AppliedFilters, right: AppliedFilters): boolean {
  return (Object.keys(left) as (keyof AppliedFilters)[]).every((key) => left[key] === right[key]);
}

type AppliedFilters = {
  q: string;
  taskType: string;
  level: string;
  serviceId: string;
  statusCode: string;
  user: string;
  metadataKey: string;
  metadataValue: string;
  startTime: string;
  endTime: string;
  selectedTenantId: string;
};

function traceStatusIcon(failed: boolean, ok: boolean): React.ReactNode {
  if (failed) {
    return <CloseIcon boxSize={2.5} color="red.500" aria-hidden />;
  }
  if (ok) {
    return <CheckIcon boxSize={3} color="green.500" aria-hidden />;
  }
  return (
    <Box
      as="span"
      w={2}
      h={2}
      borderRadius="full"
      bg="orange.400"
      aria-hidden
    />
  );
}

function traceStatusLabel(
  row: TelemetryTraceRecord,
  isAdmin: boolean,
): string {
  const statusText = row.status ?? "unknown";
  const failed = isFailureStatus(statusText);
  let label =
    failed && row.status_code != null
      ? `${statusText} (${row.status_code})`
      : statusText;
  if (failed && isAdmin && row.error) {
    label = `${label}: ${row.error}`;
  }
  return label;
}

function renderTraceStatusCell(
  row: TelemetryTraceRecord,
  isAdmin: boolean,
): React.ReactNode {
  const statusText = row.status ?? "unknown";
  const label = traceStatusLabel(row, isAdmin);
  return (
    <Tooltip label={label} placement="top" hasArrow>
      <Flex
        align="center"
        justify="center"
        w={5}
        h={5}
        aria-label={label}
        role="img"
      >
        {traceStatusIcon(
          isFailureStatus(statusText),
          isSuccessStatus(statusText),
        )}
      </Flex>
    </Tooltip>
  );
}

const LogsPage: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading, user } = useAuth();
  const { taskTypeNames, isLoading: isLoadingTaskTypes } = useInferenceTypes();

  const initialRange = useMemo(() => defaultTimeRange(), []);

  const [draft, setDraft] = useState<DraftFilters>({
    q: "",
    searchScope: "",
    timePreset: "custom",
    taskType: "",
    level: "",
    serviceId: "",
    statusCode: "",
    endUser: "",
    metadata: "",
    startTime: initialRange.startTime,
    endTime: initialRange.endTime,
    selectedTenantId: "",
  });

  const [applied, setApplied] = useState<AppliedFilters>({
    q: "",
    taskType: "",
    level: "",
    serviceId: "",
    statusCode: "",
    user: "",
    metadataKey: "",
    metadataValue: "",
    startTime: initialRange.startTime,
    endTime: initialRange.endTime,
    selectedTenantId: "",
  });

  const [taskTypeFilterReady, setTaskTypeFilterReady] = useState(false);
  const didInitTaskTypes = useRef(false);
  useEffect(() => {
    if (didInitTaskTypes.current || isLoadingTaskTypes) return;
    didInitTaskTypes.current = true;
    // Default task type is All (omit task_types) — do not auto-select the first type.
    setTaskTypeFilterReady(true);
  }, [isLoadingTaskTypes]);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);
  const [autoRefresh, setAutoRefresh] = useState(false);
  /**
   * True while the range is meant to end at "now" (default open, Refresh, Clear).
   * Cleared when the user edits End Time so auto-refresh stays available on the
   * default range instead of timing out against a pinned datetime-local value.
   */
  const [followsPresent, setFollowsPresent] = useState(true);
  const [sort, setSort] = useState<DataTableSortState>({
    key: "timestamp",
    direction: "desc",
  });
  const [selectedColumns, setSelectedColumns] = useState<string[]>(DEFAULT_COLUMN_KEYS);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [isTraceModalOpen, setIsTraceModalOpen] = useState(false);

  const isAdmin = isPlatformAdminUser(user?.roles);
  const isUser = userHasRole(user?.roles, "USER");
  const isGuest = userHasRole(user?.roles, "GUEST");
  const isTenantAdmin = isTenantAdminUser(user?.roles);
  const canPickTenant = isAdmin && !isTenantAdmin;
  const { cardBg, borderColor } = useAdminTableSurface();

  const authTenantId = useMemo(
    () => user?.tenant_id?.trim() || getTenantIdFromToken() || null,
    [user?.tenant_id]
  );

  const apiTenantId = useMemo(
    () =>
      resolveTelemetryTenantId({
        isAdmin,
        isTenantAdmin,
        selectedTenantId: applied.selectedTenantId,
        authTenantId,
      }),
    [isAdmin, isTenantAdmin, applied.selectedTenantId, authTenantId]
  );

  const searchFields = selectedSearchFields(draft.searchScope);
  const searchingAllFields = searchFields.size === 0;
  const keywordError =
    searchingAllFields && draft.q.trim().length > KEYWORD_MAX_LENGTH
      ? FIELD_HINTS.logs.search.tooLong
      : undefined;

  const trimmedSearch = draft.q.trim();
  const endUserError =
    searchFields.has("endUser") && trimmedSearch.length > END_USER_MAX_LENGTH
      ? FIELD_HINTS.logs.endUser.tooLong
      : undefined;
  const metadataFilter = useMemo(
    () => (searchFields.has("metadata") ? parseMetadataFilter(draft.q) : null),
    [draft.q, draft.searchScope],
  );
  const metadataError =
    metadataFilter && "error" in metadataFilter ? metadataFilter.error : undefined;
  const statusCodeFilter = useMemo(
    () => (searchFields.has("statusCode") ? parseStatusCodeFilter(draft.q) : null),
    [draft.q, draft.searchScope],
  );
  const statusCodeError =
    statusCodeFilter && "error" in statusCodeFilter ? statusCodeFilter.error : undefined;
  const searchError = searchingAllFields
    ? keywordError
    : endUserError || metadataError || statusCodeError;
  const onlySearchField = searchFields.size === 1 ? Array.from(searchFields)[0] : undefined;

  useEffect(() => {
    if (!followsPresent && autoRefresh) {
      setAutoRefresh(false);
    }
  }, [followsPresent, autoRefresh]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      showToast({
        type: "warning",
        message: "Please log in to view logs.",
      });
      router.push("/auth");
    }
  }, [isAuthenticated, authLoading, router]);

  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      if (isUser || isGuest) {
        showToast({
          type: "error",
          message: "You do not have permission to view logs.",
        });
        router.push("/");
        return;
      }
      if (isTenantAdmin && !authTenantId) {
        showToast({
          type: "error",
          message: `Your account is not linked to ${INSTITUTION_ARTICLE} ${INSTITUTION.toLowerCase()}. Contact an administrator.`,
        });
        router.push("/");
        return;
      }
      if (!authTenantId && !isAdmin) {
        showToast({
          type: "error",
          message: `You need to be assigned to ${INSTITUTION_ARTICLE} ${INSTITUTION.toLowerCase()} to view logs.`,
        });
        router.push("/");
      }
    }
  }, [
    isAuthenticated,
    authLoading,
    user,
    isUser,
    isGuest,
    isAdmin,
    isTenantAdmin,
    authTenantId,
    router,
  ]);

  const { data: tenantsData, isLoading: tenantsLoading, error: tenantsError } =
    useTenantsList({
      enabled: isAuthenticated && canPickTenant,
    });

  const activeTenants = useMemo(() => {
    if (!tenantsData?.tenants || !Array.isArray(tenantsData.tenants)) {
      return [];
    }
    return tenantsData.tenants.filter((tenant: { status?: string }) =>
      isTenantStatus(tenant?.status, TENANT.STATUS.ACTIVE)
    );
  }, [tenantsData]);

  const tenantById = useMemo(
    () => new Map(activeTenants.map((tenant) => [tenant.tenant_id, tenant])),
    [activeTenants]
  );

  const resolveTenantName = useCallback(
    (tenantId: string | null | undefined) => {
      if (!tenantId) return "-";
      const tenant = tenantById.get(tenantId);
      return tenant?.organisation || tenantId;
    },
    [tenantById]
  );

  const {
    data: columnsResponse,
    isFetched: columnsFetched,
  } = useQuery({
    queryKey: ["telemetry-traces-columns"],
    queryFn: async () => {
      try {
        return await getTelemetryTraceColumns();
      } catch {
        // Keep a contract-aligned fallback if /traces/columns is unreachable.
        return { columns: FALLBACK_COLUMN_DEFS };
      }
    },
    enabled: isAuthenticated && !isUser && !isGuest && !authLoading,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const columnDefs = useMemo(() => {
    const raw =
      columnsResponse?.columns && columnsResponse.columns.length > 0
        ? columnsResponse.columns
        : FALLBACK_COLUMN_DEFS;
    const normalized = normalizeColumnDefs(raw);
    // Error column is admin-only on the screen (AC-6); BE catalogue has no admin_only flag.
    return isAdmin
      ? normalized
      : normalized.filter((c) => !isAdminOnlyColumnKey(c.key));
  }, [columnsResponse, isAdmin]);

  // Hydrate once after auth + catalogue settle so admin-only columns (e.g. Error) are kept.
  const didHydrateColumns = useRef(false);
  useEffect(() => {
    if (didHydrateColumns.current) return;
    if (authLoading || !columnsFetched || columnsResponse === undefined) return;
    didHydrateColumns.current = true;
    const allowed = new Set(columnDefs.map((c) => c.key));
    const stored = readStoredColumns();
    const defaults = columnDefs.filter((c) => c.default).map((c) => c.key);
    const next =
      stored && stored.length > 0
        ? stored.filter((k) => allowed.has(k))
        : defaults;
    setSelectedColumns(next.length > 0 ? next : defaults);
  }, [authLoading, columnsFetched, columnsResponse, columnDefs]);

  const draftRef = useRef(draft);
  draftRef.current = draft;

  const commitFilters = useCallback((next: DraftFilters) => {
    const built = appliedFromDraft(next);
    if (!built) return;
    let changed = false;
    setApplied((prev) => {
      if (sameApplied(prev, built)) return prev;
      changed = true;
      return built;
    });
    if (changed) setPage(1);
  }, []);

  const replaceDraft = useCallback(
    (next: DraftFilters, commit = true) => {
      draftRef.current = next;
      setDraft(next);
      if (commit) commitFilters(next);
    },
    [commitFilters],
  );

  const clearAllFilters = useCallback(() => {
    const range = defaultTimeRange();
    const clearedDraft: DraftFilters = {
      q: "",
      searchScope: "",
      timePreset: "custom",
      taskType: "",
      level: "",
      serviceId: "",
      statusCode: "",
      endUser: "",
      metadata: "",
      startTime: range.startTime,
      endTime: range.endTime,
      selectedTenantId: "",
    };
    draftRef.current = clearedDraft;
    setDraft(clearedDraft);
    setApplied({
      q: "",
      taskType: "",
      level: "",
      serviceId: "",
      statusCode: "",
      user: "",
      metadataKey: "",
      metadataValue: "",
      startTime: range.startTime,
      endTime: range.endTime,
      selectedTenantId: "",
    });
    setSort({ key: "timestamp", direction: "desc" });
    setFollowsPresent(true);
    setPage(1);
  }, []);

  const sortBy: TelemetryTraceSortBy =
    SORTABLE_API_KEYS[sort.key] ?? "timestamp";
  const sortOrder = sort.direction;

  // Always request status_code so the status cell can show it on failures (AC-6).
  const columnsParam = useMemo(
    () =>
      buildColumnsQueryParam(
        selectedColumns,
        columnDefs.map((c) => c.key),
        { includeError: isAdmin }
      ),
    [selectedColumns, isAdmin, columnDefs]
  );

  const {
    data: tracesData,
    isLoading: tracesLoading,
    error: tracesError,
  } = useQuery({
    queryKey: [
      "telemetry-traces-search",
      applied,
      apiTenantId,
      isAdmin,
      isTenantAdmin,
      page,
      pageSize,
      sortBy,
      sortOrder,
      columnsParam,
    ],
    queryFn: () => {
      const apiStartDate =
        applied.startTime && applied.startTime.trim() !== ""
          ? convertToISOFormat(applied.startTime)
          : undefined;
      const apiEndDate =
        applied.endTime && applied.endTime.trim() !== ""
          ? convertToISOFormat(applied.endTime)
          : undefined;

      return searchTelemetryTraces({
        taskType:
          applied.taskType && applied.taskType.trim() !== ""
            ? applied.taskType
            : undefined,
        level:
          applied.level && applied.level.trim() !== ""
            ? applied.level
            : undefined,
        startDate: apiStartDate,
        endDate: apiEndDate,
        page,
        pageSize,
        tenant_id: apiTenantId,
        user: applied.user || undefined,
        metadataKey: applied.metadataKey || undefined,
        metadataValue: applied.metadataValue || undefined,
        q: applied.q || undefined,
        serviceId: applied.serviceId || undefined,
        statusCode: applied.statusCode || undefined,
        sortBy,
        sortOrder,
        columns: columnsParam || undefined,
      });
    },
    enabled:
      isAuthenticated &&
      (!isTenantAdmin || !!apiTenantId) &&
      taskTypeFilterReady,
    staleTime: 30 * 1000,
    // Default app retry is 1; skip for AC-17 narrow-range 400 so the costly
    // keyword pre-query (up to 20,001 trace IDs) does not run twice.
    retry: (count, err) =>
      count < 1 &&
      !(err as Error)?.message?.toLowerCase().includes("narrow"),
  });

  useEffect(() => {
    if (tracesError) {
      const error = tracesError as { message?: string };
      const message = error?.message || "Failed to load traces";
      if (
        message.toLowerCase().includes("unauthorized") ||
        message.toLowerCase().includes("forbidden")
      ) {
        forceFrontendSessionEnd();
        return;
      }
      // Narrow-range 400 is shown in the page Alert — skip a duplicate toast.
      if (message.toLowerCase().includes("narrow")) return;
      showToast({
        type: "error",
        message,
      });
    }
  }, [tracesError]);

  const handleRefresh = useCallback(() => {
    const now = new Date();
    const endSrc = applied.endTime || draft.endTime;
    const startSrc = applied.startTime || draft.startTime;

    if (startSrc && endSrc) {
      try {
        const startDate = new Date(startSrc);
        const endDate = new Date(endSrc);
        const timeRangeMs = endDate.getTime() - startDate.getTime();
        const nextEnd = formatDateTimeLocal(now);
        const nextStart = formatDateTimeLocal(
          new Date(now.getTime() - timeRangeMs)
        );
        setDraft((prev) => ({
          ...prev,
          startTime: nextStart,
          endTime: nextEnd,
        }));
        setApplied((prev) => ({
          ...prev,
          startTime: nextStart,
          endTime: nextEnd,
        }));
      } catch (error) {
        console.warn("Error parsing time range, updating endTime only:", error);
        const nextEnd = formatDateTimeLocal(now);
        setDraft((prev) => ({ ...prev, endTime: nextEnd }));
        setApplied((prev) => ({ ...prev, endTime: nextEnd }));
      }
    } else {
      const range = defaultTimeRange();
      setDraft((prev) => ({
        ...prev,
        startTime: range.startTime,
        endTime: range.endTime,
      }));
      setApplied((prev) => ({
        ...prev,
        startTime: range.startTime,
        endTime: range.endTime,
      }));
    }
    setFollowsPresent(true);
  }, [applied.endTime, applied.startTime, draft.endTime, draft.startTime]);

  const handleRefreshRef = useRef(handleRefresh);
  useEffect(() => {
    handleRefreshRef.current = handleRefresh;
  }, [handleRefresh]);

  useEffect(() => {
    if (!autoRefresh || !followsPresent) return;
    const refreshTimer = setInterval(() => {
      handleRefreshRef.current();
    }, AUTO_REFRESH_MS);
    return () => clearInterval(refreshTimer);
  }, [autoRefresh, followsPresent]);

  const formatTimestamp = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleString();
    } catch {
      return timestamp;
    }
  };

  const traceRows = tracesData?.data ?? [];
  const aggregationStats = tracesData?.aggregations;
  const successCount =
    tracesData?.summary?.success ?? aggregationStats?.by_level.success ?? 0;
  const failureCount =
    tracesData?.summary?.failure ?? aggregationStats?.by_level.failure ?? 0;

  const openTraceDetail = useCallback((traceId: string) => {
    if (!traceId?.trim()) return;
    setSelectedTraceId(traceId.trim());
    setIsTraceModalOpen(true);
  }, []);

  const closeTraceDetail = useCallback(() => {
    setIsTraceModalOpen(false);
    setSelectedTraceId(null);
  }, []);

  const applyColumnSelection = useCallback(
    (keys: string[]) => {
      const allowed = new Set(columnDefs.map((c) => c.key));
      const ordered = columnDefs
        .map((c) => c.key)
        .filter((k) => keys.includes(k) && allowed.has(k));
      // Never leave the table with zero data columns.
      if (ordered.length === 0) return;
      setSelectedColumns(ordered);
      writeStoredColumns(ordered);
    },
    [columnDefs]
  );

  const resetColumns = useCallback(() => {
    const defaults = columnDefs.filter((c) => c.default).map((c) => c.key);
    applyColumnSelection(defaults);
  }, [columnDefs, applyColumnSelection]);

  const handleSortChange = useCallback((next: DataTableSortState) => {
    // Only API-supported sorts; ignore non-sortable clicks.
    if (!SORTABLE_API_KEYS[next.key]) return;
    setSort(next);
    setPage(1);
  }, []);

  const renderStatusCell = useCallback(
    (row: TelemetryTraceRecord) => renderTraceStatusCell(row, isAdmin),
    [isAdmin],
  );

  const cellForColumn = useCallback(
    (key: string, row: TelemetryTraceRecord): React.ReactNode => {
      const plain = (value: React.ReactNode, opts?: { mono?: boolean; weight?: string }) => (
        <Text
          fontSize="sm"
          color="ink.700"
          fontWeight={opts?.weight}
          fontFamily={opts?.mono ? "mono" : undefined}
        >
          {value || "—"}
        </Text>
      );
      const cells: Record<string, () => React.ReactNode> = {
        timestamp: () => (
          <Text fontSize="sm" color="ink.600">
            {row.timestamp ? formatTimestamp(row.timestamp) : "—"}
          </Text>
        ),
        status: () => renderStatusCell(row),
        task_type: () => plain(row.task_type, { weight: "medium" }),
        url: () => (
          <Text
            fontSize="sm"
            color="ink.700"
            fontFamily="mono"
            noOfLines={1}
            title={row.url || undefined}
          >
            {row.url || "—"}
          </Text>
        ),
        institution: () => (
          <Text fontSize="sm" color="ink.600">
            {resolveTenantName(row.tenant_id)}
          </Text>
        ),
        status_code: () => plain(row.status_code ?? "—"),
        error: () => (
          <Text
            fontSize="sm"
            color={row.error ? "red.600" : "ink.500"}
            noOfLines={1}
            title={row.error || undefined}
          >
            {row.error || "—"}
          </Text>
        ),
        service: () => plain(row.service),
        model: () => plain(row.model),
        latency: () => plain(row.latency != null ? row.latency : "—"),
        application: () => plain(row.application, { mono: true }),
        api_key: () => plain(row.api_key, { mono: true }),
        end_user: () => plain(row.end_user),
        metadata: () => {
          const metadataText = formatMetadataCell(row.metadata);
          return (
            <Text
              fontSize="sm"
              color="ink.700"
              noOfLines={1}
              title={metadataText === "—" ? undefined : metadataText}
            >
              {metadataText}
            </Text>
          );
        },
        method: () => plain(row.method),
      };
      return (
        cells[key]?.() ?? (
          <Text fontSize="sm" color="ink.500">
            —
          </Text>
        )
      );
    },
    [renderStatusCell, resolveTenantName]
  );

  const traceColumns = useMemo((): DataTableColumn<TelemetryTraceRecord>[] => {
    const visible = columnDefs.filter((c) => selectedColumns.includes(c.key));
    return visible.map((def) => ({
      id: def.key,
      header: def.label,
      sortable: Boolean(def.sortable && SORTABLE_API_KEYS[def.key]),
      cell: (row) => cellForColumn(def.key, row),
    }));
  }, [columnDefs, selectedColumns, cellForColumn]);

  const hasAppliedFilters =
    applied.level !== "" ||
    (canPickTenant && applied.selectedTenantId !== "") ||
    applied.q !== "" ||
    applied.user !== "" ||
    applied.metadataKey !== "" ||
    applied.serviceId !== "" ||
    applied.statusCode !== "" ||
    applied.taskType !== "";

  const narrowRangeMessage =
    tracesError &&
    typeof (tracesError as Error).message === "string" &&
    (tracesError as Error).message.toLowerCase().includes("narrow")
      ? (tracesError as Error).message
      : null;

  return (
    <>
      <Head>
        <title>{`Logs Dashboard - ${getPlatformName()}`}</title>
        <meta
          name="description"
          content="View telemetry traces and request outcomes"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full" align="stretch">
          {!authLoading && isAuthenticated && (isUser || isGuest) ? (
            <Card
              bg={cardBg}
              border="1px"
              borderColor={borderColor}
              boxShadow="sm"
              w="full"
            >
              <CardBody>
                <Flex direction="column" align="center" justify="center" py={12}>
                  <Text
                    fontSize="lg"
                    color="ink.500"
                    fontWeight="medium"
                    mb={2}
                  >
                    Access Denied
                  </Text>
                  <Text fontSize="sm" color="ink.400" textAlign="center">
                    You do not have permission to view logs.
                  </Text>
                </Flex>
              </CardBody>
            </Card>
          ) : (
            <>
              <ManagementPageHeader
                title="Logs Dashboard"
                description="View telemetry traces and request outcomes"
              />

              {!authLoading && !isAuthenticated && (
                <Alert status="warning">
                  <AlertIcon />
                  <AlertDescription>
                    Please log in to view logs.{" "}
                    <Button
                      size="sm"
                      colorScheme="blue"
                      ml={4}
                      onClick={() => router.push("/auth")}
                    >
                      Log In
                    </Button>
                  </AlertDescription>
                </Alert>
              )}

              {tracesError && (
                <Alert status="error">
                  <AlertIcon />
                  <AlertDescription>
                    {narrowRangeMessage ||
                      (tracesError as Error)?.message ||
                      "Error loading traces"}
                  </AlertDescription>
                </Alert>
              )}

              {aggregationStats && (
                <SimpleGrid columns={{ base: 2, md: 3 }} spacing={4}>
                  <Card
                    bg={cardBg}
                    border="1px"
                    borderColor={borderColor}
                    boxShadow="sm"
                  >
                    <CardBody>
                      <Stat>
                        <StatLabel
                          fontSize="sm"
                          color="ink.600"
                          fontWeight="medium"
                        >
                          Total Requests
                        </StatLabel>
                        <StatNumber
                          fontSize="2xl"
                          fontWeight="bold"
                          color="ink.800"
                        >
                          {aggregationStats.total.toLocaleString()}
                        </StatNumber>
                      </Stat>
                    </CardBody>
                  </Card>
                  <Card
                    bg={cardBg}
                    border="1px"
                    borderColor="green.200"
                    boxShadow="sm"
                  >
                    <CardBody>
                      <Stat>
                        <StatLabel
                          fontSize="sm"
                          color="ink.600"
                          fontWeight="medium"
                        >
                          Success
                        </StatLabel>
                        <StatNumber
                          fontSize="2xl"
                          fontWeight="bold"
                          color="green.500"
                        >
                          {successCount.toLocaleString()}
                        </StatNumber>
                      </Stat>
                    </CardBody>
                  </Card>
                  <Card
                    bg={cardBg}
                    border="1px"
                    borderColor="red.200"
                    boxShadow="sm"
                  >
                    <CardBody>
                      <Stat>
                        <StatLabel
                          fontSize="sm"
                          color="ink.600"
                          fontWeight="medium"
                        >
                          Failures
                        </StatLabel>
                        <StatNumber
                          fontSize="2xl"
                          fontWeight="bold"
                          color="red.500"
                        >
                          {failureCount.toLocaleString()}
                        </StatNumber>
                      </Stat>
                    </CardBody>
                  </Card>
                </SimpleGrid>
              )}

              <DataTable
                layout="admin"
                items={traceRows}
                columns={traceColumns}
                getRowKey={(row) =>
                  `${row.trace_id}-${row.timestamp}-${row.task_type}-${row.url}`
                }
                sort={sort}
                onSortChange={handleSortChange}
                onRowClick={(row) => {
                  if (row.trace_id) openTraceDetail(row.trace_id);
                }}
                paginate="server"
                paginationPosition="bottom"
                serverPagination={{
                  page,
                  pageSize,
                  totalItems: tracesData?.total ?? 0,
                  onPageChange: setPage,
                  onPageSizeChange: (size) => {
                    setPageSize(size);
                    setPage(1);
                  },
                  pageSizeOptions: [10, 15, 25, 50, 100],
                }}
                isLoading={tracesLoading}
                loadingMessage="Loading traces..."
                emptyMessage={
                  narrowRangeMessage
                    ? FIELD_HINTS.logs.narrowDateRange
                    : "No traces found for the selected filters. Try adjusting the time range or removing filters."
                }
                noResultsMessage={
                  narrowRangeMessage
                    ? FIELD_HINTS.logs.narrowDateRange
                    : "No traces match the current filters."
                }
                hasActiveFilters={hasAppliedFilters}
                onClearFilters={clearAllFilters}
                search={{
                  label: "Search",
                  value: draft.q,
                  debounceMs: 400,
                  onChange: (v) => replaceDraft(withSearchText(draftRef.current, v)),
                  onSubmit: () => commitFilters(draftRef.current),
                  placeholder: searchFieldCopy(onlySearchField).placeholder,
                  hint: searchFieldCopy(onlySearchField).hint,
                  error: searchError,
                  width: { base: "full", sm: "240px" },
                }}
                filterDefs={[
                  {
                    id: "searchScope",
                    label: "Search in",
                    type: "multiselect",
                    value: draft.searchScope,
                    onChange: (v) =>
                      replaceDraft({ ...draftRef.current, searchScope: v }),
                    width: { base: "full", sm: "168px" },
                    options: [
                      { label: "All fields", value: "" },
                      { label: "Service", value: "service" },
                      { label: "Status code", value: "statusCode" },
                      { label: "End user", value: "endUser" },
                      { label: "Metadata", value: "metadata" },
                    ],
                  },
                  ...(canPickTenant
                    ? [
                        {
                          id: "tenant",
                          label: INSTITUTION,
                          type: "select" as const,
                          param: "tenant_id",
                          value: draft.selectedTenantId,
                          onChange: (v: string) =>
                            replaceDraft({ ...draftRef.current, selectedTenantId: v }),
                          hint: FIELD_HINTS.logs.tenant.tip,
                          width: { base: "full", sm: "180px" },
                          options: [
                            { label: `All ${INSTITUTIONS}`, value: "" },
                            ...(!tenantsLoading && !tenantsError
                              ? activeTenants.map(
                                  (tenant: {
                                    tenant_id: string;
                                    organisation?: string;
                                  }) => ({
                                    label:
                                      tenant.organisation || tenant.tenant_id,
                                    value: tenant.tenant_id,
                                  }),
                                )
                              : []),
                          ],
                        },
                      ]
                    : []),
                  {
                    id: "taskType",
                    label: "Task Type",
                    type: "select",
                    param: "task_types",
                    value: draft.taskType,
                    onChange: (v) => replaceDraft({ ...draftRef.current, taskType: v }),
                    width: { base: "full", sm: "150px" },
                    options: [
                      { label: "All", value: "" },
                      ...taskTypeNames.map((tt) => ({
                        label: formatModelTaskTypeLabel(tt),
                        value: tt,
                      })),
                    ],
                  },
                  {
                    id: "status",
                    label: "Status",
                    type: "select",
                    param: "level",
                    value: draft.level,
                    onChange: (v) => replaceDraft({ ...draftRef.current, level: v }),
                    width: { base: "full", sm: "132px" },
                    options: [
                      { label: "All Statuses", value: "" },
                      { label: "Success", value: "success" },
                      { label: "Failure", value: "failure" },
                    ],
                  },
                  {
                    id: "timePreset",
                    label: "Time range",
                    type: "select",
                    value: draft.timePreset,
                    onChange: (v) => {
                      if (v === "custom") {
                        replaceDraft({ ...draftRef.current, timePreset: "custom" }, false);
                        return;
                      }
                      const preset = v as Exclude<LogTimePreset, "custom">;
                      setFollowsPresent(true);
                      replaceDraft({
                        ...draftRef.current,
                        timePreset: preset,
                        ...rangeForTimePreset(preset),
                      });
                    },
                    width: { base: "full", sm: "156px" },
                    options: [
                      { label: "Custom", value: "custom" },
                      ...LOG_TIME_PRESETS.map((preset) => ({
                        label: preset.label,
                        value: preset.id,
                      })),
                    ],
                  },
                  {
                    id: "startTime",
                    label: "Start Time",
                    type: "date",
                    param: "start_time",
                    value: draft.startTime,
                    onChange: (v) =>
                      replaceDraft({ ...draftRef.current, timePreset: "custom", startTime: v }),
                    inputType: "datetime-local",
                    hint: FIELD_HINTS.logs.startTime.tip,
                    width: { base: "full", sm: "196px" },
                    cluster: "log-time",
                  },
                  {
                    id: "endTime",
                    label: "End Time",
                    type: "date",
                    param: "end_time",
                    value: draft.endTime,
                    onChange: (v) => {
                      setFollowsPresent(false);
                      replaceDraft({ ...draftRef.current, timePreset: "custom", endTime: v });
                    },
                    inputType: "datetime-local",
                    hint: FIELD_HINTS.logs.endTime.tip,
                    width: { base: "full", sm: "196px" },
                    cluster: "log-time",
                  },
                ]}
                filterToolbarRightContent={
                  <HStack spacing={3} flexWrap="wrap" align="center">
                    <Menu closeOnSelect={false}>
                      <Tooltip
                        label={FIELD_HINTS.logs.columns.tip}
                        placement="top"
                        hasArrow
                      >
                        <Box as="span" display="inline-block">
                          <MenuButton
                            as={Button}
                            size="sm"
                            variant="outline"
                            leftIcon={<SettingsIcon />}
                            rightIcon={<ChevronDownIcon />}
                          >
                            Columns
                          </MenuButton>
                        </Box>
                      </Tooltip>
                      <Portal>
                        <MenuList maxH="320px" overflowY="auto" minW="240px" py={2}>
                          <Text
                            px={3}
                            pb={1}
                            fontSize="xs"
                            color="ink.500"
                            fontWeight="medium"
                          >
                            {FIELD_HINTS.logs.columns.tip}
                          </Text>
                          {columnDefs.map((col) => {
                            const checked = selectedColumns.includes(col.key);
                            const onlyOne =
                              selectedColumns.length === 1 && checked;
                            return (
                              <MenuItem
                                as="div"
                                key={col.key}
                                closeOnSelect={false}
                                isDisabled={onlyOne}
                                onClick={() => {
                                  if (onlyOne) return;
                                  // Absolute next set (not flip) so a double-fired
                                  // click cannot cancel the selection.
                                  const next = checked
                                    ? selectedColumns.filter((k) => k !== col.key)
                                    : [...selectedColumns, col.key];
                                  applyColumnSelection(next);
                                }}
                                py={1.5}
                                cursor={onlyOne ? "not-allowed" : "pointer"}
                              >
                                <Checkbox
                                  isChecked={checked}
                                  isDisabled={onlyOne}
                                  pointerEvents="none"
                                  colorScheme="blue"
                                  mr={2}
                                >
                                  <Text as="span" fontSize="sm">
                                    {col.label}
                                    {col.default ? (
                                      <Text as="span" color="ink.400" ml={1}>
                                        (default)
                                      </Text>
                                    ) : null}
                                  </Text>
                                </Checkbox>
                              </MenuItem>
                            );
                          })}
                          <MenuDivider />
                          <MenuItem
                            onClick={resetColumns}
                            fontSize="sm"
                            color="blue.600"
                          >
                            Reset to default
                          </MenuItem>
                        </MenuList>
                      </Portal>
                    </Menu>
                    <FormControl display="flex" alignItems="center" w="auto">
                      <FieldLabel
                        hint={FIELD_HINTS.logs.autoRefresh.tip}
                        formLabelProps={{
                          htmlFor: "auto-refresh-toggle",
                          mb: 0,
                          fontSize: "sm",
                          fontWeight: "medium",
                          mr: 2,
                          whiteSpace: "nowrap",
                        }}
                      >
                        Auto-refresh
                      </FieldLabel>
                      <Tooltip
                        label={
                          followsPresent
                            ? FIELD_HINTS.logs.autoRefresh.tip
                            : "Available only while End Time is the present"
                        }
                        placement="top"
                        hasArrow
                      >
                        <Box display="inline-flex" alignItems="center">
                          <Switch
                            id="auto-refresh-toggle"
                            colorScheme="green"
                            isChecked={autoRefresh}
                            isDisabled={!followsPresent}
                            onChange={(e) => setAutoRefresh(e.target.checked)}
                          />
                        </Box>
                      </Tooltip>
                    </FormControl>
                    <Tooltip label="Refresh now" placement="top" hasArrow>
                      <IconButton
                        aria-label="Refresh"
                        icon={<RepeatIcon />}
                        onClick={handleRefresh}
                        isLoading={tracesLoading}
                        size="sm"
                        variant="outline"
                      />
                    </Tooltip>
                  </HStack>
                }
              />

              <TelemetryTraceDetailModal
                traceId={selectedTraceId}
                isOpen={isTraceModalOpen}
                onClose={closeTraceDetail}
              />
            </>
          )}
        </VStack>
      </ContentLayout>
    </>
  );
};

export default LogsPage;
