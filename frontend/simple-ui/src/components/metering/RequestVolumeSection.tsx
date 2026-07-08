import { Box, Text } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { METERING } from "../../config/meteringConstants";
import { useMeteringChartColors } from "../../hooks/useMeteringChartColors";
import type { MeteringGraph, MeteringWindow } from "../../types/metering";
import {
  buildRequestVolumeChartData,
  formatCompactNumber,
  formatMeteringTooltipLabel,
  formatMeteringYTick,
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
  timeWindow: MeteringWindow;
}> = ({ active, payload, timeWindow }) => {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <Box bg="white" border="1px solid" borderColor="gray.200" borderRadius="lg" px={3} py={2.5} shadow="md" fontSize="sm" minW="140px">
      <Text fontWeight="semibold" color="gray.800" mb={1.5}>{formatMeteringTooltipLabel(p.ts, timeWindow)}</Text>
      <Text color="green.500" fontWeight="medium">{formatCompactNumber(p.successful)} successful</Text>
      <Text color="red.500" fontWeight="medium">{formatCompactNumber(p.failed)} failed</Text>
      <Text color="gray.600" mt={1}>{formatCompactNumber(p.requests)} total</Text>
    </Box>
  );
};

const RequestVolumeSection: React.FC<{ graph?: MeteringGraph | null; timeWindow: MeteringWindow }> = ({
  graph, timeWindow,
}) => {
  const colors = useMeteringChartColors();
  const section = METERING.SECTIONS.REQUEST_VOLUME;
  const chartData = useMemo(() => buildRequestVolumeChartData(graph, timeWindow), [graph, timeWindow]);

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
                <Tooltip cursor={{ fill: "rgba(148, 163, 184, 0.15)" }} content={<RequestVolumeTooltip timeWindow={timeWindow} />} />
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
