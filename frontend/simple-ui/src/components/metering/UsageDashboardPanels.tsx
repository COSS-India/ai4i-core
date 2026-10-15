import { Box, Heading, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import type { useMeteringDashboard } from "../../hooks/useMeteringDashboard";
import { OverviewKpiCards, ConsumptionOverviewSection } from "./OverviewSections";
import ModelConsumptionTab from "./ModelConsumptionTab";
import UsageAndSpendTab from "./UsageAndSpendTab";
import ApplicationUsageTab from "./ApplicationUsageTab";

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
  period: MeteringDashboardState["period"];
  overview: MeteringDashboardState["overview"];
  requestVolumeSection: React.ReactNode;
  modelQuery: MeteringDashboardState["modelQuery"];
  parseQueryError: MeteringDashboardState["parseQueryError"];
  tenantId?: string | null;
  organisationLabel?: string | null;
  refreshNonce?: number;
  /** When recorded usage starts (Overview's period.recordedFrom), for the Applications drawer. */
  recordedFrom?: string | null;
}

export const TenantDashboardPanels: React.FC<TenantPanelsProps> = ({
  subTab,
  period,
  overview,
  requestVolumeSection,
  modelQuery,
  parseQueryError,
  tenantId,
  organisationLabel,
  refreshNonce,
  recordedFrom,
}) => (
  <Box pt={2}>
    {subTab === METERING.SUB_TAB.OVERVIEW && overview ? (
      <VStack align="stretch" spacing={6}>
        <OverviewKpiCards data={overview} isPlatformWide={false} />
        {requestVolumeSection}
      </VStack>
    ) : null}
    {subTab === METERING.SUB_TAB.MODEL && (
      <ModelConsumptionTab
        data={modelQuery.data}
        isLoading={modelQuery.isLoading}
        errorMessage={parseQueryError(modelQuery.error)}
        isPlatformWide={false}
      />
    )}
    {subTab === METERING.SUB_TAB.USAGE_SPEND && (
      <UsageAndSpendTab
        period={period}
        isTenantView
        tenantId={tenantId}
        organisationLabel={organisationLabel}
        refreshNonce={refreshNonce}
      />
    )}
    {subTab === METERING.SUB_TAB.APPLICATIONS && (
      <ApplicationUsageTab
        period={period}
        isTenantView
        tenantId={tenantId}
        organisationLabel={organisationLabel}
        refreshNonce={refreshNonce}
        recordedFrom={recordedFrom}
      />
    )}
  </Box>
);

interface AdopterPanelsProps {
  subTab: MeteringDashboardState["subTab"];
  period: MeteringDashboardState["period"];
  overview: MeteringDashboardState["overview"];
  tenantOrganisationById: MeteringDashboardState["tenantOrganisationById"];
  requestVolumeSection: React.ReactNode;
  topN: MeteringDashboardState["topN"];
  onTopNChange: MeteringDashboardState["setTopN"];
  modelQuery: MeteringDashboardState["modelQuery"];
  parseQueryError: MeteringDashboardState["parseQueryError"];
  scopeTenantId?: string | null;
  refreshNonce?: number;
  /** When recorded usage starts (Overview's period.recordedFrom), for the Applications drawer. */
  recordedFrom?: string | null;
}

export const AdopterDashboardPanels: React.FC<AdopterPanelsProps> = ({
  subTab,
  period,
  overview,
  tenantOrganisationById,
  requestVolumeSection,
  topN,
  onTopNChange,
  modelQuery,
  parseQueryError,
  scopeTenantId,
  refreshNonce,
  recordedFrom,
}) => (
  <Box pt={2}>
    {subTab === METERING.SUB_TAB.OVERVIEW && overview ? (
      <VStack align="stretch" spacing={6}>
        <OverviewKpiCards data={overview} isPlatformWide={!scopeTenantId} />
        <ConsumptionOverviewSection
          data={overview}
          tenantOrganisationById={tenantOrganisationById}
          topN={topN}
          onTopNChange={onTopNChange}
          isScopedTenant={Boolean(scopeTenantId)}
        />
        {requestVolumeSection}
      </VStack>
    ) : null}
    {subTab === METERING.SUB_TAB.MODEL && (
      <ModelConsumptionTab
        data={modelQuery.data}
        isLoading={modelQuery.isLoading}
        errorMessage={parseQueryError(modelQuery.error)}
        isPlatformWide={!scopeTenantId}
        showModelCountKpis={false}
      />
    )}
    {subTab === METERING.SUB_TAB.USAGE_SPEND && (
      <UsageAndSpendTab
        period={period}
        scopeTenantId={scopeTenantId}
        refreshNonce={refreshNonce}
      />
    )}
    {subTab === METERING.SUB_TAB.APPLICATIONS && (
      <ApplicationUsageTab
        period={period}
        scopeTenantId={scopeTenantId}
        refreshNonce={refreshNonce}
        recordedFrom={recordedFrom}
      />
    )}
  </Box>
);
