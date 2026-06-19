import { useColorModeValue } from "@chakra-ui/react";
import { getMeteringChartColor } from "../utils/meteringColors";

/** Shared Recharts color tokens for metering area/composed charts. */
export function useMeteringChartColors() {
  const grid = useColorModeValue(
    getMeteringChartColor("GRID"),
    getMeteringChartColor("GRID_DARK"),
  );
  const tooltipBg = useColorModeValue("white", "gray.700");

  return {
    grid,
    axis: getMeteringChartColor("AXIS"),
    primaryStroke: getMeteringChartColor("PRIMARY_STROKE"),
    primaryFill: getMeteringChartColor("PRIMARY_FILL"),
    failureStroke: getMeteringChartColor("FAILURE_STROKE"),
    tooltipBorder: getMeteringChartColor("TOOLTIP_BORDER"),
    tooltipBg,
  };
}
