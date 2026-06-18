import {
  Box,
  Heading,
  Text,
  VStack,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import React, { useEffect, useMemo, useState } from "react";
import { MOCK_PREVIEW_TENANTS, buildMeteringRequestVolumeSeries } from "../../data/meteringMockData";
import { listTenants } from "../../services/tenantService";
import type { MeteringTopN, MeteringWindow } from "../../types/metering";
import {
  fetchMeteringOverview,
  fetchMeteringServiceConsumption,
  fetchMeteringTenantConsumption,
  parseMeteringError,
  type MeteringContext,
} from "../../services/meteringService";
import {
  getMeteringRoleViewConfig,
  type MeteringRoleView,
} from "../../utils/rbac";
import { formatMeteringRefreshTime } from "../../utils/meteringFormatters";
import { getTenantIdFromToken } from "../../utils/helpers";
import LoadingSpinner from "../common/LoadingSpinner";
import MeteringControls from "./MeteringControls";
import MeteringRoleViewBar from "./MeteringRoleViewBar";
import MeteringStatusBanners from "./MeteringStatusBanners";
import type { MeteringSubTab } from "./MeteringSubTabBar";
import {
  ConsumptionOverviewSection,
  OverviewKpiCards,
  PlatformAdoptionSection,
} from "./OverviewSections";
import RequestVolumeSection from "./RequestVolumeSection";
import ServiceConsumptionTab from "./ServiceConsumptionTab";
import TenantConsumptionTab from "./TenantConsumptionTab";
import TenantPreviewSelect, { type TenantPreviewOption } from "./TenantPreviewSelect";
import ThroughputLoadSection from "./ThroughputLoadSection";

interface UsageDashboardProps {
  userRoles?: string[];
  tenantId?: string | null;
}

const UsageDashboard: React.FC<UsageDashboardProps> = ({
  userRoles,
  tenantId,
}) => {
  const roleViewConfig = useMemo(
    () => getMeteringRoleViewConfig(userRoles),
    [userRoles],
  );

  const [roleView, setRoleView] = useState<MeteringRoleView>(roleViewConfig.defaultView);
  const [subTab, setSubTab] = useState<MeteringSubTab>("overview");
  const [window, setWindow] = useState<MeteringWindow>("24h");
  const [topN, setTopN] = useState<MeteringTopN>(10);
  const [scopeTenantId, setScopeTenantId] = useState("");
  const [previewTenantId, setPreviewTenantId] = useState("");
  const [tenantHeatmapServices, setTenantHeatmapServices] = useState<string[] | null>(null);

  useEffect(() => {
    setRoleView(roleViewConfig.defaultView);
  }, [roleViewConfig.defaultView]);

  useEffect(() => {
    if (subTab !== "tenant") {
      setTenantHeatmapServices(null);
    }
  }, [subTab]);

  useEffect(() => {
    setTenantHeatmapServices(null);
  }, [window, topN]);

  const isAdopterView = roleView === "adopter";
  const isTenantView = roleView === "tenant";

  const tenantsQuery = useQuery({
    queryKey: ["metering-tenant-directory"],
    queryFn: () => listTenants(),
    enabled: isAdopterView || (roleViewConfig.canSwitchViews && isTenantView),
    staleTime: 5 * 60_000,
  });

  const useMockTenants = process.env.NEXT_PUBLIC_METERING_USE_MOCK === "true";

  const previewTenants: TenantPreviewOption[] = useMemo(() => {
    const apiTenants = tenantsQuery.data?.tenants ?? [];
    if (apiTenants.length > 0) {
      return apiTenants.map((t, i) => ({
        id: t.tenant_id,
        organisation: t.organisation,
        plan: i % 3 === 2 ? "Pro" : "Enterprise",
      }));
    }
    if (useMockTenants) {
      return MOCK_PREVIEW_TENANTS;
    }
    return [];
  }, [tenantsQuery.data?.tenants, useMockTenants]);

  const tenantOrganisationById = useMemo(() => {
    const map: Record<string, string> = {};
    (tenantsQuery.data?.tenants ?? []).forEach((t) => {
      if (t.tenant_id && t.organisation) {
        map[String(t.tenant_id)] = t.organisation;
      }
    });
    return map;
  }, [tenantsQuery.data?.tenants]);

  useEffect(() => {
    if (isTenantView && roleViewConfig.canSwitchViews && previewTenants.length > 0 && !previewTenantId) {
      setPreviewTenantId(previewTenants[0].id);
    }
  }, [isTenantView, roleViewConfig.canSwitchViews, previewTenants, previewTenantId]);

  const previewOrganisation =
    previewTenants.find((t) => t.id === previewTenantId)?.organisation ?? null;

  const isAdminPreviewingTenant = roleViewConfig.canSwitchViews && isTenantView;
  const effectiveIsPlatformAdmin = isAdopterView || isAdminPreviewingTenant;
  const effectiveTenantId = isTenantView
    ? roleViewConfig.canSwitchViews
      ? previewTenantId || null
      : tenantId?.trim() || getTenantIdFromToken() || null
    : scopeTenantId || null;

  const tenantOverviewEnabled =
    isTenantView &&
    (roleViewConfig.canSwitchViews ? !!previewTenantId : !!effectiveTenantId);

  const ctx: MeteringContext = useMemo(
    () => ({
      isPlatformAdmin: effectiveIsPlatformAdmin,
      tenantId: effectiveTenantId,
      previewTenantId: isAdminPreviewingTenant ? previewTenantId || null : null,
      organisation: isTenantView ? previewOrganisation : null,
    }),
    [
      effectiveIsPlatformAdmin,
      effectiveTenantId,
      isAdminPreviewingTenant,
      previewTenantId,
      isTenantView,
      previewOrganisation,
    ],
  );

  const queryTenantId = scopeTenantId || (isTenantView ? effectiveTenantId : null);

  const overviewQuery = useQuery({
    queryKey: [
      "metering-overview",
      window,
      queryTenantId,
      previewTenantId,
      roleView,
      effectiveIsPlatformAdmin,
    ],
    queryFn: () => fetchMeteringOverview(window, ctx, queryTenantId),
    enabled: isAdopterView || tenantOverviewEnabled,
    staleTime: 60_000,
  });

  const tenantQuery = useQuery({
    queryKey: ["metering-tenant", window, topN, tenantHeatmapServices?.join(",") ?? "all"],
    queryFn: () => fetchMeteringTenantConsumption(window, topN, tenantHeatmapServices),
    enabled: isAdopterView && subTab === "tenant",
    staleTime: 60_000,
  });

  const serviceQuery = useQuery({
    queryKey: [
      "metering-service",
      window,
      queryTenantId,
      previewTenantId,
      roleView,
      effectiveIsPlatformAdmin,
    ],
    queryFn: () => fetchMeteringServiceConsumption(window, ctx, queryTenantId),
    enabled: (isAdopterView && subTab === "service") || tenantOverviewEnabled,
    staleTime: 60_000,
  });

  const overview = overviewQuery.data?.data;
  const isMock =
    overviewQuery.data?.isMock ||
    tenantQuery.data?.isMock ||
    serviceQuery.data?.isMock;

  const isDegraded =
    overview?.degraded ||
    tenantQuery.data?.data?.degraded ||
    serviceQuery.data?.data?.degraded;

  const primaryError = useMemo(() => {
    const err = overviewQuery.error || serviceQuery.error || tenantQuery.error;
    return err ? parseMeteringError(err) : null;
  }, [overviewQuery.error, serviceQuery.error, tenantQuery.error]);

  const isLoading =
    (isAdopterView && overviewQuery.isLoading) ||
    (isTenantView && overviewQuery.isLoading && tenantOverviewEnabled);

  const requestVolumeGraph = useMemo(() => {
    const fromApi =
      overview?.request_volume ?? serviceQuery.data?.data?.request_volume ?? null;
    if (fromApi) return fromApi;
    if (isMock && overview) return buildMeteringRequestVolumeSeries(window);
    return null;
  }, [overview, serviceQuery.data?.data?.request_volume, isMock, window]);

  const isRefreshing =
    overviewQuery.isFetching ||
    tenantQuery.isFetching ||
    serviceQuery.isFetching;

  const handleRefresh = () => {
    overviewQuery.refetch();
    tenantQuery.refetch();
    serviceQuery.refetch();
  };

  const totalRequestsKpi = overview?.kpis.find((k) => k.key === "total_requests")?.value;
  const successRateKpi = overview?.kpis.find((k) => k.key === "success_rate")?.value;

  const organisationLabel =
    overview?.scope.organisation ?? previewOrganisation ?? null;

  const statusBanners = (
    <MeteringStatusBanners
      isMock={isMock}
      isDegraded={Boolean(isDegraded)}
      errorMessage={primaryError}
    />
  );

  const overviewTabContent = overview ? (
    <VStack align="stretch" spacing={6} pt={2}>
      <OverviewKpiCards data={overview} />
      <ConsumptionOverviewSection
        data={overview}
        tenantOrganisationById={tenantOrganisationById}
      />
      <RequestVolumeSection
        graph={requestVolumeGraph}
        requestHealth={overview.request_health}
        totalRequests={totalRequestsKpi}
        successRate={successRateKpi}
      />
    </VStack>
  ) : null;

  const roleViewBar = (
    <MeteringRoleViewBar
      activeView={roleView}
      availableViews={roleViewConfig.availableViews}
      canSwitchViews={roleViewConfig.canSwitchViews}
      onViewChange={setRoleView}
    />
  );

  if (isLoading) {
    return (
      <VStack align="stretch" spacing={4}>
        {roleViewBar}
        <Box minH="400px" display="flex" alignItems="center" justifyContent="center">
          <LoadingSpinner size="xl" />
        </Box>
      </VStack>
    );
  }

  if (isTenantView) {
    return (
      <VStack align="stretch" spacing={4}>
        {roleViewBar}

        {roleViewConfig.canSwitchViews ? (
          <TenantPreviewSelect
            tenants={previewTenants}
            selectedTenantId={previewTenantId}
            onSelect={setPreviewTenantId}
          />
        ) : null}

        {organisationLabel ? (
          <Heading size="md" color="gray.700">
            My Usage · {organisationLabel}
          </Heading>
        ) : (
          <Text color="gray.600" fontSize="sm">
            My Usage
          </Text>
        )}

        {statusBanners}

        <MeteringControls
          window={window}
          onWindowChange={setWindow}
          lastRefreshed={formatMeteringRefreshTime(overview?.generated_at)}
          onRefresh={handleRefresh}
          isRefreshing={isRefreshing}
        />

        {overview ? (
          <VStack align="stretch" spacing={6}>
            <OverviewKpiCards data={overview} />
            <ThroughputLoadSection
              throughput={overview.throughput}
              window={overview.scope.window}
              requestVolumeGraph={requestVolumeGraph}
              fourthMetric={{
                label: "Total requests",
                value: String(totalRequestsKpi ?? "—"),
                helper: "across selected window",
              }}
            />
            <RequestVolumeSection
              graph={requestVolumeGraph}
              requestHealth={overview.request_health}
              totalRequests={totalRequestsKpi}
              successRate={successRateKpi}
            />
          </VStack>
        ) : null}

        <ServiceConsumptionTab
          data={serviceQuery.data?.data}
          isLoading={serviceQuery.isLoading}
          errorMessage={serviceQuery.error ? parseMeteringError(serviceQuery.error) : null}
        />
      </VStack>
    );
  }

  return (
    <VStack align="stretch" spacing={5}>
      {roleViewBar}
      {statusBanners}

      {overview?.platform_adoption ? (
        <PlatformAdoptionSection data={overview} />
      ) : null}

      <MeteringControls
        window={window}
        onWindowChange={setWindow}
        showTenantFilter
        tenantOptions={previewTenants.map((t) => ({
          id: t.id,
          label: t.organisation,
        }))}
        selectedTenantId={scopeTenantId}
        onTenantChange={setScopeTenantId}
        showSubTabs
        subTab={subTab}
        onSubTabChange={setSubTab}
        showTopN={false}
        topN={topN}
        onTopNChange={setTopN}
        lastRefreshed={formatMeteringRefreshTime(overview?.generated_at)}
        onRefresh={handleRefresh}
        isRefreshing={isRefreshing}
      />

      <Box pt={2}>
        {subTab === "overview" && overviewTabContent}
        {subTab === "tenant" && (
          <TenantConsumptionTab
            data={tenantQuery.data?.data}
            fallbackThroughput={overview?.throughput}
            fallbackRequestVolumeGraph={overview?.request_volume}
            topN={topN}
            onTopNChange={setTopN}
            onHeatmapServicesChange={setTenantHeatmapServices}
            tenantOrganisationById={tenantOrganisationById}
            isLoading={tenantQuery.isLoading}
            errorMessage={tenantQuery.error ? parseMeteringError(tenantQuery.error) : null}
          />
        )}
        {subTab === "service" && (
          <ServiceConsumptionTab
            data={serviceQuery.data?.data}
            isLoading={serviceQuery.isLoading}
            errorMessage={serviceQuery.error ? parseMeteringError(serviceQuery.error) : null}
          />
        )}
      </Box>
    </VStack>
  );
};

export default UsageDashboard;
