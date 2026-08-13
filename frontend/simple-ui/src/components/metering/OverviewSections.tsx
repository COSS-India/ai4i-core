import { Box, Flex, SimpleGrid, Text, VStack } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import type { OverviewResponse, PlatformAdoption } from "../../types/metering";
import {
  formatMeteringKpiValue,
  formatTenantLabel,
  getWindowLabel,
} from "../../utils/meteringFormatters";
import { meteringColorAt } from "../../utils/meteringColors";
import MeteringDonutChart from "./MeteringDonutChart";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import RankedShareList from "./RankedShareList";

interface OverviewKpiCardsProps {
  data: OverviewResponse;
}

// Value colour per KPI: successful = green, failed = red, others neutral.
const KPI_VALUE_COLORS: Record<string, string> = {
  total_requests: "gray.800",
  successful: "green.500",
  failed: "red.500",
  avg_rps: "gray.800",
};

/** Top-row summary KPI cards (Total, Successful, Failed, Avg RPS). */
export const OverviewKpiCards: React.FC<OverviewKpiCardsProps> = ({ data }) => (
  <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
    {data.kpis.map((kpi) => (
      <KpiCard
        key={kpi.key}
        label={METERING.KPI.LABELS[kpi.key as keyof typeof METERING.KPI.LABELS] ?? kpi.label}
        value={formatMeteringKpiValue(kpi.key, kpi.value)}
        pctChange={kpi.pct_change}
        valueColor={KPI_VALUE_COLORS[kpi.key] ?? "gray.800"}
        invertTrend={kpi.key === "failed"}
        helper={kpi.helper ?? METERING.KPI.HELPERS[kpi.key as keyof typeof METERING.KPI.HELPERS]}
      />
    ))}
  </SimpleGrid>
);

interface ConsumptionOverviewSectionProps {
  data: OverviewResponse;
  tenantOrganisationById?: Record<string, string>;
}

/** Consumption overview — usage concentration donut + top-tenant list. */
export const ConsumptionOverviewSection: React.FC<ConsumptionOverviewSectionProps> = ({
  data,
  tenantOrganisationById = {},
}) => {
  const conc = data.usage_concentration;
  const windowLabel = getWindowLabel(data.scope.window);
  const section = METERING.SECTIONS.CONSUMPTION_OVERVIEW;

  const pieData = useMemo(
    () =>
      (conc?.top_tenants ?? []).map((t, i) => ({
        name: formatTenantLabel(t.tenant, t.organisation, tenantOrganisationById),
        value: t.requests,
        color: meteringColorAt(i),
      })),
    [conc?.top_tenants, tenantOrganisationById],
  );

  if (!conc) return null;

  return (
    <MeteringSectionCard
      title={section.TITLE}
      subtitle={`${section.SUBTITLE_SUFFIX} ${windowLabel}`}
      sectionLabel
    >
      <VStack align="stretch" spacing={4}>
        <Box>
          <Text
            fontSize="xs"
            fontWeight="semibold"
            color="gray.500"
            textTransform="uppercase"
            letterSpacing="wider"
            mb={1}
          >
            {section.CONCENTRATION_TITLE}
          </Text>
          <Text fontSize="xs" color="gray.500">
            {section.CONCENTRATION_SUBTITLE}
          </Text>
        </Box>

        <Flex direction={{ base: "column", lg: "row" }} gap={8} align="center">
          <Box flex="1" w="full" maxW={{ lg: "360px" }} mx="auto">
            <MeteringDonutChart
              data={pieData}
              height={260}
              innerRadius={65}
              outerRadius={100}
              showTooltip
              centerPrimary={section.DONUT_PRIMARY}
              centerSecondary={section.DONUT_SECONDARY}
            />
          </Box>

          <RankedShareList
            rows={conc.top_tenants.map((row) => ({
              rank: row.rank,
              label: formatTenantLabel(row.tenant, row.organisation, tenantOrganisationById),
              formattedValue: row.formatted_requests,
              percentage: row.percentage,
            }))}
          />
        </Flex>
      </VStack>
    </MeteringSectionCard>
  );
};

interface PlatformAdoptionSectionProps {
  data: OverviewResponse;
}

export const PlatformAdoptionSection: React.FC<PlatformAdoptionSectionProps> = ({ data }) => {
  const adoption = data.platform_adoption;
  const section = METERING.SECTIONS.PLATFORM_ADOPTION;

  const activeByKey = useMemo(
    () => Object.fromEntries((data.active_tenants ?? []).map((cell) => [cell.key, cell])),
    [data.active_tenants],
  );

  if (!adoption && !data.active_tenants?.length) return null;

  const adoptionValues: Record<string, number | null | undefined> = {
    total_tenants: adoption?.total_tenants,
    new_tenants_7d: adoption?.new_tenants_7d,
    active_24h: adoption?.active_24h,
    active_7d: adoption?.active_7d,
    active_30d: adoption?.active_30d,
  };

  return (
    <MeteringSectionCard title={section.TITLE} subtitle={section.SUBTITLE} sectionLabel bare>
      <SimpleGrid columns={{ base: 1, sm: 2, lg: 5 }} spacing={4}>
        {section.CARDS.map((card) => {
          const activeCell = activeByKey[card.key];
          const adoptionValue = adoptionValues[card.key as keyof PlatformAdoption];

          return (
            <KpiCard
              key={card.key}
              label={activeCell?.label ?? card.label}
              value={
                activeCell?.value ??
                adoptionValue ??
                METERING.GRAPH.EMPTY_VALUE
              }
              pctChange={activeCell?.pct_change}
              helper={card.helper}
              valueColor="gray.800"
            />
          );
        })}
      </SimpleGrid>
    </MeteringSectionCard>
  );
};
