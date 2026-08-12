import { Box, Heading, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import type { useMeteringDashboard } from "../../hooks/useMeteringDashboard";
import { OverviewKpiCards, ConsumptionOverviewSection } from "./OverviewSections";
import ModelConsumptionTab from "./ModelConsumptionTab";
import TenantConsumptionTab from "./TenantConsumptionTab";
import UsageAndSpendTab from "./UsageAndSpendTab";

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
  subTab: MeteringDashboardState["subTab"];
  overview: MeteringDashboardState["overview"];
  requestVolumeSection: React.ReactNode;
  modelQuery: MeteringDashboardState["modelQuery"];
  parseQueryError: MeteringDashboardState["parseQueryError"];
  tenantId?: string | null;
  organisationLabel?: string | null;
  refreshNonce?: number;
}

export const TenantDashboardPanels: React.FC<TenantPanelsProps> = ({
  subTab,
  overview,
  requestVolumeSection,
  modelQuery,
  parseQueryError,
  tenantId,
  organisationLabel,
  refreshNonce,
}) => (
  <Box pt={2}>
    {subTab === METERING.SUB_TAB.OVERVIEW && overview ? (
      <VStack align="stretch" spacing={6}>
        <OverviewKpiCards data={overview} />
        {requestVolumeSection}
      </VStack>
    ) : null}
    {subTab === METERING.SUB_TAB.MODEL && (
      <ModelConsumptionTab
        data={modelQuery.data}
        isLoading={modelQuery.isLoading}
        errorMessage={parseQueryError(modelQuery.error)}
      />
    )}
    {subTab === METERING.SUB_TAB.USAGE_SPEND && (
      <UsageAndSpendTab
        isTenantView
        tenantId={tenantId}
        organisationLabel={organisationLabel}
        refreshNonce={refreshNonce}
      />
    )}
  </Box>
);

interface AdopterPanelsProps {
  subTab: MeteringDashboardState["subTab"];
  overview: MeteringDashboardState["overview"];
  tenantOrganisationById: MeteringDashboardState["tenantOrganisationById"];
  requestVolumeSection: React.ReactNode;
  topN: MeteringDashboardState["topN"];
  onTopNChange: MeteringDashboardState["setTopN"];
  tenantQuery: MeteringDashboardState["tenantQuery"];
  modelQuery: MeteringDashboardState["modelQuery"];
  parseQueryError: MeteringDashboardState["parseQueryError"];
  scopeTenantId?: string | null;
  refreshNonce?: number;
}

export const AdopterDashboardPanels: React.FC<AdopterPanelsProps> = ({
  subTab,
  overview,
  tenantOrganisationById,
  requestVolumeSection,
  topN,
  onTopNChange,
  tenantQuery,
  modelQuery,
  parseQueryError,
  scopeTenantId,
  refreshNonce,
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
          tenantOrganisationById={tenantOrganisationById}
        isLoading={tenantQuery.isLoading}
        errorMessage={parseQueryError(tenantQuery.error)}
      />
    )}
    {subTab === METERING.SUB_TAB.MODEL && (
      <ModelConsumptionTab
        data={modelQuery.data}
        isLoading={modelQuery.isLoading}
        errorMessage={parseQueryError(modelQuery.error)}
      />
    )}
    {subTab === METERING.SUB_TAB.USAGE_SPEND && (
      <UsageAndSpendTab
        scopeTenantId={scopeTenantId}
        refreshNonce={refreshNonce}
      />
    )}
  </Box>
);
