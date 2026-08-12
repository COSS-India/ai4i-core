import { Box, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import { useMeteringDashboard } from "../../hooks/useMeteringDashboard";
import LoadingSpinner from "../common/LoadingSpinner";
import { MeteringAlerts } from "./MeteringAsyncState";
import MeteringControls from "./MeteringControls";
import { PlatformAdoptionSection } from "./OverviewSections";
import RequestVolumeSection from "./RequestVolumeSection";
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
    subTab,
    setSubTab,
    timeWindow,
    setTimeWindow,
    topN,
    setTopN,
    scopeTenantId,
    setScopeTenantId,
    isTenantView,
    previewTenants,
    tenantOrganisationById,
    overview,
    tenantQuery,
    serviceQuery,
    modelQuery,
    isLoading,
    isRefreshing,
    handleRefresh,
    primaryError,
    dataStateBanner,
    requestVolumeGraph,
    organisationLabel,
    lastGeneratedAt,
    parseQueryError,
    refreshNonce,
    effectiveTenantId,
  } = dash;

  const requestVolumeSection = overview ? (
    <RequestVolumeSection
      graph={requestVolumeGraph}
      timeWindow={timeWindow}
    />
  ) : null;

  const showPlatformAdoption =
    isTenantView === false &&
    Boolean(overview?.platform_adoption || overview?.active_tenants?.length);

  if (isLoading) {
    return (
      <Box minH={METERING.DEFAULTS.LOADING_MIN_HEIGHT} display="flex" alignItems="center" justifyContent="center">
        <LoadingSpinner size="xl" />
      </Box>
    );
  }

  return (
    <VStack align="stretch" spacing={isTenantView ? 4 : 5}>
      {isTenantView && subTab !== METERING.SUB_TAB.USAGE_SPEND ? (
        <TenantDashboardHeader organisationLabel={organisationLabel} />
      ) : null}

      <MeteringAlerts errorMessage={primaryError} dataStateBanner={dataStateBanner} />

      {showPlatformAdoption && overview ? (
        <PlatformAdoptionSection data={overview} />
      ) : null}

      <MeteringControls
        timeWindow={timeWindow}
        onTimeWindowChange={setTimeWindow}
        lastGeneratedAt={lastGeneratedAt}
        onRefresh={isTenantView ? undefined : handleRefresh}
        isRefreshing={isRefreshing}
        showTenantFilter={isTenantView === false}
        tenantOptions={previewTenants.map((t) => ({ id: t.id, label: t.organisation }))}
        selectedTenantId={scopeTenantId}
        onTenantChange={setScopeTenantId}
        showSubTabs
        subTabs={isTenantView ? METERING.TENANT_SUB_TABS : METERING.SUB_TABS}
        subTab={subTab}
        onSubTabChange={setSubTab}
        topN={topN}
        onTopNChange={setTopN}
      />

      {isTenantView ? (
        <TenantDashboardPanels
          subTab={subTab}
          overview={overview}
          requestVolumeSection={requestVolumeSection}
          serviceQuery={serviceQuery}
          modelQuery={modelQuery}
          parseQueryError={parseQueryError}
          tenantId={effectiveTenantId}
          organisationLabel={organisationLabel}
          refreshNonce={refreshNonce}
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
          tenantQuery={tenantQuery}
          serviceQuery={serviceQuery}
          modelQuery={modelQuery}
          parseQueryError={parseQueryError}
          scopeTenantId={scopeTenantId}
          refreshNonce={refreshNonce}
        />
      )}
    </VStack>
  );
};

export default UsageDashboard;
