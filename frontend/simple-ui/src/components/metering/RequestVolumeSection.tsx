import { Box, HStack, Text, VStack } from "@chakra-ui/react";
import React, { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { METERING } from "../../constants";
import { useMeteringChartColors } from "../../hooks/useMeteringChartColors";
import type { MeteringGraph } from "../../types/metering";
import { buildRequestVolumeChartData } from "../../utils/meteringFormatters";
import MeteringChartPanel from "./MeteringChartPanel";
import MeteringSectionCard from "./MeteringSectionCard";

interface RequestVolumeSectionProps {
  graph?: MeteringGraph | null;
}

/**
 * Compact Y-axis tick label: 700 → "700", 350000 → "350K", 1000000 → "1M",
 * 1500000 → "1.5M". The axis range itself is auto-scaled by Recharts to the
 * data; this only controls how the (already dynamic) tick values are rendered
 * so large aggregated volumes read as compact units per the design.
 */
const formatRequestAxisTick = (v: number): string => {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(v);
};

type ChartColors = ReturnType<typeof useMeteringChartColors>;

const TooltipRow: React.FC<{
  dot?: string;
  label: string;
  value: string;
  emphasis?: boolean;
}> = ({ dot, label, value, emphasis }) => (
  <HStack justify="space-between" spacing={6}>
    <HStack spacing={2}>
      {dot ? <Box w={2} h={2} borderRadius="full" bg={dot} /> : <Box w={2} h={2} />}
      <Text color="gray.600" fontWeight={emphasis ? "semibold" : "normal"}>
        {label}
      </Text>
    </HStack>
    <Text color="gray.800" fontWeight={emphasis ? "bold" : "medium"}>
      {value}
    </Text>
  </HStack>
);

interface RequestVolumeTooltipProps {
  active?: boolean;
  label?: string;
  payload?: ReadonlyArray<{ dataKey?: string | number; value?: number }>;
  colors: ChartColors;
}

/** Custom tooltip: time bucket + successful / failed / total / failure rate. */
const RequestVolumeTooltip: React.FC<RequestVolumeTooltipProps> = ({
  active,
  label,
  payload,
  colors,
}) => {
  if (!active || !payload?.length) return null;
  const section = METERING.SECTIONS.REQUEST_VOLUME;
  const valueOf = (key: string) =>
    Number(payload.find((p) => p.dataKey === key)?.value ?? 0);
  const successful = valueOf("successful");
  const failed = valueOf("failed");
  const total = successful + failed;
  const failureRate = total > 0 ? (failed / total) * 100 : 0;

  return (
    <Box
      bg={colors.tooltipBg}
      borderWidth="1px"
      borderColor={colors.tooltipBorder}
      borderRadius="8px"
      px={3}
      py={2.5}
      fontSize="12px"
      minW="190px"
      boxShadow="lg"
    >
      <Text fontWeight="semibold" color="gray.700" mb={2}>
        {label}
      </Text>
      <VStack align="stretch" spacing={1.5}>
        <TooltipRow
          dot={colors.primaryStroke}
          label={section.SERIES_SUCCESSFUL}
          value={successful.toLocaleString()}
        />
        <TooltipRow
          dot={colors.failureStroke}
          label={section.SERIES_FAILED}
          value={failed.toLocaleString()}
        />
        <Box borderTopWidth="1px" borderColor="gray.200" my={0.5} />
        <TooltipRow label="Total" value={total.toLocaleString()} emphasis />
        <TooltipRow label="Failure rate" value={`${failureRate.toFixed(2)}%`} />
      </VStack>
    </Box>
  );
};

const RequestVolumeSection: React.FC<RequestVolumeSectionProps> = ({ graph }) => {
  const colors = useMeteringChartColors();
  const section = METERING.SECTIONS.REQUEST_VOLUME;

  const chartData = useMemo(() => buildRequestVolumeChartData(graph), [graph]);

  return (
    <MeteringSectionCard
      title={section.TITLE}
      subtitle={section.SUBTITLE}
      sectionLabel
      bare
    >
      <MeteringChartPanel height={340} hasData={chartData.length > 0}>
        {(size) => (
          <BarChart
            width={size.width}
            height={size.height}
            data={chartData}
            margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke={colors.axis} />
            <YAxis
              tick={{ fontSize: 11 }}
              stroke={colors.primaryStroke}
              tickFormatter={formatRequestAxisTick}
              label={{
                value: section.Y_AXIS_REQUESTS,
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 10, fill: colors.primaryStroke, fontWeight: 600 },
              }}
            />
            <Tooltip
              cursor={{ fill: colors.tooltipBorder, fillOpacity: 0.15 }}
              content={<RequestVolumeTooltip colors={colors} />}
            />
            <Legend wrapperStyle={{ fontSize: "12px" }} />
            <Bar
              dataKey="successful"
              name={section.SERIES_SUCCESSFUL}
              stackId="requests"
              fill={colors.primaryStroke}
              radius={[0, 0, 0, 0]}
            />
            <Bar
              dataKey="failed"
              name={section.SERIES_FAILED}
              stackId="requests"
              fill={colors.failureStroke}
              radius={[2, 2, 0, 0]}
            />
          </BarChart>
        )}
      </MeteringChartPanel>
    </MeteringSectionCard>
  );
};

export default RequestVolumeSection;
