import { Box, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import { useMeteringDashboard } from "../../hooks/useMeteringDashboard";
import { formatMeteringRefreshTime } from "../../utils/meteringFormatters";
import type { MeteringRoleView } from "../../utils/rbac";
import LoadingSpinner from "../common/LoadingSpinner";
import { MeteringAlerts } from "./MeteringAsyncState";
import MeteringControls from "./MeteringControls";
import { PlatformAdoptionSection } from "./OverviewSections";
import RequestVolumeSection from "./RequestVolumeSection";
import SegmentedTabBar from "./SegmentedTabBar";
import {
  AdopterDashboardPanels,
  TenantDashboardHeader,
  TenantDashboardPanels,
} from "./UsageDashboardPanels";

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
    lastGeneratedAt,
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

  const requestVolumeSection = overview ? (
    <RequestVolumeSection
      graph={requestVolumeGraph}
      requestHealth={overview.request_health}
      totalRequests={totalRequestsKpi}
      successRate={successRateKpi}
    />
  ) : null;

  const showPlatformAdoption =
    isTenantView === false &&
    Boolean(overview?.platform_adoption || overview?.active_tenants?.length);

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
        <TenantDashboardHeader
          canSwitchViews={roleViewConfig.canSwitchViews}
          previewTenants={previewTenants}
          previewTenantId={previewTenantId}
          onSelectTenant={setPreviewTenantId}
          organisationLabel={organisationLabel}
        />
      ) : null}

      <MeteringAlerts errorMessage={primaryError} isDegraded={isDegraded} />

      {showPlatformAdoption && overview ? (
        <PlatformAdoptionSection data={overview} />
      ) : null}

      <MeteringControls
        timeWindow={timeWindow}
        onTimeWindowChange={setTimeWindow}
        lastRefreshed={formatMeteringRefreshTime(lastGeneratedAt)}
        onRefresh={handleRefresh}
        isRefreshing={isRefreshing}
        showTenantFilter={isTenantView === false}
        tenantOptions={previewTenants.map((t) => ({ id: t.id, label: t.organisation }))}
        selectedTenantId={scopeTenantId}
        onTenantChange={setScopeTenantId}
        showSubTabs={isTenantView === false}
        subTab={subTab}
        onSubTabChange={setSubTab}
        topN={topN}
        onTopNChange={setTopN}
      />

      {isTenantView && overview ? (
        <TenantDashboardPanels
          overview={overview}
          requestVolumeGraph={requestVolumeGraph}
          totalRequestsKpi={totalRequestsKpi}
          requestVolumeSection={requestVolumeSection}
          serviceSectionRef={serviceSectionRef}
          serviceQuery={serviceQuery}
          parseQueryError={parseQueryError}
        />
      ) : null}

      {isTenantView ? null : (
        <AdopterDashboardPanels
          subTab={subTab}
          overview={overview}
          tenantOrganisationById={tenantOrganisationById}
          requestVolumeSection={requestVolumeSection}
          topN={topN}
          onTopNChange={setTopN}
          onHeatmapServicesChange={setTenantHeatmapServices}
          tenantQuery={tenantQuery}
          serviceQuery={serviceQuery}
          parseQueryError={parseQueryError}
        />
      )}
    </VStack>
  );
};

export default UsageDashboard;
