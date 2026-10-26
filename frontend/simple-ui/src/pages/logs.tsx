// Logs Dashboard - View telemetry traces via unified traces/search API
// AI4IDS-3527: keyword + filters apply on Search/Enter; sort/page hit the API;
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
  ViewIcon,
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
import FieldHint from "../components/common/FieldHint";
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

type DraftFilters = {
  q: string;
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

const LogsPage: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading, user } = useAuth();
  const { taskTypeNames, isLoading: isLoadingTaskTypes } = useInferenceTypes();

  const initialRange = useMemo(() => defaultTimeRange(), []);

  const [draft, setDraft] = useState<DraftFilters>({
    q: "",
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

  const keywordError =
    draft.q.trim().length > KEYWORD_MAX_LENGTH
      ? FIELD_HINTS.logs.search.tooLong
      : undefined;

  const trimmedEndUser = draft.endUser.trim();
  const endUserError =
    trimmedEndUser.length > END_USER_MAX_LENGTH
      ? FIELD_HINTS.logs.endUser.tooLong
      : undefined;
  const metadataFilter = useMemo(
    () => parseMetadataFilter(draft.metadata),
    [draft.metadata]
  );
  const metadataError =
    metadataFilter && "error" in metadataFilter ? metadataFilter.error : undefined;
  const statusCodeFilter = useMemo(
    () => parseStatusCodeFilter(draft.statusCode),
    [draft.statusCode]
  );
  const statusCodeError =
    statusCodeFilter && "error" in statusCodeFilter
      ? statusCodeFilter.error
      : undefined;

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

  const updateDraft = useCallback(
    <K extends keyof DraftFilters>(key: K, value: DraftFilters[K]) => {
      if (key === "endTime") {
        setFollowsPresent(false);
      }
      setDraft((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  const applyFilters = useCallback(() => {
    if (keywordError || endUserError || metadataError || statusCodeError) {
      return;
    }
    const meta =
      metadataFilter && "key" in metadataFilter ? metadataFilter : null;
    const codes =
      statusCodeFilter && "value" in statusCodeFilter
        ? statusCodeFilter.value
        : "";

    setApplied({
      q: draft.q.trim(),
      taskType: draft.taskType,
      level: draft.level,
      serviceId: draft.serviceId.trim(),
      statusCode: codes,
      user: endUserError ? "" : trimmedEndUser,
      metadataKey: meta?.key ?? "",
      metadataValue: meta?.value ?? "",
      startTime: draft.startTime,
      endTime: draft.endTime,
      selectedTenantId: draft.selectedTenantId,
    });
    setPage(1);
  }, [
    keywordError,
    endUserError,
    metadataError,
    statusCodeError,
    metadataFilter,
    statusCodeFilter,
    draft,
    trimmedEndUser,
  ]);

  const clearAllFilters = useCallback(() => {
    const range = defaultTimeRange();
    const clearedDraft: DraftFilters = {
      q: "",
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

  const filtersDirty = useMemo(() => {
    const appliedMeta =
      applied.metadataKey && applied.metadataValue
        ? `${applied.metadataKey}=${applied.metadataValue}`
        : "";
    const draftMeta =
      metadataFilter && "key" in metadataFilter
        ? `${metadataFilter.key}=${metadataFilter.value}`
        : draft.metadata.trim() === ""
          ? ""
          : draft.metadata.trim();
    const draftCodes =
      statusCodeFilter && "value" in statusCodeFilter
        ? statusCodeFilter.value
        : draft.statusCode.trim();

    return (
      draft.q.trim() !== applied.q ||
      draft.taskType !== applied.taskType ||
      draft.level !== applied.level ||
      draft.serviceId.trim() !== applied.serviceId ||
      draftCodes !== applied.statusCode ||
      trimmedEndUser !== applied.user ||
      draftMeta !== appliedMeta ||
      draft.startTime !== applied.startTime ||
      draft.endTime !== applied.endTime ||
      draft.selectedTenantId !== applied.selectedTenantId
    );
  }, [
    draft,
    applied,
    metadataFilter,
    statusCodeFilter,
    trimmedEndUser,
  ]);

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
    (row: TelemetryTraceRecord) => {
      const statusText = row.status ?? "unknown";
      const failed = isFailureStatus(statusText);
      const ok = isSuccessStatus(statusText);
      let label =
        failed && row.status_code != null
          ? `${statusText} (${row.status_code})`
          : statusText;
      // AC-6: admins see the error without opening the trace (tooltip on default view).
      if (failed && isAdmin && row.error) {
        label = `${label}: ${row.error}`;
      }
      const icon = failed ? (
        <CloseIcon boxSize={2.5} color="red.500" aria-hidden />
      ) : ok ? (
        <CheckIcon boxSize={3} color="green.500" aria-hidden />
      ) : (
        <Box
          as="span"
          w={2}
          h={2}
          borderRadius="full"
          bg="orange.400"
          aria-hidden
        />
      );

      return (
        <HStack spacing={2} align="center">
          <Tooltip label={label} placement="top" hasArrow>
            <Flex
              align="center"
              justify="center"
              w={5}
              h={5}
              aria-label={label}
              role="img"
            >
              {icon}
            </Flex>
          </Tooltip>
          {failed && row.status_code != null && (
            <Text fontSize="sm" color="red.600" fontWeight="medium">
              {row.status_code}
            </Text>
          )}
        </HStack>
      );
    },
    [isAdmin]
  );

  const cellForColumn = useCallback(
    (key: string, row: TelemetryTraceRecord): React.ReactNode => {
      switch (key) {
        case "timestamp":
          return (
            <Text fontSize="sm" color="ink.600">
              {row.timestamp ? formatTimestamp(row.timestamp) : "—"}
            </Text>
          );
        case "status":
          return renderStatusCell(row);
        case "task_type":
          return (
            <Text fontSize="sm" fontWeight="medium" color="ink.700">
              {row.task_type || "—"}
            </Text>
          );
        case "url":
          return (
            <Text
              noOfLines={2}
              maxW="400px"
              fontSize="sm"
              color="ink.700"
              fontFamily="mono"
            >
              {row.url || "—"}
            </Text>
          );
        case "institution":
          return (
            <Text fontSize="sm" color="ink.600">
              {resolveTenantName(row.tenant_id)}
            </Text>
          );
        case "status_code":
          return (
            <Text fontSize="sm" color="ink.700">
              {row.status_code ?? "—"}
            </Text>
          );
        case "error":
          return (
            <Text fontSize="sm" color="red.600" noOfLines={2} maxW="280px">
              {row.error || "—"}
            </Text>
          );
        case "service":
          return (
            <Text fontSize="sm" color="ink.700">
              {row.service || "—"}
            </Text>
          );
        case "model":
          return (
            <Text fontSize="sm" color="ink.700">
              {row.model || "—"}
            </Text>
          );
        case "latency":
          return (
            <Text fontSize="sm" color="ink.700">
              {row.latency != null ? row.latency : "—"}
            </Text>
          );
        case "application":
          return (
            <Text fontSize="sm" color="ink.700" fontFamily="mono">
              {row.application || "—"}
            </Text>
          );
        case "api_key":
          return (
            <Text fontSize="sm" color="ink.700" fontFamily="mono">
              {row.api_key || "—"}
            </Text>
          );
        case "end_user":
          return (
            <Text fontSize="sm" color="ink.700">
              {row.end_user || "—"}
            </Text>
          );
        case "metadata":
          return (
            <Text fontSize="sm" color="ink.700" noOfLines={2} maxW="240px">
              {formatMetadataCell(row.metadata)}
            </Text>
          );
        case "method":
          return (
            <Text fontSize="sm" color="ink.700">
              {row.method || "—"}
            </Text>
          );
        default:
          return (
            <Text fontSize="sm" color="ink.500">
              —
            </Text>
          );
      }
    },
    [renderStatusCell, resolveTenantName]
  );

  const traceColumns = useMemo((): DataTableColumn<TelemetryTraceRecord>[] => {
    const visible = columnDefs.filter((c) => selectedColumns.includes(c.key));
    const cols: DataTableColumn<TelemetryTraceRecord>[] = visible.map((def) => ({
      id: def.key,
      header: def.label,
      sortable: Boolean(def.sortable && SORTABLE_API_KEYS[def.key]),
      cell: (row) => cellForColumn(def.key, row),
    }));

    cols.push({
      id: "actions",
      header: "Actions",
      cell: (row) =>
        row.trace_id ? (
          <Tooltip label="View trace" placement="top" hasArrow>
            <IconButton
              aria-label="View trace"
              icon={<ViewIcon />}
              size="sm"
              variant="ghost"
              color="ink.700"
              _hover={{ color: "blue.500", bg: "blue.50" }}
              onClick={(e) => {
                e.stopPropagation();
                openTraceDetail(row.trace_id);
              }}
            />
          </Tooltip>
        ) : (
          <Text color="ink.400" fontSize="sm">
            —
          </Text>
        ),
    });

    return cols;
  }, [columnDefs, selectedColumns, cellForColumn, openTraceDetail]);

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
                  onChange: (v) => updateDraft("q", v),
                  onSubmit: applyFilters,
                  placeholder: FIELD_HINTS.logs.search.placeholder,
                  helper: FIELD_HINTS.logs.search.helper,
                  error: keywordError,
                }}
                filterDefs={[
                  ...(canPickTenant
                    ? [
                        {
                          id: "tenant",
                          label: INSTITUTION,
                          type: "select" as const,
                          param: "tenant_id",
                          value: draft.selectedTenantId,
                          onChange: (v: string) =>
                            updateDraft("selectedTenantId", v),
                          helper: FIELD_HINTS.logs.tenant.helper,
                          width: { base: "full", sm: "200px" },
                          options: [
                            { label: `All ${INSTITUTIONS}`, value: "" },
                            ...(tenantsLoading
                              ? []
                              : tenantsError
                                ? []
                                : activeTenants.map(
                                    (tenant: {
                                      tenant_id: string;
                                      organisation?: string;
                                    }) => ({
                                      label:
                                        tenant.organisation ||
                                        tenant.tenant_id,
                                      value: tenant.tenant_id,
                                    })
                                  )),
                          ],
                        },
                      ]
                    : []),
                  {
                    id: "taskType",
                    label: "Task Type",
                    type: "select",
                    param: "task_type",
                    value: draft.taskType,
                    onChange: (v) => updateDraft("taskType", v),
                    width: { base: "full", sm: "160px" },
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
                    onChange: (v) => updateDraft("level", v),
                    width: { base: "full", sm: "140px" },
                    options: [
                      { label: "All Statuses", value: "" },
                      { label: "Success", value: "success" },
                      { label: "Failure", value: "failure" },
                    ],
                  },
                  {
                    id: "service",
                    label: "Service",
                    type: "text",
                    param: "service_id",
                    value: draft.serviceId,
                    onChange: (v) => updateDraft("serviceId", v),
                    placeholder: FIELD_HINTS.logs.service.placeholder,
                    helper: FIELD_HINTS.logs.service.helper,
                    width: { base: "full", sm: "200px" },
                  },
                  {
                    id: "statusCode",
                    label: "Status Code",
                    type: "text",
                    param: "status_code",
                    value: draft.statusCode,
                    onChange: (v) => updateDraft("statusCode", v),
                    placeholder: FIELD_HINTS.logs.statusCode.placeholder,
                    helper: FIELD_HINTS.logs.statusCode.helper,
                    error: statusCodeError,
                    width: { base: "full", sm: "180px" },
                  },
                  {
                    id: "endUser",
                    label: "End User",
                    type: "text",
                    param: "user",
                    value: draft.endUser,
                    onChange: (v) => updateDraft("endUser", v),
                    placeholder: FIELD_HINTS.logs.endUser.placeholder,
                    helper: FIELD_HINTS.logs.endUser.helper,
                    error: endUserError,
                    width: { base: "full", sm: "200px" },
                  },
                  {
                    id: "metadata",
                    label: "Metadata",
                    type: "text",
                    param: "metadata_key, metadata_value",
                    value: draft.metadata,
                    onChange: (v) => updateDraft("metadata", v),
                    placeholder: FIELD_HINTS.logs.metadata.placeholder,
                    helper: FIELD_HINTS.logs.metadata.helper,
                    error: metadataError,
                    width: { base: "full", sm: "220px" },
                  },
                  {
                    id: "startTime",
                    label: "Start Time",
                    type: "date",
                    param: "start_time",
                    value: draft.startTime,
                    onChange: (v) => updateDraft("startTime", v),
                    inputType: "datetime-local",
                    helper: FIELD_HINTS.logs.startTime.helper,
                    width: { base: "full", sm: "220px" },
                  },
                  {
                    id: "endTime",
                    label: "End Time",
                    type: "date",
                    param: "end_time",
                    value: draft.endTime,
                    onChange: (v) => updateDraft("endTime", v),
                    inputType: "datetime-local",
                    helper: FIELD_HINTS.logs.endTime.helper,
                    width: { base: "full", sm: "220px" },
                  },
                ]}
                filterToolbarRightContent={
                  <HStack spacing={3} flexWrap="wrap" align="center">
                    <Tooltip
                      label={
                        keywordError ||
                        endUserError ||
                        metadataError ||
                        statusCodeError
                          ? "Fix validation errors before searching"
                          : filtersDirty
                            ? "Apply keyword and filters"
                            : "No changes to apply"
                      }
                      placement="top"
                      hasArrow
                    >
                      <Box as="span" display="inline-block">
                        <Button
                          size="sm"
                          colorScheme="blue"
                          variant={filtersDirty ? "solid" : "outline"}
                          onClick={applyFilters}
                          isDisabled={Boolean(
                            keywordError ||
                              endUserError ||
                              metadataError ||
                              statusCodeError
                          )}
                        >
                          Search
                        </Button>
                      </Box>
                    </Tooltip>
                    {filtersDirty && (
                      <Text fontSize="xs" color="ink.500" whiteSpace="nowrap">
                        Unapplied changes
                      </Text>
                    )}
                    <Menu closeOnSelect={false}>
                      <Tooltip
                        label={FIELD_HINTS.logs.columns.helper}
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
                            {FIELD_HINTS.logs.columns.helper}
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
                            ? FIELD_HINTS.logs.autoRefresh.helper
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
                      <FieldHint ml={2} mt={0}>
                        {FIELD_HINTS.logs.autoRefresh.helper}
                      </FieldHint>
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
                tableContainerProps={{ overflowX: "auto" }}
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
