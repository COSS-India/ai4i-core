import { SimpleGrid, Text, VStack } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import type {
  KeyMetricsSupplement,
  MeteringCell,
  MeteringTopN,
  OverviewResponse,
} from "../../types/metering";
import {
  formatMeteringKpiValue,
  formatTenantLabel,
} from "../../utils/meteringFormatters";
import { meteringColorAt } from "../../utils/meteringColors";
import MeteringDonutChart, { DonutRankedLayout } from "./MeteringDonutChart";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import RankedShareList from "./RankedShareList";
import SegmentedTabBar from "./SegmentedTabBar";

interface OverviewKpiCardsProps {
  data: OverviewResponse;
  /** When false, omit the all-institutions helper on Total Requests. */
  isPlatformWide?: boolean;
  /** Institution Admin only: show the Fallback Requests / Successful / Failed cards after Failed. */
  showFallbackRequests?: boolean;
}

// Value colour per KPI: successful = green, failed = red, fallback = orange, others neutral.
const KPI_VALUE_COLORS: Record<string, string> = {
  total_requests: "gray.800",
  successful: "green.500",
  failed: "red.500",
  fallback_requests: "orange.500",
  fallback_successful: "green.500",
  fallback_failed: "red.500",
  avg_rps: "gray.800",
};

// An increase in these KPIs is bad, so their trend is shown red.
const INVERTED_TREND_KPIS = new Set<string>([
  METERING.KPI.KEYS.FAILED,
  METERING.KPI.KEYS.FALLBACK_REQUESTS,
  METERING.KPI.KEYS.FALLBACK_FAILED,
]);

// Fallback KPIs, in display order. Shown only to Institution Admins.
const FALLBACK_KPI_KEYS: readonly string[] = [
  METERING.KPI.KEYS.FALLBACK_REQUESTS,
  METERING.KPI.KEYS.FALLBACK_SUCCESSFUL,
  METERING.KPI.KEYS.FALLBACK_FAILED,
];

/** Drop the fallback KPIs, or reposition them so they sit right after Failed. */
function orderOverviewKpis(kpis: MeteringCell[], showFallbackRequests: boolean): MeteringCell[] {
  const rest = kpis.filter((kpi) => !FALLBACK_KPI_KEYS.includes(kpi.key));
  if (!showFallbackRequests) return rest;
  const fallbacks = FALLBACK_KPI_KEYS.flatMap((key) => kpis.filter((kpi) => kpi.key === key));
  if (fallbacks.length === 0) return rest;
  const failedIndex = rest.findIndex((kpi) => kpi.key === METERING.KPI.KEYS.FAILED);
  if (failedIndex === -1) return [...rest, ...fallbacks];
  return [...rest.slice(0, failedIndex + 1), ...fallbacks, ...rest.slice(failedIndex + 1)];
}

/** Top-row summary KPI cards (Total Requests, Successful, Failed, Average RPS). */
export const OverviewKpiCards: React.FC<OverviewKpiCardsProps> = ({
  data,
  isPlatformWide = true,
  showFallbackRequests = false,
}) => {
  const kpis = useMemo(
    () => orderOverviewKpis(data.kpis, showFallbackRequests),
    [data.kpis, showFallbackRequests],
  );
  return (
    <SimpleGrid columns={{ base: 1, sm: 2, lg: Math.max(kpis.length, 4) }} spacing={4}>
      {kpis.map((kpi) => {
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
            invertTrend={INVERTED_TREND_KPIS.has(kpi.key)}
            helper={kpi.helper ?? fallbackHelper}
            tooltip={METERING.KPI.TOOLTIPS[kpi.key as keyof typeof METERING.KPI.TOOLTIPS]}
          />
        );
      })}
    </SimpleGrid>
  );
};

interface ConsumptionOverviewSectionProps {
  data: OverviewResponse;
  tenantOrganisationById?: Record<string, string>;
  topN: MeteringTopN;
  onTopNChange: (n: MeteringTopN) => void;
  /** True when the All Institutions filter is narrowed to one institution. */
  isScopedTenant?: boolean;
}

