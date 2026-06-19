import { Box, Heading, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import type { useMeteringDashboard } from "../../hooks/useMeteringDashboard";
import { formatMeteringRefreshTime } from "../../utils/meteringFormatters";
import type { MeteringRoleView } from "../../utils/rbac";
import LoadingSpinner from "../common/LoadingSpinner";
import { MeteringAlerts } from "./MeteringAsyncState";
import MeteringControls from "./MeteringControls";
import SegmentedTabBar from "./SegmentedTabBar";
import {
  ConsumptionOverviewSection,
  OverviewKpiCards,
  PlatformAdoptionSection,
} from "./OverviewSections";
import ServiceConsumptionTab from "./ServiceConsumptionTab";
import TenantConsumptionTab from "./TenantConsumptionTab";
import TenantPreviewSelect from "./TenantPreviewSelect";
import ThroughputLoadSection from "./ThroughputLoadSection";

export type MeteringDashboardState = ReturnType<typeof useMeteringDashboard>;

interface RoleViewBarProps {
  roleViewConfig: MeteringDashboardState["roleViewConfig"];
  roleView: MeteringRoleView;
  onRoleViewChange: (view: MeteringRoleView) => void;
}

export const RoleViewBar: React.FC<RoleViewBarProps> = () => null;

interface LoadingViewProps {
  roleViewBar: React.ReactNode;
}

export const LoadingView: React.FC<LoadingViewProps> = ({ roleViewBar }) => (
  <VStack align="stretch" spacing={4}>
    {roleViewBar}
    <Box
      minH={METERING.DEFAULTS.LOADING_MIN_HEIGHT}
      display="flex"
      alignItems="center"
      justifyContent="center"
    >
      <LoadingSpinner size="xl" />
    </Box>
  </VStack>
);

interface TenantUsageViewProps {
  dash: MeteringDashboardState;
  requestVolumeSection: React.ReactNode;
}

export const TenantUsageView: React.FC<TenantUsageViewProps> = ({
  dash,
  requestVolumeSection,
}) => {
  const {
    organisationLabel,
    primaryError,
    isDegraded,
    timeWindow,
    setTimeWindow,
    overview,
    handleRefresh,
    isRefreshing,
    requestVolumeGraph,
    totalRequestsKpi,
    serviceSectionRef,
    serviceQuery,
    parseQueryError,
  } = dash;

  return (
    <>
      {organisationLabel ? (
        <Heading size="md" color="gray.700">
          {METERING.TENANT_VIEW.TITLE} · {organisationLabel}
        </Heading>
      ) : (
        <Text color="gray.600" fontSize="sm">
          {METERING.TENANT_VIEW.TITLE}
        </Text>
      )}

      <MeteringAlerts errorMessage={primaryError} isDegraded={isDegraded} />

      <MeteringControls
        timeWindow={timeWindow}
        onTimeWindowChange={setTimeWindow}
        lastRefreshed={formatMeteringRefreshTime(dash.lastGeneratedAt)}
        onRefresh={handleRefresh}
        isRefreshing={isRefreshing}
      />

      {overview ? (
        <VStack align="stretch" spacing={6}>
          <OverviewKpiCards data={overview} />
          <ThroughputLoadSection
            throughput={overview.throughput}
            timeWindow={overview.scope.window}
            requestVolumeGraph={requestVolumeGraph}
            fourthMetric={{
              label: METERING.TENANT_VIEW.TOTAL_REQUESTS_LABEL,
              value: String(totalRequestsKpi ?? METERING.GRAPH.EMPTY_VALUE),
              helper: METERING.TENANT_VIEW.TOTAL_REQUESTS_HELPER,
            }}
          />
          {requestVolumeSection}
        </VStack>
      ) : null}

      <Box ref={serviceSectionRef}>
        <ServiceConsumptionTab
          data={serviceQuery.data}
          isLoading={serviceQuery.isLoading}
          errorMessage={parseQueryError(serviceQuery.error)}
        />
      </Box>
    </>
  );
};

interface AdopterUsageViewProps {
  dash: MeteringDashboardState;
  requestVolumeSection: React.ReactNode;
}

export const AdopterUsageView: React.FC<AdopterUsageViewProps> = ({
  dash,
  requestVolumeSection,
}) => {
  const {
    subTab,
    setSubTab,
    timeWindow,
    setTimeWindow,
    topN,
    setTopN,
    scopeTenantId,
    setScopeTenantId,
    previewTenants,
    overview,
    tenantOrganisationById,
    tenantQuery,
    serviceQuery,
    handleRefresh,
    isRefreshing,
    setTenantHeatmapServices,
    parseQueryError,
  } = dash;

  return (
    <>
      {overview?.platform_adoption || overview?.active_tenants?.length ? (
        <PlatformAdoptionSection data={overview} />
      ) : null}

      <MeteringControls
        timeWindow={timeWindow}
        onTimeWindowChange={setTimeWindow}
        lastRefreshed={formatMeteringRefreshTime(dash.lastGeneratedAt)}
        onRefresh={handleRefresh}
        isRefreshing={isRefreshing}
        showTenantFilter
        tenantOptions={previewTenants.map((t) => ({ id: t.id, label: t.organisation }))}
        selectedTenantId={scopeTenantId}
        onTenantChange={setScopeTenantId}
        showSubTabs
        subTab={subTab}
        onSubTabChange={setSubTab}
        topN={topN}
        onTopNChange={setTopN}
      />

      <Box pt={2}>
        {subTab === METERING.SUB_TAB.OVERVIEW && overview ? (
          <VStack align="stretch" spacing={6}>
            <OverviewKpiCards data={overview} />
            <ConsumptionOverviewSection
              data={overview}
              tenantOrganisationById={tenantOrganisationById}
            />
            {requestVolumeSection}
          </VStack>
        ) : null}
        {subTab === METERING.SUB_TAB.TENANT && (
          <TenantConsumptionTab
            data={tenantQuery.data}
            topN={topN}
            onTopNChange={setTopN}
            onHeatmapServicesChange={setTenantHeatmapServices}
            tenantOrganisationById={tenantOrganisationById}
            isLoading={tenantQuery.isLoading}
            errorMessage={parseQueryError(tenantQuery.error)}
          />
        )}
        {subTab === METERING.SUB_TAB.SERVICE && (
          <ServiceConsumptionTab
            data={serviceQuery.data}
            isLoading={serviceQuery.isLoading}
            errorMessage={parseQueryError(serviceQuery.error)}
          />
        )}
      </Box>
    </>
  );
};
