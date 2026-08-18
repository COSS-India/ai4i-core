// Logs Dashboard - View telemetry traces via unified traces/search API

import {
  Box,
  Button,
  FormControl,
  FormLabel,
  HStack,
  Input,
  Switch,
  Text,
  Tooltip,
  VStack,
  Badge,
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
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { RepeatIcon, ViewIcon } from "@chakra-ui/icons";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import { useAuth, forceFrontendSessionEnd } from "../hooks/useAuth";
import { useRouter } from "next/router";
import { getTenantIdFromToken } from "../utils/helpers";
import {
  searchTelemetryTraces,
  resolveTelemetryTenantId,
  TelemetryTraceRecord,
} from "../services/observabilityService";
import { showToast } from "../utils/toast";
import { INSTITUTION, INSTITUTIONS, INSTITUTION_ARTICLE, isTenantStatus, TENANT, formatModelTaskTypeLabel } from "../config/constants";
import { useInferenceTypes } from "../hooks/useInferenceTypes";
import { listTenants } from "../services/tenantService";
import {
  useAdminTableSurface,
  TableSearchField,
  TableSelectField,
} from "../components/common/TableControls";
import AdminDataTable, {
  type AdminTableColumn,
} from "../components/common/AdminDataTable";
import TelemetryTraceDetailModal from "@/components/observability/TelemetryTraceDetailModal";
import { getPlatformName } from "../config/runtimeConfig";

/** Auto-refresh interval when enabled (within 30–45s range). */
const AUTO_REFRESH_MS = 37_000;

/**
 * Convert datetime-local format (YYYY-MM-DDTHH:mm) to ISO format (YYYY-MM-DDTHH:mm:ss.sssZ)
 * This ensures the timestamp is properly formatted for OpenSearch queries
 */
const convertToISOFormat = (datetimeLocal: string): string => {
  if (!datetimeLocal || datetimeLocal.trim() === "") {
    return "";
  }

  // Parse the datetime-local string (YYYY-MM-DDTHH:mm)
  // Treat it as local time and convert to ISO format
  try {
    // If the string doesn't have seconds, add :00
    let normalized = datetimeLocal;
    if (!normalized.includes(":")) {
      return ""; // Invalid format
    }

    // Count colons to determine format
    const colonCount = (normalized.match(/:/g) || []).length;
    if (colonCount === 1) {
      // Format: YYYY-MM-DDTHH:mm - add seconds
      normalized = normalized + ":00";
    }

    // Parse as local time and convert to ISO (UTC)
    const date = new Date(normalized);
    if (Number.isNaN(date.getTime())) {
      console.warn(`Invalid datetime format: ${datetimeLocal}`);
      return "";
    }

    // Return ISO format string
    return date.toISOString();
  } catch (error) {
    console.error(`Error converting datetime to ISO: ${datetimeLocal}`, error);
    return "";
  }
};

const LogsPage: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading, user } = useAuth();
  // Task-type filter options come from the enabled set (ENABLED_TASK_TYPES),
  // not a hardcoded list, so disabled types don't appear here either.
  const { taskTypeNames, isLoading: isLoadingTaskTypes } = useInferenceTypes();

  const [taskType, setTaskType] = useState<string>("");
  const didInitTaskTypeFilter = useRef(false);
  const [taskTypeFilterReady, setTaskTypeFilterReady] = useState(false);
  useEffect(() => {
    if (didInitTaskTypeFilter.current || isLoadingTaskTypes) return;
    didInitTaskTypeFilter.current = true;
    if (taskTypeNames.length > 0) setTaskType(taskTypeNames[0]);
    setTaskTypeFilterReady(true);
  }, [isLoadingTaskTypes, taskTypeNames]);
  const [level, setLevel] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [startTime, setStartTime] = useState<string>("");
  const [endTime, setEndTime] = useState<string>("");
  const [selectedTenantId, setSelectedTenantId] = useState<string>("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [isTraceModalOpen, setIsTraceModalOpen] = useState(false);

  // Check if user is admin (full ADMIN role — sees all tenants)
  const isAdmin = user?.roles?.includes('ADMIN') || false;
  // Check if user has USER role - hide logs UI for them
  const isUser = user?.roles?.includes('USER') || false;
  // Check if user has GUEST role - hide logs UI for them
  const isGuest = user?.roles?.includes('GUEST') || false;
  // Check if user is a TENANT ADMIN — scoped to their own tenant only
  const isTenantAdmin = user?.roles?.includes('TENANT ADMIN') || false;
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
        selectedTenantId,
        authTenantId,
      }),
    [isAdmin, isTenantAdmin, selectedTenantId, authTenantId]
  );

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      showToast({
        type: "warning",
        message: "Please log in to view logs.",
      });
      router.push("/auth");
    }
  }, [isAuthenticated, authLoading, router]);

  // Redirect if user has USER or GUEST role or doesn't have tenant_id (but allow admins)
  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      // Hide logs for users with USER or GUEST role
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
  }, [isAuthenticated, authLoading, user, isUser, isGuest, isAdmin, isTenantAdmin, authTenantId, router]);

  // Fetch tenants list (for all admins - ADMIN or SUPER_ADMIN role)
  const { data: tenantsData, isLoading: tenantsLoading, error: tenantsError } = useQuery({
    queryKey: ["tenants-list"],
    queryFn: () => listTenants(),
    enabled: isAuthenticated && canPickTenant,
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: 1, // Retry once on failure
  });

  // Fetch the current tenant's detail (subscriptions) for TENANT ADMIN role
  // Filter tenants to only show active tenants
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

  // Unified traces/search (list + aggregations in one response)
  const {
    data: tracesData,
    isLoading: tracesLoading,
    error: tracesError,
  } = useQuery({
    queryKey: [
      "telemetry-traces-search",
      taskType,
      level,
      startTime,
      endTime,
      apiTenantId,
      isAdmin,
      isTenantAdmin,
      page,
      pageSize,
    ],
    queryFn: () => {
      const apiStartDate =
        startTime && startTime.trim() !== "" ? convertToISOFormat(startTime) : undefined;
      const apiEndDate =
        endTime && endTime.trim() !== "" ? convertToISOFormat(endTime) : undefined;

      return searchTelemetryTraces({
        taskType: taskType && taskType.trim() !== "" ? taskType : undefined,
        level: level && level.trim() !== "" ? level : undefined,
        startDate: apiStartDate,
        endDate: apiEndDate,
        page,
        pageSize,
        tenant_id: apiTenantId,
      });
    },
    enabled: isAuthenticated && (!isTenantAdmin || !!apiTenantId) && taskTypeFilterReady,
    staleTime: 30 * 1000,
  });

  // Handle traces error
  useEffect(() => {
    if (tracesError) {
      const error = tracesError as { message?: string };
      const message = error?.message || "Failed to load traces";
      if (message.toLowerCase().includes("unauthorized") || message.toLowerCase().includes("forbidden")) {
        forceFrontendSessionEnd();
        return;
      }
      showToast({
        type: "error",
        message,
      });
    }
  }, [tracesError]);

  // Set default time range (last 1 hour) on initial load
  useEffect(() => {
    if (!startTime && !endTime) {
      const now = new Date();
      const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
      // Format as YYYY-MM-DDTHH:mm for datetime-local input
      const formatDateTime = (date: Date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}`;
      };
      const formattedNow = formatDateTime(now);
      const formattedOneHourAgo = formatDateTime(oneHourAgo);
      setEndTime(formattedNow);
      setStartTime(formattedOneHourAgo);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRefresh = useCallback(() => {
    // Update time range to include latest logs
    const now = new Date();
    const formatDateTime = (date: Date) => {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');
      return `${year}-${month}-${day}T${hours}:${minutes}`;
    };

    if (startTime && endTime) {
      try {
        const startDate = new Date(startTime);
        const endDate = new Date(endTime);
        const timeRangeMs = endDate.getTime() - startDate.getTime();
        setEndTime(formatDateTime(now));
        setStartTime(formatDateTime(new Date(now.getTime() - timeRangeMs)));
      } catch (error) {
        console.warn("Error parsing time range, updating endTime only:", error);
        setEndTime(formatDateTime(now));
      }
    } else {
      const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
      setEndTime(formatDateTime(now));
      setStartTime(formatDateTime(oneHourAgo));
    }
  }, [startTime, endTime]);

  const handleRefreshRef = useRef(handleRefresh);
  useEffect(() => {
    handleRefreshRef.current = handleRefresh;
  }, [handleRefresh]);

  // Auto-refresh: shift time window and refetch on the same interval as manual Refresh
  useEffect(() => {
    if (!autoRefresh) return;
    const refreshTimer = setInterval(() => {
      handleRefreshRef.current();
    }, AUTO_REFRESH_MS);
    return () => clearInterval(refreshTimer);
  }, [autoRefresh]);

  const clearAllFilters = () => {
    if (taskTypeNames.length > 0) setTaskType(taskTypeNames[0]);
    setLevel("");
    setSearchQuery("");
    setSelectedTenantId("");
    const now = new Date();
    const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
    const formatDateTime = (date: Date) => {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      const hours = String(date.getHours()).padStart(2, "0");
      const minutes = String(date.getMinutes()).padStart(2, "0");
      return `${year}-${month}-${day}T${hours}:${minutes}`;
    };
    setEndTime(formatDateTime(now));
    setStartTime(formatDateTime(oneHourAgo));
    setPage(1);
  };

  const getStatusColor = (status: string) => {
    const statusLower = status.toLowerCase();
    if (statusLower === "fail" || statusLower === "failure" || statusLower === "error") {
      return "red";
    }
    if (statusLower === "success") return "green";
    if (statusLower === "unknown") return "orange";
    return "gray";
  };

  const formatTimestamp = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleString();
    } catch {
      return timestamp;
    }
  };

  const traceRows = tracesData?.data ?? [];

  const displayedTraceRows = useMemo(() => {
    if (!debouncedSearch) return traceRows;
    const q = debouncedSearch.toLowerCase();
    return traceRows.filter(
      (row) =>
        row.trace_id.toLowerCase().includes(q) ||
        (row.url ?? "").toLowerCase().includes(q) ||
        (row.task_type ?? "").toLowerCase().includes(q) ||
        row.status.toLowerCase().includes(q)
    );
  }, [traceRows, debouncedSearch]);

  const aggregationStats = tracesData?.aggregations;

  const openTraceDetail = useCallback((traceId: string) => {
    if (!traceId?.trim()) return;
    setSelectedTraceId(traceId.trim());
    setIsTraceModalOpen(true);
  }, []);

  const closeTraceDetail = useCallback(() => {
    setIsTraceModalOpen(false);
    setSelectedTraceId(null);
  }, []);

  const traceColumns = useMemo((): AdminTableColumn<TelemetryTraceRecord>[] => {
    return [
      {
        id: "timestamp",
        header: "Timestamp",
        thProps: { fontWeight: "semibold", color: "gray.700", py: 3 },
        cell: (row) => (
          <Text fontSize="sm" color="gray.600" py={3}>
            {formatTimestamp(row.timestamp)}
          </Text>
        ),
      },
      {
        id: "status",
        header: "Status",
        thProps: { fontWeight: "semibold", color: "gray.700" },
        cell: (row) => (
          <Badge
            colorScheme={getStatusColor(row.status)}
            fontSize="xs"
            px={2}
            py={1}
            borderRadius="md"
            fontWeight="semibold"
          >
            {row.status}
          </Badge>
        ),
      },
      {
        id: "task_type",
        header: "Task Type",
        thProps: { fontWeight: "semibold", color: "gray.700" },
        cell: (row) => (
          <Text fontSize="sm" fontWeight="medium" color="gray.700">
            {row.task_type || "—"}
          </Text>
        ),
      },
      {
        id: "url",
        header: "URL",
        thProps: { fontWeight: "semibold", color: "gray.700" },
        cell: (row) => (
          <Text noOfLines={2} maxW="400px" fontSize="sm" color="gray.700" fontFamily="mono">
            {row.url}
          </Text>
        ),
      },
      {
        id: "tenant_id",
        header: INSTITUTION,
        thProps: { fontWeight: "semibold", color: "gray.700" },
        cell: (row) => (
          <Text fontSize="sm" color="gray.600">
            {resolveTenantName(row.tenant_id)}
          </Text>
        ),
      },
      {
        id: "actions",
        header: "Actions",
        thProps: { fontWeight: "semibold", color: "gray.700" },
        cell: (row) =>
          row.trace_id ? (
            <Tooltip label="View trace" placement="top" hasArrow>
              <IconButton
                aria-label="View trace"
                icon={<ViewIcon />}
                size="sm"
                variant="ghost"
                color="gray.700"
                _hover={{ color: "blue.500", bg: "blue.50" }}
                onClick={(e) => {
                  e.stopPropagation();
                  openTraceDetail(row.trace_id);
                }}
              />
            </Tooltip>
          ) : (
            <Text color="gray.400" fontSize="sm">
              —
            </Text>
          ),
      },
    ];
  }, [openTraceDetail, resolveTenantName]);

  const hasAppliedFilters =
    level !== "" ||
    (canPickTenant && selectedTenantId !== "") ||
    searchQuery.trim() !== "";

  return (
    <>
      <Head>
        <title>{`Logs Dashboard - ${getPlatformName()}`}</title>
        <meta name="description" content="View telemetry traces and request outcomes" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full" align="stretch">
          {/* Hide logs UI for users with USER or GUEST role */}
          {!authLoading && isAuthenticated && (isUser || isGuest) ? (
            <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
              <CardBody>
                <Flex direction="column" align="center" justify="center" py={12}>
                  <Text fontSize="lg" color="gray.500" fontWeight="medium" mb={2}>
                    Access Denied
                  </Text>
                  <Text fontSize="sm" color="gray.400" textAlign="center">
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

              {/* Show auth warning if not authenticated */}
              {!authLoading && !isAuthenticated && (
                <Alert status="warning">
                  <AlertIcon />
                  <AlertDescription>
                    Please log in to view logs. <Button
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
                    {((tracesError as Error)?.message) || "Error loading traces"}
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
                _hover={{ boxShadow: "md", transform: "translateY(-2px)" }}
                transition="all 0.2s"
              >
                <CardBody>
                  <Stat>
                    <StatLabel fontSize="sm" color="gray.600" fontWeight="medium">Total Requests</StatLabel>
                    <StatNumber fontSize="2xl" fontWeight="bold" color="gray.800">
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
                _hover={{ boxShadow: "md", transform: "translateY(-2px)", borderColor: "green.300" }}
                transition="all 0.2s"
              >
                <CardBody>
                  <Stat>
                    <StatLabel fontSize="sm" color="gray.600" fontWeight="medium">Success</StatLabel>
                    <StatNumber fontSize="2xl" fontWeight="bold" color="green.500">
                      {aggregationStats.by_level.success.toLocaleString()}
                    </StatNumber>
                  </Stat>
                </CardBody>
              </Card>
              <Card
                bg={cardBg}
                border="1px"
                borderColor="red.200"
                boxShadow="sm"
                _hover={{ boxShadow: "md", transform: "translateY(-2px)", borderColor: "red.300" }}
                transition="all 0.2s"
              >
                <CardBody>
                  <Stat>
                    <StatLabel fontSize="sm" color="gray.600" fontWeight="medium">Failures</StatLabel>
                    <StatNumber fontSize="2xl" fontWeight="bold" color="red.500">
                      {aggregationStats.by_level.failure.toLocaleString()}
                    </StatNumber>
                  </Stat>
                </CardBody>
              </Card>
            </SimpleGrid>
              )}

              <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
            <CardBody>
              {!tracesError && (
                <>
                  <AdminDataTable
                    items={displayedTraceRows}
                    columns={traceColumns}
                    getRowKey={(row) =>
                      `${row.trace_id}-${row.timestamp}-${row.task_type}-${row.url}`
                    }
                    onRowClick={(row) => {
                      if (row.trace_id) openTraceDetail(row.trace_id);
                    }}
                    paginate="server"
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
                    size="md"
                    isLoading={tracesLoading}
                    loadingMessage="Loading traces..."
                    emptyMessage="No traces found for the selected filters. Try adjusting the time range or removing filters."
                    noResultsMessage="No traces match the current filters."
                    hasActiveFilters={hasAppliedFilters}
                    onClearFilters={clearAllFilters}
                    filters={
                      <VStack align="stretch" spacing={3} flex="1" w="full">
                        <HStack spacing={3} align="flex-end" flexWrap="wrap" rowGap={3} w="full">
                          <TableSearchField
                            label="Search"
                            value={searchQuery}
                            onChange={setSearchQuery}
                            placeholder="Trace ID, URL, task type…"
                            formControlProps={{ w: { base: "full", md: "280px" } }}
                          />
                          {canPickTenant && (
                            <TableSelectField
                              label={INSTITUTION}
                              value={selectedTenantId}
                              onChange={setSelectedTenantId}
                              formControlProps={{ w: { base: "full", sm: "200px" } }}
                              selectProps={{ isDisabled: tenantsLoading }}
                            >
                              <option value="">All {INSTITUTIONS}</option>
                              {tenantsLoading ? (
                                <option value="" disabled>
                                  Loading {INSTITUTIONS.toLowerCase()}…
                                </option>
                              ) : tenantsError ? (
                                <option value="" disabled>
                                  Error loading {INSTITUTIONS.toLowerCase()}
                                </option>
                              ) : activeTenants.length > 0 ? (
                                activeTenants.map(
                                  (tenant: { tenant_id: string; organisation?: string }) => (
                                    <option key={tenant.tenant_id} value={tenant.tenant_id}>
                                      {tenant.organisation || tenant.tenant_id}
                                    </option>
                                  )
                                )
                              ) : (
                                <option value="" disabled>
                                  No active {INSTITUTIONS.toLowerCase()}
                                </option>
                              )}
                            </TableSelectField>
                          )}
                          <TableSelectField
                            label="Task Type"
                            value={taskType}
                            onChange={setTaskType}
                            formControlProps={{ w: { base: "full", sm: "160px" } }}
                          >
                            {taskTypeNames.map((tt) => (
                              <option key={tt} value={tt}>
                                {formatModelTaskTypeLabel(tt)}
                              </option>
                            ))}
                          </TableSelectField>
                          <TableSelectField
                            label="Status"
                            value={level}
                            onChange={setLevel}
                            formControlProps={{ w: { base: "full", sm: "140px" } }}
                          >
                            <option value="">All Statuses</option>
                            <option value="success">Success</option>
                            <option value="failure">Failure</option>
                          </TableSelectField>
                          <FormControl w={{ base: "full", sm: "220px" }}>
                            <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
                              Start Time
                            </FormLabel>
                            <Input
                              type="datetime-local"
                              size="sm"
                              value={startTime}
                              onChange={(e) => {
                                setStartTime(e.target.value);
                                setPage(1);
                              }}
                              bg={cardBg}
                            />
                          </FormControl>
                          <FormControl w={{ base: "full", sm: "220px" }}>
                            <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
                              End Time
                            </FormLabel>
                            <Input
                              type="datetime-local"
                              size="sm"
                              value={endTime}
                              onChange={(e) => {
                                setEndTime(e.target.value);
                                setPage(1);
                              }}
                              bg={cardBg}
                            />
                          </FormControl>
                          <Box flex="1" minW={0} display={{ base: "none", lg: "block" }} />
                        </HStack>
                      </VStack>
                    }
                    filterToolbarAlign="flex-end"
                    filterToolbarRightContent={
                      <HStack spacing={3} flexWrap="wrap">
                        <FormControl display="flex" alignItems="center" w="auto">
                          <FormLabel
                            htmlFor="auto-refresh-toggle"
                            mb="0"
                            fontSize="sm"
                            fontWeight="medium"
                            mr={2}
                            whiteSpace="nowrap"
                          >
                            Auto-refresh
                          </FormLabel>
                          <Switch
                            id="auto-refresh-toggle"
                            colorScheme="green"
                            isChecked={autoRefresh}
                            onChange={(e) => setAutoRefresh(e.target.checked)}
                          />
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
                </>
              )}
            </CardBody>
              </Card>

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
