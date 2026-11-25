import { Box, HStack, Text } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { METERING } from "../../config/meteringConstants";
import { useMeteringChartColors } from "../../hooks/useMeteringChartColors";
import type { MeteringGraph, MeteringScope } from "../../types/metering";
import {
  buildRequestVolumeChartData,
  formatMeteringTooltipLabel,
  formatMeteringYTick,
  resolveMeteringChartScale,
  type MeteringChartScale,
  type RequestVolumeChartPoint,
} from "../../utils/meteringFormatters";
import MeteringChartPanel, {
  MeteringEmptyState,
  MeteringSeriesLegend,
} from "./MeteringChartPanel";
import MeteringSectionCard from "./MeteringSectionCard";

const RequestVolumeTooltip: React.FC<{
  active?: boolean;
  payload?: ReadonlyArray<{ payload: RequestVolumeChartPoint }>;
  scale: MeteringChartScale;
}> = ({ active, payload, scale }) => {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  const section = METERING.SECTIONS.REQUEST_VOLUME;
  // Exact counts (not 1.2K) so Total visibly equals Successful + Failed.
  const rows = [
    { label: section.TOTAL, value: p.requests, color: "gray.800" },
    { label: section.SUCCESSFUL, value: p.successful, color: "green.500" },
    { label: section.FAILED, value: p.failed, color: "red.500" },
  ];
  return (
    <Box bg="white" border="1px solid" borderColor="gray.200" borderRadius="lg" px={3} py={2.5} shadow="md" fontSize="sm" minW="180px">
      <Text fontWeight="semibold" color="gray.800" mb={1.5}>{formatMeteringTooltipLabel(p.ts, scale)}</Text>
      {rows.map((row) => (
        <HStack key={row.label} justify="space-between" spacing={4} color={row.color} fontWeight="medium">
          <Text>{row.label}</Text>
          <Text>{row.value.toLocaleString("en-IN")}</Text>
        </HStack>
      ))}
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
  const scale = useMemo(() => resolveMeteringChartScale(scope), [scope]);
  const chartData = useMemo(() => buildRequestVolumeChartData(graph, scale), [graph, scale]);

  return (
    <MeteringSectionCard title={section.TITLE} subtitle={section.SUBTITLE} sectionLabel>
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
                <Bar dataKey="successful" stackId="volume" fill={colors.successFill} maxBarSize={48} />
                <Bar dataKey="failed" stackId="volume" fill={colors.failureStroke} radius={[4, 4, 0, 0]} maxBarSize={48} />
              </BarChart>
            )}
          </MeteringChartPanel>
          <MeteringSeriesLegend items={[
            { label: section.SUCCESSFUL, color: colors.successFill },
            { label: section.FAILED, color: colors.failureStroke },
          ]} />
        </>
      )}
    </MeteringSectionCard>
  );
};

export default RequestVolumeSection;