/** Usage concentration — donut + top-institution list. */
export const ConsumptionOverviewSection: React.FC<ConsumptionOverviewSectionProps> = ({
  data,
  tenantOrganisationById = {},
  topN,
  onTopNChange,
  isScopedTenant = false,
}) => {
  const conc = data.usage_concentration;
  const section = METERING.SECTIONS.CONSUMPTION_OVERVIEW;
  const donutPrimary = `${METERING.CONTROLS.TOP_N_PREFIX} ${topN}`;

  const visibleTenants = useMemo(
    () => (conc?.top_tenants ?? []).slice(0, topN),
    [conc?.top_tenants, topN],
  );

  const pieData = useMemo(
    () =>
      visibleTenants.map((t, i) => ({
        name: formatTenantLabel(t.tenant, t.organisation, tenantOrganisationById),
        value: t.requests,
        color: meteringColorAt(i),
      })),
    [visibleTenants, tenantOrganisationById],
  );

  if (!conc) return null;

  return (
    <MeteringSectionCard
      title={section.TITLE}
      subtitle={section.SUBTITLE}
      sectionLabel
      action={
        isScopedTenant ? undefined : (
          <SegmentedTabBar
            options={[...METERING.TOP_N_SEGMENT_OPTIONS]}
            activeId={String(topN)}
            onChange={(id) => onTopNChange(Number(id) as MeteringTopN)}
          />
        )
      }
    >
      <DonutRankedLayout
        chart={
          <MeteringDonutChart
            data={pieData}
            height={260}
            innerRadius={65}
            outerRadius={100}
            showTooltip
            centerPrimary={donutPrimary}
            centerSecondary={section.DONUT_SECONDARY}
          />
        }
        list={
          <RankedShareList
            rows={visibleTenants.map((row) => ({
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

interface KeyMetricsSectionProps {
  data?: OverviewResponse;
  supplement?: KeyMetricsSupplement;
}

function formatGrowthPct(value: number | null | undefined): string {
  if (value == null) return METERING.GRAPH.EMPTY_VALUE;
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const formatted = Number.isInteger(abs) ? abs.toFixed(0) : abs.toFixed(1);
  return `${sign}${formatted}%`;
}

function keyMetricValueColor(
  key: string,
  raw: number | null | undefined,
): string {
  if (key === "tenants_budget_exhausted" && raw != null && raw > 0) return "red.500";
  if (key === "model_usage_growth_pct" && raw != null) {
    if (raw > 0) return "green.500";
    if (raw < 0) return "red.500";
  }
  return "gray.800";
}

function renderKeyMetricCard(
  card: (typeof METERING.SECTIONS.KEY_METRICS.INSTITUTION_CARDS)[number] |
    (typeof METERING.SECTIONS.KEY_METRICS.MODEL_CARDS)[number],
  values: Record<string, number | null | undefined>,
) {
  const raw = values[card.key];
  const isGrowth = card.key === "model_usage_growth_pct";
  const value = isGrowth ? formatGrowthPct(raw) : (raw ?? METERING.GRAPH.EMPTY_VALUE);

  return (
    <KpiCard
      key={card.key}
      label={card.label}
      value={value}
      helper={card.helper}
      tooltip={card.tooltip}
      valueColor={keyMetricValueColor(card.key, raw)}
    />
  );
}

export const KeyMetricsSection: React.FC<KeyMetricsSectionProps> = ({
  data,
  supplement,
}) => {
  const adoption = data?.platform_adoption;
  const section = METERING.SECTIONS.KEY_METRICS;

  const values: Record<string, number | null | undefined> = {
    total_tenants: adoption?.total_tenants,
    new_tenants_15d: adoption?.new_tenants_15d,
    active_30d: adoption?.active_30d,
    total_models: supplement?.total_models,
    active_models_30d: supplement?.active_models_30d,
    tenants_budget_exhausted: supplement?.tenants_budget_exhausted,
    model_usage_growth_pct: adoption?.model_usage_growth_pct,
  };

  return (
    <MeteringSectionCard title={section.TITLE} subtitle={section.SUBTITLE} bare>
      <VStack align="stretch" spacing={6}>
        <VStack align="stretch" spacing={3}>
          <Text
            fontSize="xs"
            fontWeight="semibold"
            color="gray.500"
            textTransform="uppercase"
            letterSpacing="wider"
          >
            {section.INSTITUTION_ROW_TITLE}
          </Text>
          <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
            {section.INSTITUTION_CARDS.map((card) => renderKeyMetricCard(card, values))}
          </SimpleGrid>
        </VStack>
        <VStack align="stretch" spacing={3}>
          <Text
            fontSize="xs"
            fontWeight="semibold"
            color="gray.500"
            textTransform="uppercase"
            letterSpacing="wider"
          >
            {section.MODEL_ROW_TITLE}
          </Text>
          <SimpleGrid columns={{ base: 1, sm: 2, lg: 3 }} spacing={4}>
            {section.MODEL_CARDS.map((card) => renderKeyMetricCard(card, values))}
          </SimpleGrid>
        </VStack>
      </VStack>
    </MeteringSectionCard>
  );
};
