import { Box, Flex, HStack, Text, VStack } from "@chakra-ui/react";
import React from "react";
import MeteringDonutChart, { type DonutChartDatum } from "./MeteringDonutChart";

interface DonutLegendItem {
  name: string;
  color: string;
  pct?: number;
}

interface DonutWithLegendProps {
  data: DonutChartDatum[];
  legendItems?: DonutLegendItem[];
  height?: number;
  innerRadius?: number;
  outerRadius?: number;
  centerPrimary?: string;
  centerSecondary?: string;
  legendVariant?: "dotted" | "simple";
}

const DonutWithLegend: React.FC<DonutWithLegendProps> = ({
  data,
  legendItems,
  height = 280,
  innerRadius = 70,
  outerRadius = 110,
  centerPrimary,
  centerSecondary,
  legendVariant = "dotted",
}) => {
  const items: DonutLegendItem[] =
    legendItems ??
    data.map((row) => ({
      name: row.name,
      color: row.color,
      pct: undefined,
    }));

  return (
    <Flex direction={{ base: "column", lg: "row" }} gap={6} align="center">
      <Box flex="1" w="full" maxW={{ lg: "50%" }}>
        <MeteringDonutChart
          data={data}
          height={height}
          innerRadius={innerRadius}
          outerRadius={outerRadius}
          showTooltip
          centerPrimary={centerPrimary}
          centerSecondary={centerSecondary}
        />
      </Box>

      <VStack align="stretch" spacing={3} flex="1" w="full">
        {items.map((row) => (
          <HStack key={row.name} spacing={3} fontSize="sm">
            <Box w={2.5} h={2.5} borderRadius="full" bg={row.color} flexShrink={0} />
            <Text fontWeight="medium" minW="140px" noOfLines={1}>
              {row.name}
            </Text>
            {legendVariant === "dotted" ? (
              <>
                <Box flex="1" borderBottom="1px dotted" borderColor="gray.300" mx={2} />
                {row.pct != null ? (
                  <Text color="gray.600" fontWeight="medium" flexShrink={0}>
                    {row.pct.toFixed(2)}%
                  </Text>
                ) : null}
              </>
            ) : null}
          </HStack>
        ))}
      </VStack>
    </Flex>
  );
};

export default DonutWithLegend;
