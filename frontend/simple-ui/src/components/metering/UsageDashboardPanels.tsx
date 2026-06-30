import { Box, Heading, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import type { useMeteringDashboard } from "../../hooks/useMeteringDashboard";
import { OverviewKpiCards, ConsumptionOverviewSection } from "./OverviewSections";
import ServiceConsumptionTab from "./ServiceConsumptionTab";
import TenantConsumptionTab from "./TenantConsumptionTab";
import UsageAndSpendTab from "./UsageAndSpendTab";
import ThroughputLoadSection from "./ThroughputLoadSection";

type MeteringDashboardState = ReturnType<typeof useMeteringDashboard>;

interface TenantHeaderProps {
  organisationLabel: string | null;
}

export const TenantDashboardHeader: React.FC<TenantHeaderProps> = ({
  organisationLabel,
}) => (
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
  </>
);

interface TenantPanelsProps {
  overview: NonNullable<MeteringDashboardState["overview"]>;
  requestVolumeGraph: MeteringDashboardState["requestVolumeGraph"];
  totalRequestsKpi: MeteringDashboardState["totalRequestsKpi"];
  requestVolumeSection: React.ReactNode;
  serviceSectionRef: MeteringDashboardState["serviceSectionRef"];
  serviceQuery: MeteringDashboardState["serviceQuery"];
  parseQueryError: MeteringDashboardState["parseQueryError"];
}

export const TenantDashboardPanels: React.FC<TenantPanelsProps> = ({
  overview,
  requestVolumeGraph,
  totalRequestsKpi,
  requestVolumeSection,
  serviceSectionRef,
  serviceQuery,
  parseQueryError,
}) => (
  <>
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
    <Box ref={serviceSectionRef}>
      <ServiceConsumptionTab
        data={serviceQuery.data}
        isLoading={serviceQuery.isLoading}
        errorMessage={parseQueryError(serviceQuery.error)}
      />
    </Box>
  </>
);

interface AdopterPanelsProps {
  subTab: MeteringDashboardState["subTab"];
  overview: MeteringDashboardState["overview"];
  tenantOrganisationById: MeteringDashboardState["tenantOrganisationById"];
  requestVolumeSection: React.ReactNode;
  topN: MeteringDashboardState["topN"];
  onTopNChange: MeteringDashboardState["setTopN"];
  onHeatmapServicesChange: MeteringDashboardState["setTenantHeatmapServices"];
  tenantQuery: MeteringDashboardState["tenantQuery"];
  serviceQuery: MeteringDashboardState["serviceQuery"];
  parseQueryError: MeteringDashboardState["parseQueryError"];
}

export const AdopterDashboardPanels: React.FC<AdopterPanelsProps> = ({
  subTab,
  overview,
  tenantOrganisationById,
  requestVolumeSection,
  topN,
  onTopNChange,
  onHeatmapServicesChange,
  tenantQuery,
  serviceQuery,
  parseQueryError,
}) => (
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
        onTopNChange={onTopNChange}
        onHeatmapServicesChange={onHeatmapServicesChange}
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
    {subTab === METERING.SUB_TAB.USAGE_SPEND && <UsageAndSpendTab />}
  </Box>
);
