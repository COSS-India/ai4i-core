// Logs Dashboard - View telemetry traces via unified traces/search API

import {
  Alert,
  AlertDescription,
  AlertIcon,
  Button,
  Card,
  CardBody,
  Flex,
  Text,
  VStack,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import { useAdminTableSurface } from "../components/common/TableControls";
import LogsAggregationStats from "../components/logs/LogsAggregationStats";
import LogsTable from "../components/logs/LogsTable";
import {
  AUTO_REFRESH_MS,
  convertToISOFormat,
  getDefaultTimeRange,
  shiftTimeRangeToNow,
} from "../components/logs/logsUtils";
import TelemetryTraceDetailModal from "@/components/observability/TelemetryTraceDetailModal";
import { isTenantStatus, TENANT } from "../config/constants";
import { useAuth, forceFrontendSessionEnd } from "../hooks/useAuth";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";
import {
  searchTelemetryTraces,
  resolveTelemetryTenantId,
} from "../services/observabilityService";
import { listTenants } from "../services/tenantService";
import { getTenantIdFromToken } from "../utils/helpers";

const LogsPage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading, user } = useAuth();

  const [taskType, setTaskType] = useState("");
  const [level, setLevel] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [selectedTenantId, setSelectedTenantId] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [isTraceModalOpen, setIsTraceModalOpen] = useState(false);

  const isAdmin = user?.roles?.includes("ADMIN") || false;
  const isUser = user?.roles?.includes("USER") || false;
  const isGuest = user?.roles?.includes("GUEST") || false;
  const isTenantAdmin = user?.roles?.includes("TENANT ADMIN") || false;
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

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      toast({
        title: "Authentication Required",
        description: "Please log in to view logs.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      router.push("/auth");
    }
  }, [isAuthenticated, authLoading, router, toast]);

  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      if (isUser || isGuest) {
        toast({
          title: "Access Denied",
          description: "You do not have permission to view logs.",
          status: "error",
          duration: 5000,
          isClosable: true,
        });
        router.push("/");
        return;
      }
      if (isTenantAdmin && !authTenantId) {
        toast({
          title: "Access Denied",
          description: "Your account is not linked to a tenant. Contact an administrator.",
          status: "error",
          duration: 5000,
          isClosable: true,
        });
        router.push("/");
        return;
      }
      if (!authTenantId && !isAdmin) {
        toast({
          title: "Access Denied",
          description: "You need to be assigned to a tenant to view logs.",
          status: "error",
          duration: 5000,
          isClosable: true,
        });
        router.push("/");
      }
    }
  }, [
    isAuthenticated,
    authLoading,
    isUser,
    isGuest,
    isAdmin,
    isTenantAdmin,
    authTenantId,
    router,
    toast,
  ]);

  const {
    data: tenantsData,
    isLoading: tenantsLoading,
    error: tenantsError,
  } = useQuery({
    queryKey: ["tenants-list"],
    queryFn: () => listTenants(),
    enabled: isAuthenticated && canPickTenant,
    staleTime: 5 * 60 * 1000,
    retry: 1,
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
    enabled: isAuthenticated && (!isTenantAdmin || !!apiTenantId),
    staleTime: 30 * 1000,
  });

  useEffect(() => {
    if (tracesError) {
      const error = tracesError as { message?: string };
      const message = error?.message || "Failed to load traces";
      if (message.toLowerCase().includes("unauthorized") || message.toLowerCase().includes("forbidden")) {
        forceFrontendSessionEnd();
        return;
      }
      toast({
        title: "Error Loading Traces",
        description: message,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  }, [tracesError, toast]);

  useEffect(() => {
    if (!startTime && !endTime) {
      const { startTime: defaultStart, endTime: defaultEnd } = getDefaultTimeRange();
      setStartTime(defaultStart);
      setEndTime(defaultEnd);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRefresh = useCallback(() => {
    const shifted = shiftTimeRangeToNow(startTime, endTime);
    setStartTime(shifted.startTime);
    setEndTime(shifted.endTime);
  }, [startTime, endTime]);

  const handleRefreshRef = useRef(handleRefresh);
  useEffect(() => {
    handleRefreshRef.current = handleRefresh;
  }, [handleRefresh]);

  useEffect(() => {
    if (!autoRefresh) return;
    const refreshTimer = setInterval(() => {
      handleRefreshRef.current();
    }, AUTO_REFRESH_MS);
    return () => clearInterval(refreshTimer);
  }, [autoRefresh]);

  const clearAllFilters = () => {
    setTaskType("");
    setLevel("");
    setSearchQuery("");
    setSelectedTenantId("");
    const { startTime: defaultStart, endTime: defaultEnd } = getDefaultTimeRange();
    setStartTime(defaultStart);
    setEndTime(defaultEnd);
    setPage(1);
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

  const hasAppliedFilters =
    taskType !== "" ||
    level !== "" ||
    (canPickTenant && selectedTenantId !== "") ||
    searchQuery.trim() !== "";

  return (
    <>
      <Head>
        <title>Logs Dashboard - AI4Inclusion Console</title>
        <meta name="description" content="View telemetry traces and request outcomes" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full" align="stretch">
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

              {!authLoading && !isAuthenticated && (
                <Alert status="warning">
                  <AlertIcon />
                  <AlertDescription>
                    Please log in to view logs.{" "}
                    <Button size="sm" colorScheme="blue" ml={4} onClick={() => router.push("/auth")}>
                      Log In
                    </Button>
                  </AlertDescription>
                </Alert>
              )}

              {tracesError && (
                <Alert status="error">
                  <AlertIcon />
                  <AlertDescription>
                    {(tracesError as Error)?.message || "Error loading traces"}
                  </AlertDescription>
                </Alert>
              )}

              {aggregationStats && (
                <LogsAggregationStats
                  total={aggregationStats.total}
                  success={aggregationStats.by_level.success}
                  failure={aggregationStats.by_level.failure}
                  cardBg={cardBg}
                  borderColor={borderColor}
                />
              )}

              <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
                <CardBody>
                  {!tracesError && (
                    <LogsTable
                      rows={displayedTraceRows}
                      isLoading={tracesLoading}
                      page={page}
                      pageSize={pageSize}
                      totalItems={tracesData?.total ?? 0}
                      onPageChange={setPage}
                      onPageSizeChange={setPageSize}
                      onTimeRangeChange={() => setPage(1)}
                      hasActiveFilters={hasAppliedFilters}
                      onClearFilters={clearAllFilters}
                      resolveTenantName={resolveTenantName}
                      onOpenTrace={openTraceDetail}
                      searchQuery={searchQuery}
                      onSearchQueryChange={setSearchQuery}
                      canPickTenant={canPickTenant}
                      selectedTenantId={selectedTenantId}
                      onTenantChange={setSelectedTenantId}
                      tenantsLoading={tenantsLoading}
                      tenantsError={!!tenantsError}
                      activeTenants={activeTenants}
                      taskType={taskType}
                      onTaskTypeChange={setTaskType}
                      level={level}
                      onLevelChange={setLevel}
                      startTime={startTime}
                      onStartTimeChange={setStartTime}
                      endTime={endTime}
                      onEndTimeChange={setEndTime}
                      cardBg={cardBg}
                      autoRefresh={autoRefresh}
                      onAutoRefreshChange={setAutoRefresh}
                      onRefresh={handleRefresh}
                      isRefreshing={tracesLoading}
                    />
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
