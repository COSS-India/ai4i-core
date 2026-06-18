import { Box, Flex, Text } from "@chakra-ui/react";
import React from "react";
import MeteringChartContainer from "./MeteringChartContainer";

interface MeteringChartPanelProps {
  height?: number;
  minWidth?: number;
  title?: string;
  emptyMessage?: string;
  hasData: boolean;
  children: (size: { width: number; height: number }) => React.ReactNode;
}

const MeteringChartPanel: React.FC<MeteringChartPanelProps> = ({
  height = 340,
  minWidth = 320,
  title,
  emptyMessage = "No chart data available for the selected window.",
  hasData,
  children,
}) => (
  <Box w="full" borderWidth="1px" borderColor="gray.200" borderRadius="lg" bg="white" p={4} overflow="visible">
    {title ? (
      <Text
        fontSize="xs"
        color="gray.500"
        fontWeight="semibold"
        textTransform="uppercase"
        mb={3}
      >
        {title}
      </Text>
    ) : null}
    {hasData ? (
      <MeteringChartContainer height={height} minWidth={minWidth}>
        {children}
      </MeteringChartContainer>
    ) : (
      <Flex h={`${height}px`} align="center" justify="center">
        <Text color="gray.500" fontSize="sm">
          {emptyMessage}
        </Text>
      </Flex>
    )}
  </Box>
);

export default MeteringChartPanel;
