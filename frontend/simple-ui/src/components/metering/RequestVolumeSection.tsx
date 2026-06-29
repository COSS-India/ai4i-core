import { SimpleGrid } from "@chakra-ui/react";
import React, { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  Tooltip,
  YAxis,
} from "recharts";
import { METERING } from "../../config/meteringConstants";
import { useMeteringChartColors } from "../../hooks/useMeteringChartColors";
import type { MeteringGraph, MeteringWindow, RequestHealth } from "../../types/metering";
import {
  buildRequestVolumeChartData,
  findMeteringSeries,
  formatCompactNumber,
  formatFailureRateDisplay,
  formatMeteringTooltipLabel,
  formatSuccessRateDisplay,
  parseCompactTotal,
  parseSuccessRatePct,
} from "../../utils/meteringFormatters";
import MeteringChartPanel from "./MeteringChartPanel";
import MeteringChartTimeAxis from "./MeteringChartTimeAxis";
import MeteringSectionCard, { SummaryMetricCard } from "./MeteringSectionCard";

interface RequestVolumeSectionProps {
  graph?: MeteringGraph | null;
  requestHealth?: RequestHealth | null;
  totalRequests?: string | number | null;
  successRate?: string | number | null;
  timeWindow: MeteringWindow;
}

const RequestVolumeSection: React.FC<RequestVolumeSectionProps> = ({
  graph,
  requestHealth,
  totalRequests,
  successRate,
  timeWindow,
}) => {
  const colors = useMeteringChartColors();
  const section = METERING.SECTIONS.REQUEST_VOLUME;

  const failureSeries = findMeteringSeries(
    graph,
    METERING.GRAPH.SERIES_KEYS.FAILURE_RATE,
  );

  const chartData = useMemo(
    () => buildRequestVolumeChartData(graph, timeWindow),
    [graph, timeWindow],
  );

  const total = requestHealth?.total_formatted ?? totalRequests ?? METERING.GRAPH.EMPTY_VALUE;
  const successPct = requestHealth?.success_rate_pct ?? parseSuccessRatePct(successRate);
  const rateDisplay = requestHealth
    ? `${requestHealth.success_rate_pct.toFixed(2)}%`
    : formatSuccessRateDisplay(successRate);
  const failedPct = formatFailureRateDisplay(requestHealth, successPct);

  const successfulValue = requestHealth?.successful_formatted ?? (() => {
    const totalNum = parseCompactTotal(totalRequests ?? total);
    if (totalNum == null || successPct == null) return METERING.GRAPH.EMPTY_VALUE;
    return formatCompactNumber(totalNum * (successPct / 100));
  })();

  const failedValue = requestHealth?.failed_formatted ?? (() => {
    const totalNum = parseCompactTotal(totalRequests ?? total);
    if (totalNum == null || successPct == null) return METERING.GRAPH.EMPTY_VALUE;
    return formatCompactNumber(totalNum * ((100 - successPct) / 100));
  })();

  const hasFailureSeries = Boolean(failureSeries?.points?.length);
  const hasRequestCounts = hasFailureSeries;

  const yAxisLabel = hasRequestCounts ? section.Y_AXIS_REQUESTS : section.Y_AXIS_RPS;

  return (
    <MeteringSectionCard
      title={section.TITLE}
      subtitle={hasRequestCounts ? section.SUBTITLE_WITH_FAILURE : section.SUBTITLE_RPS}
      sectionLabel
      bare
    >
      <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4} mb={6}>
        <SummaryMetricCard label={section.TOTAL} value={String(total)} leftBorderColor="gray.700" />
        <SummaryMetricCard
          label={section.SUCCESSFUL}
          value={successfulValue}
          helper={`${rateDisplay} ${section.SUCCESS_RATE_SUFFIX}`}
          leftBorderColor="green.400"
          helperColor="green.600"
        />
        <SummaryMetricCard
          label={section.FAILED}
          value={failedValue}
          helper={`${failedPct} ${section.FAILURE_RATE_SUFFIX}`}
          leftBorderColor="orange.400"
          helperColor="orange.500"
        />
      </SimpleGrid>

      <MeteringChartPanel height={340} hasData={chartData.length > 0}>
        {(size) => (
          <ComposedChart
            width={size.width}
            height={size.height}
            data={chartData}
            margin={{ top: 8, right: hasFailureSeries ? 48 : 16, left: 8, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} vertical={false} />
            <MeteringChartTimeAxis stroke={colors.axis} data={chartData} />
            <YAxis
              yAxisId="requests"
              tick={{ fontSize: 11 }}
              stroke={colors.primaryStroke}
              tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v))}
              label={{
                value: yAxisLabel,
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 10, fill: colors.primaryStroke, fontWeight: 600 },
              }}
            />
            {hasFailureSeries ? (
              <YAxis
                yAxisId="failure"
                orientation="right"
                tick={{ fontSize: 11 }}
                stroke={colors.failureStroke}
                tickFormatter={(v) => `${v}%`}
                domain={[0, 100]}
                label={{
                  value: section.Y_AXIS_FAILURE,
                  angle: 90,
                  position: "insideRight",
                  style: { fontSize: 10, fill: colors.failureStroke, fontWeight: 600 },
                }}
              />
            ) : null}
            <Tooltip
              contentStyle={{
                background: colors.tooltipBg,
                border: `1px solid ${colors.tooltipBorder}`,
                borderRadius: "8px",
                fontSize: "12px",
              }}
              labelFormatter={(_, payload) => {
                const ts = payload?.[0]?.payload?.ts as number | undefined;
                return ts != null ? formatMeteringTooltipLabel(ts, timeWindow) : "";
              }}
              formatter={(value: number, name: string) => {
                if (name === section.SERIES_FAILURE) {
                  return [`${value}%`, name];
                }
                if (hasRequestCounts) {
                  return [value.toLocaleString(), name];
                }
                return [`${value.toLocaleString()} req/s`, name];
              }}
            />
            <Area
              yAxisId="requests"
              type="monotone"
              dataKey="requests"
              name={hasRequestCounts ? section.SERIES_REQUESTS : section.SERIES_RPS}
              stroke={colors.primaryStroke}
              fill={colors.primaryFill}
              fillOpacity={0.6}
              strokeWidth={2}
            />
            {hasFailureSeries ? (
              <Line
                yAxisId="failure"
                type="monotone"
                dataKey="failureRate"
                name={section.SERIES_FAILURE}
                stroke={colors.failureStroke}
                strokeWidth={2}
                connectNulls={false}
                dot={false}
              />
            ) : null}
          </ComposedChart>
        )}
      </MeteringChartPanel>
    </MeteringSectionCard>
  );
};

export default RequestVolumeSection;
