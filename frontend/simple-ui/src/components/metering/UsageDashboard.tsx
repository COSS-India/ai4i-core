import {
  Box,
  Heading,
  Text,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import { useMeteringDashboard } from "../../hooks/useMeteringDashboard";
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
import RequestVolumeSection from "./RequestVolumeSection";
import ServiceConsumptionTab from "./ServiceConsumptionTab";
import TenantConsumptionTab from "./TenantConsumptionTab";
import TenantPreviewSelect from "./TenantPreviewSelect";
import ThroughputLoadSection from "./ThroughputLoadSection";

interface UsageDashboardProps {
  userRoles?: string[];
  tenantId?: string | null;
}

const UsageDashboard: React.FC<UsageDashboardProps> = (props) => {
  const dash = useMeteringDashboard(props);
  const {
    roleViewConfig,
    roleView,
    setRoleView,
    subTab,
    setSubTab,
    timeWindow,
    setTimeWindow,
    topN,
    setTopN,
    scopeTenantId,
    setScopeTenantId,
    previewTenantId,
    setPreviewTenantId,
    setTenantHeatmapServices,
    serviceSectionRef,
    isTenantView,
    previewTenants,
    tenantOrganisationById,
    overview,
    tenantQuery,
    serviceQuery,
    isLoading,
    isRefreshing,
    handleRefresh,
    primaryError,
    isDegraded,
    requestVolumeGraph,
    totalRequestsKpi,
    successRateKpi,
    organisationLabel,
    parseQueryError,
  } = dash;

  const roleViewBar = roleViewConfig.canSwitchViews ? (
    <SegmentedTabBar<MeteringRoleView>
      options={roleViewConfig.availableViews.map((view) => ({
        id: view,
        label: METERING.ROLE_VIEWS[view],
      }))}
      activeId={roleView}
      onChange={setRoleView}
      justify="flex-end"
      mb={4}
    />
  ) : null;

  const controlsProps = {
    timeWindow,
    onTimeWindowChange: setTimeWindow,
    lastRefreshed: formatMeteringRefreshTime(overview?.generated_at),
    onRefresh: handleRefresh,
    isRefreshing,
  };

  const requestVolumeSection = overview ? (
    <RequestVolumeSection
      graph={requestVolumeGraph}
      requestHealth={overview.request_health}
      totalRequests={totalRequestsKpi}
      successRate={successRateKpi}
    />
  ) : null;

  if (isLoading) {
    return (
      <VStack align="stretch" spacing={4}>
        {roleViewBar}
        <Box minH={METERING.DEFAULTS.LOADING_MIN_HEIGHT} display="flex" alignItems="center" justifyContent="center">
          <LoadingSpinner size="xl" />
        </Box>
      </VStack>
    );
  }

  return (
    <VStack align="stretch" spacing={isTenantView ? 4 : 5}>
      {roleViewBar}

      {isTenantView ? (
        <>
          {roleViewConfig.canSwitchViews ? (
            <TenantPreviewSelect
              tenants={previewTenants}
              selectedTenantId={previewTenantId}
              onSelect={setPreviewTenantId}
            />
          ) : null}
          {organisationLabel ? (
            <Heading size="md" color="gray.700">
              {METERING.TENANT_VIEW.TITLE} · {organisationLabel}
            </Heading>
          ) : (
            <Text color="gray.600" fontSize="sm">{METERING.TENANT_VIEW.TITLE}</Text>
          )}
        </>
      ) : null}

      <MeteringAlerts errorMessage={primaryError} isDegraded={isDegraded} />

      {!isTenantView && (overview?.platform_adoption || overview?.active_tenants?.length) ? (
        <PlatformAdoptionSection data={overview!} />
      ) : null}

      <MeteringControls
        {...controlsProps}
        {...(!isTenantView
          ? {
              showTenantFilter: true,
              tenantOptions: previewTenants.map((t) => ({ id: t.id, label: t.organisation })),
              selectedTenantId: scopeTenantId,
              onTenantChange: setScopeTenantId,
              showSubTabs: true,
              subTab,
              onSubTabChange: setSubTab,
              topN,
              onTopNChange: setTopN,
            }
          : {})}
      />

      {isTenantView ? (
        <>
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
      ) : (
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
      )}
    </VStack>
  );
};

export default UsageDashboard;
