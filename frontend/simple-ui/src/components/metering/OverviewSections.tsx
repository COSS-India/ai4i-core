import { Box, Flex, SimpleGrid, Text, VStack } from "@chakra-ui/react";
import React, { useMemo } from "react";
import type { OverviewResponse } from "../../types/metering";
import {
  formatMeteringKpiValue,
  formatTenantLabel,
  getWindowLabel,
  meteringColorAt,
} from "../../utils/meteringFormatters";
import MeteringDonutChart from "./MeteringDonutChart";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import RankedShareList from "./RankedShareList";

const KPI_HELPERS: Record<string, string> = {
  total_requests: "across selected window",
  success_rate: "of all requests",
  avg_rps: "requests per second",
  avg_requests_per_tenant: "across active tenants",
};

interface OverviewKpiCardsProps {
  data: OverviewResponse;
}

/** Top-row summary KPI cards (Total requests, Success rate, Avg RPS, Avg per tenant). */
export const OverviewKpiCards: React.FC<OverviewKpiCardsProps> = ({ data }) => (
  <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
    {data.kpis.map((kpi) => (
      <KpiCard
        key={kpi.key}
        label={kpi.label}
        value={formatMeteringKpiValue(kpi.key, kpi.value)}
        pctChange={kpi.pct_change}
        helper={KPI_HELPERS[kpi.key]}
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
      title="Consumption overview"
      subtitle={`reflects selected time window · ${windowLabel}`}
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
            Usage concentration
          </Text>
          <Text fontSize="xs" color="gray.500">
            Top 5 by request volume · reflects selected time window
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
              centerPrimary="Top 5"
              centerSecondary="tenants"
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

const ADOPTION_CARDS = [
  { key: "total_tenants", label: "Total tenants", helper: "registered on platform" },
  { key: "active_24h", label: "Active tenants", helper: "last 24 hours" },
  { key: "active_7d", label: "Active tenants", helper: "last 7 days" },
  { key: "active_30d", label: "Active tenants", helper: "last 30 days" },
  { key: "new_tenants_7d", label: "New — Last 7 days", helper: "onboarded in last 7 days" },
] as const;

interface PlatformAdoptionSectionProps {
  data: OverviewResponse;
}

export const PlatformAdoptionSection: React.FC<PlatformAdoptionSectionProps> = ({ data }) => {
  const adoption = data.platform_adoption;
  if (!adoption) return null;

  const values: Record<string, number | null | undefined> = {
    total_tenants: adoption.total_tenants,
    active_24h: adoption.active_24h,
    active_7d: adoption.active_7d,
    active_30d: adoption.active_30d,
    new_tenants_7d: adoption.new_tenants_7d,
  };

  return (
    <MeteringSectionCard title="Platform adoption" subtitle="Tenant overview" sectionLabel bare>
      <SimpleGrid columns={{ base: 1, sm: 2, lg: 5 }} spacing={4}>
        {ADOPTION_CARDS.map((card) => (
          <KpiCard
            key={card.key}
            label={card.label}
            value={values[card.key] ?? "—"}
            helper={card.helper}
            accent="teal"
          />
        ))}
      </SimpleGrid>
    </MeteringSectionCard>
  );
};
