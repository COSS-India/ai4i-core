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
  type RequestVolumeChartPoint,
} from "../../utils/meteringFormatters";
import MeteringChartPanel from "./MeteringChartPanel";
import MeteringSectionCard from "./MeteringSectionCard";

interface RequestVolumeSectionProps {
  graph?: MeteringGraph | null;
  timeWindow: MeteringWindow;
}

const RequestVolumeTooltip: React.FC<{
  active?: boolean;
  payload?: ReadonlyArray<{ payload: RequestVolumeChartPoint }>;
  timeWindow: MeteringWindow;
}> = ({ active, payload, timeWindow }) => {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;

  return (
    <Box bg="white" border="1px solid" borderColor="gray.200" borderRadius="lg" px={3} py={2.5} shadow="md" fontSize="sm" minW="140px">
      <Text fontWeight="semibold" color="gray.800" mb={1.5}>
        {formatMeteringTooltipLabel(point.ts, timeWindow)}
      </Text>
      <Text color="green.500" fontWeight="medium">{formatCompactNumber(point.successful)} successful</Text>
      <Text color="red.500" fontWeight="medium">{formatCompactNumber(point.failed)} failed</Text>
      <Text color="gray.600" mt={1}>{formatCompactNumber(point.requests)} total</Text>
    </Box>
  );
};

const RequestVolumeSection: React.FC<RequestVolumeSectionProps> = ({ graph, timeWindow }) => {
  const colors = useMeteringChartColors();
  const section = METERING.SECTIONS.REQUEST_VOLUME;
  const chartData = useMemo(() => buildRequestVolumeChartData(graph, timeWindow), [graph, timeWindow]);

  return (
    <MeteringSectionCard title={section.TITLE} subtitle={section.SUBTITLE} sectionLabel>
      <MeteringChartPanel height={340} hasData={chartData.length > 0} bare>
        {(size) => (
          <BarChart
            width={size.width}
            height={size.height}
            data={chartData}
            margin={{ top: 8, right: 16, left: 4, bottom: 24 }}
            barCategoryGap="20%"
          >
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} vertical={false} />
            <XAxis
              dataKey="label"
              stroke={colors.axis}
              tickLine={false}
              axisLine={{ stroke: colors.axis }}
              height={40}
              interval={0}
              minTickGap={1}
              tick={{ fontSize: 11, fill: colors.axis }}
            />
            <YAxis
              tick={{ fontSize: 11 }}
              stroke={colors.axis}
              tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v))}
              label={{
                value: section.Y_AXIS_REQUESTS,
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 10, fill: colors.axis, fontWeight: 600 },
              }}
            />
            <Tooltip
              cursor={{ fill: "rgba(148, 163, 184, 0.15)" }}
              content={<RequestVolumeTooltip timeWindow={timeWindow} />}
            />
            <Bar dataKey="successful" name={section.SUCCESSFUL} stackId="volume" fill={colors.successFill} maxBarSize={48} />
            <Bar dataKey="failed" name={section.FAILED} stackId="volume" fill={colors.failureStroke} radius={[4, 4, 0, 0]} maxBarSize={48} />
          </BarChart>
        )}
      </MeteringChartPanel>
    </MeteringSectionCard>
  );
};

export default RequestVolumeSection;
