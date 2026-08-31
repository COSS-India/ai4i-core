import { SimpleGrid, VStack } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import type { KeyMetricsSupplement, OverviewResponse } from "../../types/metering";
import {
  formatMeteringKpiValue,
  formatTenantLabel,
} from "../../utils/meteringFormatters";
import { meteringColorAt } from "../../utils/meteringColors";
import MeteringDonutChart, { DonutRankedLayout } from "./MeteringDonutChart";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import RankedShareList from "./RankedShareList";

interface OverviewKpiCardsProps {
  data: OverviewResponse;
  /** When false, omit the all-institutions helper on Total LLM Requests. */
  isPlatformWide?: boolean;
}

// Value colour per KPI: successful = green, failed = red, others neutral.
const KPI_VALUE_COLORS: Record<string, string> = {
  total_requests: "gray.800",
  successful: "green.500",
  failed: "red.500",
  avg_rps: "gray.800",
};

/** Top-row summary KPI cards (Total LLM Requests, Successful, Failed, Average RPS). */
export const OverviewKpiCards: React.FC<OverviewKpiCardsProps> = ({
  data,
  isPlatformWide = true,
}) => (
  <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
    {data.kpis.map((kpi) => {
      const fallbackHelper =
        kpi.key === METERING.KPI.KEYS.TOTAL_REQUESTS && !isPlatformWide
          ? undefined
          : METERING.KPI.HELPERS[kpi.key as keyof typeof METERING.KPI.HELPERS];
      return (
        <KpiCard
          key={kpi.key}
          label={METERING.KPI.LABELS[kpi.key as keyof typeof METERING.KPI.LABELS] ?? kpi.label}
          value={formatMeteringKpiValue(kpi.key, kpi.value)}
          pctChange={kpi.pct_change}
          valueColor={KPI_VALUE_COLORS[kpi.key] ?? "gray.800"}
          invertTrend={kpi.key === "failed"}
          helper={kpi.helper ?? fallbackHelper}
          tooltip={METERING.KPI.TOOLTIPS[kpi.key as keyof typeof METERING.KPI.TOOLTIPS]}
        />
      );
    })}
  </SimpleGrid>
);

interface ConsumptionOverviewSectionProps {
  data: OverviewResponse;
  tenantOrganisationById?: Record<string, string>;
}

/** Usage concentration — donut + top-institution list. */
export const ConsumptionOverviewSection: React.FC<ConsumptionOverviewSectionProps> = ({
  data,
  tenantOrganisationById = {},
}) => {
  const conc = data.usage_concentration;
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
      subtitle={section.SUBTITLE}
      sectionLabel
    >
      <DonutRankedLayout
        chart={
          <MeteringDonutChart
            data={pieData}
            height={260}
            innerRadius={65}
            outerRadius={100}
            showTooltip
            centerPrimary={section.DONUT_PRIMARY}
            centerSecondary={section.DONUT_SECONDARY}
          />
        }
        list={
          <RankedShareList
            rows={conc.top_tenants.map((row) => ({
              rank: row.rank,
              label: formatTenantLabel(row.tenant, row.organisation, tenantOrganisationById),
              formattedValue: row.formatted_requests,
              percentage: row.percentage,
            }))}
          />
        }
      />
    </MeteringSectionCard>
  );
};

interface PlatformAdoptionSectionProps {
  data: OverviewResponse;
  supplement?: KeyMetricsSupplement;
}

function formatGrowthPct(value: number | null | undefined): string {
  if (value == null) return METERING.GRAPH.EMPTY_VALUE;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

function renderKeyMetricCard(
  card: (typeof METERING.SECTIONS.KEY_METRICS.INSTITUTION_CARDS)[number] |
    (typeof METERING.SECTIONS.KEY_METRICS.MODEL_CARDS)[number],
  values: Record<string, number | null | undefined>,
) {
  const raw = values[card.key];
  const isGrowth = card.key === "model_usage_growth_pct";
  const value = isGrowth ? formatGrowthPct(raw) : (raw ?? METERING.GRAPH.EMPTY_VALUE);
  const valueColor =
    isGrowth && raw != null
      ? raw > 0
        ? "green.500"
        : raw < 0
          ? "red.500"
          : "gray.800"
      : "gray.800";

  return (
    <KpiCard
      key={card.key}
      label={card.label}
      value={value}
      helper={card.helper}
      tooltip={card.tooltip}
      valueColor={valueColor}
    />
  );
}

export const PlatformAdoptionSection: React.FC<PlatformAdoptionSectionProps> = ({
  data,
  supplement,
}) => {
  const adoption = data.platform_adoption;
  const section = METERING.SECTIONS.KEY_METRICS;

  if (!adoption) return null;

  const values: Record<string, number | null | undefined> = {
    total_tenants: adoption.total_tenants,
    new_tenants_15d: adoption.new_tenants_15d,
    active_30d: adoption.active_30d,
    total_models: supplement?.total_models,
    active_models_30d: supplement?.active_models_30d,
    tenants_budget_exhausted: supplement?.tenants_budget_exhausted,
    model_usage_growth_pct: adoption.model_usage_growth_pct,
  };

  return (
    <MeteringSectionCard title={section.TITLE} subtitle={section.SUBTITLE} sectionLabel bare>
      <VStack align="stretch" spacing={4}>
        <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
          {section.INSTITUTION_CARDS.map((card) => renderKeyMetricCard(card, values))}
        </SimpleGrid>
        <SimpleGrid columns={{ base: 1, sm: 2, lg: 3 }} spacing={4}>
          {section.MODEL_CARDS.map((card) => renderKeyMetricCard(card, values))}
        </SimpleGrid>
      </VStack>
    </MeteringSectionCard>
  );
};
