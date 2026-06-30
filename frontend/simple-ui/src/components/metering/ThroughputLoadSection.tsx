import { SimpleGrid } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, Tooltip, YAxis } from "recharts";
import { METERING } from "../../config/meteringConstants";
import { useMeteringChartColors } from "../../hooks/useMeteringChartColors";
import {
  extractMeteringRateChartData,
  formatMeteringPeakAt,
  formatMeteringRps,
  formatMeteringTooltipLabel,
  getWindowLabel,
} from "../../utils/meteringFormatters";
import type { MeteringGraph, MeteringWindow, ThroughputData } from "../../types/metering";
import MeteringChartPanel from "./MeteringChartPanel";
import MeteringChartTimeAxis from "./MeteringChartTimeAxis";
import MeteringSectionCard, { InlineMetricCard } from "./MeteringSectionCard";

interface ThroughputLoadSectionProps {
  throughput?: ThroughputData | null;
  /** Scope window from API response (not browser global). */
  timeWindow: MeteringWindow;
  requestVolumeGraph?: MeteringGraph | null;
  /** Optional 4th metric label/value (e.g. tenant total requests). */
  fourthMetric?: { label: string; value: string; helper: string };
}

const ThroughputLoadSection: React.FC<ThroughputLoadSectionProps> = ({
  throughput,
  timeWindow,
  requestVolumeGraph,
  fourthMetric,
}) => {
  const section = METERING.SECTIONS.THROUGHPUT;
  const windowLabel = getWindowLabel(timeWindow);
  const colors = useMeteringChartColors();

  const chartData = useMemo(
    () => extractMeteringRateChartData(requestVolumeGraph, timeWindow),
    [requestVolumeGraph, timeWindow],
  );

  return (
    <MeteringSectionCard
      title={section.TITLE}
      subtitle={`${section.SUBTITLE_PREFIX} ${windowLabel}`}
      sectionLabel
    >
      <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4} mb={6}>
        <InlineMetricCard
          label={section.AVG_RPS}
          value={formatMeteringRps(throughput?.avg_rps)}
          helper={section.AVG_RPS_HELPER}
          accent="orange.600"
        />
        <InlineMetricCard
          label={section.PEAK_RPS}
          value={formatMeteringRps(throughput?.peak_rps)}
          helper={section.PEAK_RPS_HELPER}
        />
        <InlineMetricCard
          label={section.PEAK_AT}
          value={formatMeteringPeakAt(throughput?.peak_at)}
          helper={section.PEAK_AT_HELPER}
          valueSize="lg"
        />
        {fourthMetric ? (
          <InlineMetricCard
            label={fourthMetric.label}
            value={fourthMetric.value}
            helper={fourthMetric.helper}
          />
        ) : null}
      </SimpleGrid>

      <MeteringChartPanel
        height={260}
        minWidth={280}
        title={section.CHART_TITLE}
        hasData={chartData.length > 0}
        emptyMessage={METERING.EMPTY.REQUEST_RATE}
      >
        {(size) => (
          <AreaChart width={size.width} height={size.height} data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} vertical={false} />
            <MeteringChartTimeAxis stroke={colors.axis} data={chartData} />
            <YAxis
              tick={{ fontSize: 11 }}
              stroke={colors.primaryStroke}
              tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v))}
            />
            <Tooltip
              contentStyle={{
                background: colors.tooltipBg,
                border: `1px solid ${colors.tooltipBorder}`,
                borderRadius: "8px",
                fontSize: "12px",
              }}
              formatter={(value: number) => [`${value.toLocaleString()} req/s`, section.AVG_RPS]}
              labelFormatter={(_, payload) => {
                const ts = payload?.[0]?.payload?.ts as number | undefined;
                return ts == null ? "" : formatMeteringTooltipLabel(ts, timeWindow);
              }}
            />
            <Area
              type="monotone"
              dataKey="rps"
              name={section.AVG_RPS}
              stroke={colors.primaryStroke}
              fill={colors.primaryFill}
              fillOpacity={0.65}
              strokeWidth={2}
            />
          </AreaChart>
        )}
      </MeteringChartPanel>
    </MeteringSectionCard>
  );
};

export default ThroughputLoadSection;
