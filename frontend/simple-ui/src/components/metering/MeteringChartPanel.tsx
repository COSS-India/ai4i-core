import { Box, Center, Flex, Spinner, Text } from "@chakra-ui/react";
import React, { useEffect, useRef, useState } from "react";
import { METERING } from "../../constants";

interface MeteringChartPanelProps {
  height?: number;
  minWidth?: number;
  title?: string;
  emptyMessage?: string;
  /** When false, shows emptyMessage instead of the chart. Omit to always render the chart area. */
  hasData?: boolean;
  /** When true, skip the bordered panel wrapper (e.g. donut charts). */
  bare?: boolean;
  children: (size: { width: number; height: number }) => React.ReactNode;
}

/**
 * Responsive chart shell: measures container size for Recharts and optionally
 * renders title, empty state, and panel chrome.
 */
const MeteringChartPanel: React.FC<MeteringChartPanelProps> = ({
  height = 340,
  minWidth = 320,
  title,
  emptyMessage = METERING.EMPTY.CHART,
  hasData = true,
  bare = false,
  children,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || !containerRef.current) return;

    const node = containerRef.current;
    const updateSize = () => {
      const width = node.clientWidth;
      const nextHeight = node.clientHeight || height;
      if (width > 0 && nextHeight > 0) {
        setSize({ width, height: nextHeight });
      }
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(node);
    return () => observer.disconnect();
  }, [mounted, height]);

  const chartArea = (
    <Box
      ref={containerRef}
      w="100%"
      h={`${height}px`}
      minW={`${minWidth}px`}
      minH={`${height}px`}
    >
      {!mounted || size.width === 0 ? (
        <Center h="full">
          <Spinner size="md" color="orange.400" />
        </Center>
      ) : (
        children(size)
      )}
    </Box>
  );

  if (bare) {
    return chartArea;
  }

  return (
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
        chartArea
      ) : (
        <Flex h={`${height}px`} align="center" justify="center">
          <Text color="gray.500" fontSize="sm">
            {emptyMessage}
          </Text>
        </Flex>
      )}
    </Box>
  );
};

export default MeteringChartPanel;
