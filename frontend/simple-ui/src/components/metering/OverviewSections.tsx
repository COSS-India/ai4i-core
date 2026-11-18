import { Box, SimpleGrid, Tooltip, VStack } from "@chakra-ui/react";
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
  parseCompactTotal,
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
  /**
   * Institution Admin only: split the cards into a Requests group and a
   * Fallback group (Fallback Requests / Successful / Failed), each titled.
   */
  showFallbackRequests?: boolean;
}

const KPI_KEYS = METERING.KPI.KEYS;

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
  KPI_KEYS.FAILED,
  KPI_KEYS.FALLBACK_REQUESTS,
  KPI_KEYS.FALLBACK_FAILED,
]);

// Fallback KPIs, in display order. Shown only to Institution Admins.
const FALLBACK_KPI_KEYS: readonly string[] = [
  KPI_KEYS.FALLBACK_REQUESTS,
  KPI_KEYS.FALLBACK_SUCCESSFUL,
  KPI_KEYS.FALLBACK_FAILED,
];

// Cards whose helper is a rate of another card's count: rate key → the count it is a rate of.
const RATE_BASE_KPI: Record<string, string> = {
  [KPI_KEYS.SUCCESSFUL]: KPI_KEYS.TOTAL_REQUESTS,
  [KPI_KEYS.FAILED]: KPI_KEYS.TOTAL_REQUESTS,
  [KPI_KEYS.FALLBACK_SUCCESSFUL]: KPI_KEYS.FALLBACK_REQUESTS,
  [KPI_KEYS.FALLBACK_FAILED]: KPI_KEYS.FALLBACK_REQUESTS,
};

/** True when a KPI count (formatted by the API, e.g. "0", "1.2K") is zero. */
function isZeroCount(cell: MeteringCell | undefined): boolean {
  return cell?.value != null && parseCompactTotal(cell.value) === 0;
}

/**
 * A rate of nothing has no value, so an em dash alone replaces the API's
 * "0.00% success rate" / "0.00% failure rate". The fallback rates explain it on hover.
 */
function noRateHelper(key: string): React.ReactNode {
  const dash = METERING.GRAPH.EMPTY_VALUE;
  if (!FALLBACK_KPI_KEYS.includes(key)) return dash;
  const tip = METERING.KPI.NO_RATE.NO_FALLBACKS_TOOLTIP;
  return (
    <Tooltip label={tip} hasArrow placement="top" openDelay={200}>
      <Box as="span" cursor="help" aria-label={tip}>
        {dash}
      </Box>
    </Tooltip>
  );
}

interface KpiCardGridProps {
  kpis: MeteringCell[];
  byKey: Map<string, MeteringCell>;
  isPlatformWide: boolean;
  columns: number;
}

const KpiCardGrid: React.FC<KpiCardGridProps> = ({ kpis, byKey, isPlatformWide, columns }) => (
  <SimpleGrid columns={{ base: 1, sm: 2, lg: columns }} spacing={4}>
    {kpis.map((kpi) => {
      const fallbackHelper =
        kpi.key === KPI_KEYS.TOTAL_REQUESTS && !isPlatformWide
          ? undefined
          : METERING.KPI.HELPERS[kpi.key as keyof typeof METERING.KPI.HELPERS];
      const rateBase = RATE_BASE_KPI[kpi.key];
      const helper =
        rateBase && isZeroCount(byKey.get(rateBase))
          ? noRateHelper(kpi.key)
          : (kpi.helper ?? fallbackHelper);
      return (
        <KpiCard
          key={kpi.key}
          label={METERING.KPI.LABELS[kpi.key as keyof typeof METERING.KPI.LABELS] ?? kpi.label}
          value={formatMeteringKpiValue(kpi.key, kpi.value)}
          pctChange={kpi.pct_change}
          valueColor={KPI_VALUE_COLORS[kpi.key] ?? "gray.800"}
          invertTrend={INVERTED_TREND_KPIS.has(kpi.key)}
          helper={helper}
          tooltip={METERING.KPI.TOOLTIPS[kpi.key as keyof typeof METERING.KPI.TOOLTIPS]}
        />
      );
    })}
  </SimpleGrid>
);

