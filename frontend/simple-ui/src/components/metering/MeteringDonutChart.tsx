import { Box, Flex, HStack, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { Cell, Pie, PieChart, Tooltip } from "recharts";
import { getMeteringChartColor } from "../../utils/meteringColors";
import MeteringChartPanel from "./MeteringChartPanel";

export interface DonutChartDatum {
  name: string;
  value: number;
  color: string;
}

export interface DonutLegendItem {
  name: string;
  color: string;
  pct?: number;
}

interface DonutTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<{
    name?: string;
    value?: number;
    payload?: DonutChartDatum;
  }>;
  total: number;
}

const DonutTooltip: React.FC<DonutTooltipProps> = ({ active, payload, total }) => {
  if (!active || !payload?.length) return null;

  const entry = payload[0];
  const name = entry.payload?.name ?? entry.name ?? "Unknown";
  const value = Number(entry.value ?? entry.payload?.value ?? 0);
  const pct = total > 0 ? ((value / total) * 100).toFixed(2) : "0.00";

  return (
    <Box
      bg="white"
      borderWidth="1px"
      borderColor="gray.200"
      borderRadius="md"
      px={3}
      py={2}
      shadow="lg"
      maxW="260px"
    >
      <Text fontSize="sm" fontWeight="semibold" color="gray.800" noOfLines={2}>
        {name}
      </Text>
      <Text fontSize="sm" color="gray.700" mt={1}>
        {value.toLocaleString()} requests
      </Text>
      <Text fontSize="xs" color="gray.500" mt={0.5}>
        {pct}% of total
      </Text>
    </Box>
  );
};

interface MeteringDonutChartProps {
  data: DonutChartDatum[];
  height?: number;
  innerRadius?: number;
  outerRadius?: number;
  showTooltip?: boolean;
  centerPrimary?: string;
  centerSecondary?: string;
  legendItems?: DonutLegendItem[];
  legendVariant?: "dotted" | "simple";
  chartMaxW?: string | Record<string, string>;
}

const DonutLegend: React.FC<{
  items: DonutLegendItem[];
  variant: "dotted" | "simple";
}> = ({ items, variant }) => (
  <VStack align="stretch" spacing={3} flex="1" w="full">
    {items.map((row) => (
      <HStack key={row.name} spacing={3} fontSize="sm">
        <Box w={2.5} h={2.5} borderRadius="full" bg={row.color} flexShrink={0} />
        <Text fontWeight="medium" minW="140px" noOfLines={1}>
          {row.name}
        </Text>
        {variant === "dotted" ? (
          <>
            <Box flex="1" borderBottom="1px dotted" borderColor="gray.300" mx={2} />
            {row.pct == null ? null : (
              <Text color="gray.600" fontWeight="medium" flexShrink={0}>
                {row.pct.toFixed(2)}%
              </Text>
            )}
          </>
        ) : null}
      </HStack>
    ))}
  </VStack>
);

const MeteringDonutChart: React.FC<MeteringDonutChartProps> = ({
  data,
  height = 280,
  innerRadius = 70,
  outerRadius = 110,
  showTooltip = true,
  centerPrimary,
  centerSecondary,
  legendItems,
  legendVariant = "dotted",
  chartMaxW,
}) => {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  if (data.length === 0) return null;

  const chart = (
    <Box
      w="100%"
      position="relative"
      overflow="visible"
      sx={{ "& .recharts-wrapper": { overflow: "visible" } }}
    >
      <MeteringChartPanel height={height} minWidth={240}>
        {(size) => (
          <PieChart width={size.width} height={size.height}>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              cx={size.width / 2}
              cy={size.height / 2}
              innerRadius={innerRadius}
              outerRadius={outerRadius}
              paddingAngle={2}
              stroke={getMeteringChartColor("DONUT_STROKE")}
              strokeWidth={2}
            >
              {data.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            {showTooltip ? (
              <Tooltip
                content={<DonutTooltip total={total} />}
                wrapperStyle={{ zIndex: 20, outline: "none" }}
                allowEscapeViewBox={{ x: true, y: true }}
              />
            ) : null}
          </PieChart>
        )}
      </MeteringChartPanel>
      {centerPrimary ? (
        <Box
          position="absolute"
          top="50%"
          left="50%"
          transform="translate(-50%, -50%)"
          textAlign="center"
          pointerEvents="none"
          zIndex={1}
        >
          <Text fontWeight="bold" fontSize="md" color="gray.700" lineHeight="1.2">
            {centerPrimary}
          </Text>
          {centerSecondary ? (
            <Text fontSize="sm" color="gray.500">
              {centerSecondary}
            </Text>
          ) : null}
        </Box>
      ) : null}
    </Box>
  );

  if (legendItems) {
    return (
      <Flex direction={{ base: "column", lg: "row" }} gap={6} align="center">
        <Box flex="1" w="full" maxW={chartMaxW ?? { lg: "50%" }} mx="auto">
          {chart}
        </Box>
        <DonutLegend items={legendItems} variant={legendVariant} />
      </Flex>
    );
  }

  return chart;
};

export default MeteringDonutChart;
