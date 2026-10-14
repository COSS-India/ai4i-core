import { Box, Text } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Tooltip, XAxis, YAxis } from "recharts";
import { METERING } from "../../config/meteringConstants";
import { useMeteringChartColors } from "../../hooks/useMeteringChartColors";
import type { MeteringGraph, MeteringScope } from "../../types/metering";
import {
  buildRequestVolumeChartData,
  formatCompactNumber,
  formatMeteringTooltipLabel,
  formatMeteringYTick,
  resolveMeteringChartScale,
  type MeteringChartScale,
  type RequestVolumeChartPoint,
} from "../../utils/meteringFormatters";
import { estimatedUntilSeconds, formatCoverageInstant } from "../../utils/meteringCoverage";
import MeteringChartPanel, {
  MeteringEmptyState,
  MeteringSeriesLegend,
} from "./MeteringChartPanel";
import MeteringSectionCard from "./MeteringSectionCard";

/** Estimated buckets are drawn at this opacity. */
const ESTIMATED_OPACITY = 0.4;

const RequestVolumeTooltip: React.FC<{
  active?: boolean;
  payload?: ReadonlyArray<{ payload: RequestVolumeChartPoint }>;
  scale: MeteringChartScale;
}> = ({ active, payload, scale }) => {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <Box bg="white" border="1px solid" borderColor="gray.200" borderRadius="lg" px={3} py={2.5} shadow="md" fontSize="sm" minW="140px">
      <Text fontWeight="semibold" color="gray.800" mb={1.5}>{formatMeteringTooltipLabel(p.ts, scale)}</Text>
      <Text color="green.500" fontWeight="medium">{formatCompactNumber(p.successful)} successful</Text>
      <Text color="red.500" fontWeight="medium">{formatCompactNumber(p.failed)} failed</Text>
      <Text color="gray.600" mt={1}>{formatCompactNumber(p.requests)} total</Text>
      {p.estimated ? (
        <Text color="gray.500" fontSize="xs" mt={1}>{METERING.COVERAGE.ESTIMATED_LEGEND}</Text>
      ) : null}
    </Box>
  );
};

const RequestVolumeSection: React.FC<{
  graph?: MeteringGraph | null;
  /** Scope of the response `graph` came from; drives the label format. */
  scope: MeteringScope;
}> = ({ graph, scope }) => {
  const colors = useMeteringChartColors();
  const section = METERING.SECTIONS.REQUEST_VOLUME;
  const coverage = METERING.COVERAGE;
  const scale = useMemo(() => resolveMeteringChartScale(scope), [scope]);
  // Estimated days only have daily totals: daily and weekly buckets from
  // before the estimates end are drawn lighter; hourly ones have no data.
  const estimatedUntil = estimatedUntilSeconds(scope.period);
  const chartData = useMemo(
    () =>
      buildRequestVolumeChartData(graph, scale).map((p) => ({
        ...p,
        estimated: !scale.intraday && estimatedUntil != null && p.ts < estimatedUntil,
      })),
    [graph, scale, estimatedUntil],
  );
  const hasEstimated = chartData.some((p) => p.estimated);
  const hourlyNote =
    scale.intraday && estimatedUntil != null && scope.period.estimatedUntil
      ? `${coverage.HOURLY_UNAVAILABLE_PREFIX} ${formatCoverageInstant(scope.period.estimatedUntil)}${coverage.HOURLY_UNAVAILABLE_SUFFIX}`
      : null;

  return (
    <MeteringSectionCard title={section.TITLE} subtitle={section.SUBTITLE} sectionLabel>
      {hourlyNote ? (
        <Text fontSize="xs" color="gray.500" mb={2}>{hourlyNote}</Text>
      ) : null}
      {chartData.length === 0 ? (
        <MeteringEmptyState />
      ) : (
        <>
          <MeteringChartPanel height={300}>
            {(size) => (
              <BarChart width={size.width} height={size.height} data={chartData} margin={{ top: 8, right: 16, left: 4, bottom: 24 }} barCategoryGap="20%">
                <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} vertical={false} />
                <XAxis dataKey="label" stroke={colors.axis} tickLine={false} axisLine={{ stroke: colors.axis }} height={40} interval={0} minTickGap={1} tick={{ fontSize: 11, fill: colors.axis }} />
                <YAxis
                  tick={{ fontSize: 11, fill: colors.axis }}
                  stroke={colors.axis}
                  tickFormatter={formatMeteringYTick}
                  label={{ value: section.Y_AXIS_REQUESTS, angle: -90, position: "insideLeft", style: { fontSize: 10, fill: colors.axis, fontWeight: 600 } }}
                />
                <Tooltip cursor={{ fill: "rgba(148, 163, 184, 0.15)" }} content={<RequestVolumeTooltip scale={scale} />} />
                <Bar dataKey="successful" stackId="volume" fill={colors.successFill} maxBarSize={48}>
                  {chartData.map((p) => (
                    <Cell key={p.ts} fillOpacity={p.estimated ? ESTIMATED_OPACITY : 1} />
                  ))}
                </Bar>
                <Bar dataKey="failed" stackId="volume" fill={colors.failureStroke} radius={[4, 4, 0, 0]} maxBarSize={48}>
                  {chartData.map((p) => (
                    <Cell key={p.ts} fillOpacity={p.estimated ? ESTIMATED_OPACITY : 1} />
                  ))}
                </Bar>
              </BarChart>
            )}
          </MeteringChartPanel>
          <MeteringSeriesLegend items={[
            { label: section.SUCCESSFUL, color: colors.successFill },
            { label: section.FAILED, color: colors.failureStroke },
            ...(hasEstimated
              ? [{ label: coverage.ESTIMATED_LEGEND, color: colors.successFill, opacity: ESTIMATED_OPACITY }]
              : []),
          ]} />
        </>
      )}
    </MeteringSectionCard>
  );
};

export default RequestVolumeSection;