/**
 * Summary KPI cards: Total, Successful, Failed and Average Requests per Second.
 * Institution Admins also get the Fallback cards, as a separate titled group.
 */
export const OverviewKpiCards: React.FC<OverviewKpiCardsProps> = ({
  data,
  isPlatformWide = true,
  showFallbackRequests = false,
}) => {
  const { requestKpis, fallbackKpis, byKey } = useMemo(() => {
    const fallbacks = FALLBACK_KPI_KEYS.flatMap((key) =>
      data.kpis.filter((kpi) => kpi.key === key),
    );
    return {
      requestKpis: data.kpis.filter((kpi) => !FALLBACK_KPI_KEYS.includes(kpi.key)),
      fallbackKpis: fallbacks,
      byKey: new Map(data.kpis.map((kpi) => [kpi.key, kpi])),
    };
  }, [data.kpis]);

  const requestGrid = (
    <KpiCardGrid
      kpis={requestKpis}
      byKey={byKey}
      isPlatformWide={isPlatformWide}
      columns={Math.max(requestKpis.length, 4)}
    />
  );

  if (!showFallbackRequests) return requestGrid;

  const groups = METERING.KPI.GROUPS;
  return (
    <VStack align="stretch" spacing={6}>
      <MeteringSectionCard title={groups.REQUESTS_TITLE} sectionLabel bare>
        {requestGrid}
      </MeteringSectionCard>
      {/* Only the usage_events metering store records fallbacks; other stores omit them. */}
      {fallbackKpis.length > 0 ? (
        <MeteringSectionCard
          title={groups.FALLBACK_TITLE}
          subtitle={groups.FALLBACK_SUBTITLE}
          sectionLabel
          bare
        >
          <KpiCardGrid
            kpis={fallbackKpis}
            byKey={byKey}
            isPlatformWide={isPlatformWide}
            columns={3}
          />
        </MeteringSectionCard>
      ) : null}
    </VStack>
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

interface PlatformOverviewSectionProps {
  data?: OverviewResponse;
  supplement?: KeyMetricsSupplement;
}

type PlatformOverviewCard =
  | (typeof METERING.SECTIONS.PLATFORM_OVERVIEW.INSTITUTION_CARDS)[number]
  | (typeof METERING.SECTIONS.PLATFORM_OVERVIEW.MODEL_CARDS)[number];

function formatGrowthPct(value: number | null | undefined): string {
  if (value == null) return METERING.GRAPH.EMPTY_VALUE;
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const formatted = Number.isInteger(abs) ? abs.toFixed(0) : abs.toFixed(1);
  return `${sign}${formatted}%`;
}

function platformMetricValueColor(
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

function renderPlatformMetricCard(
  card: PlatformOverviewCard,
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
      helper={"helper" in card ? card.helper : undefined}
      tooltip={card.tooltip}
      valueColor={platformMetricValueColor(card.key, raw)}
    />
  );
}

/** Adopter Admin: Institution and Model summary cards under one "Platform Overview" heading. */
export const PlatformOverviewSection: React.FC<PlatformOverviewSectionProps> = ({
  data,
  supplement,
}) => {
  const adoption = data?.platform_adoption;
  const section = METERING.SECTIONS.PLATFORM_OVERVIEW;

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
      <VStack align="stretch" spacing={4}>
        <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
          {section.INSTITUTION_CARDS.map((card) => renderPlatformMetricCard(card, values))}
        </SimpleGrid>
        <SimpleGrid columns={{ base: 1, sm: 2, lg: 3 }} spacing={4}>
          {section.MODEL_CARDS.map((card) => renderPlatformMetricCard(card, values))}
        </SimpleGrid>
      </VStack>
    </MeteringSectionCard>
  );
};
