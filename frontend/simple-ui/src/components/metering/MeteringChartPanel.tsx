import { Box, Center, Flex, HStack, Spinner, Text } from "@chakra-ui/react";
import React, { useEffect, useRef, useState } from "react";
import { METERING } from "../../config/meteringConstants";

interface MeteringChartPanelProps {
  height?: number;
  minWidth?: number;
  children: (size: { width: number; height: number }) => React.ReactNode;
}

/** Responsive Recharts container. */
const MeteringChartPanel: React.FC<MeteringChartPanelProps> = ({
  height = 340,
  minWidth = 320,
  children,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted || !containerRef.current) return;
    const node = containerRef.current;
    const updateSize = () => {
      const width = node.clientWidth;
      const nextHeight = node.clientHeight || height;
      if (width > 0 && nextHeight > 0) setSize({ width, height: nextHeight });
    };
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(node);
    return () => observer.disconnect();
  }, [mounted, height]);

  return (
    <Box ref={containerRef} w="100%" h={`${height}px`} minW={`${minWidth}px`} minH={`${height}px`}>
      {!mounted || size.width === 0 ? (
        <Center h="full"><Spinner size="md" color="orange.400" /></Center>
      ) : (
        children(size)
      )}
    </Box>
  );
};

/** Shared "no data" placeholder — bar icon + message, no misleading zero axes. */
export const MeteringEmptyState: React.FC<{ height?: number; message?: string }> = ({
  height = 340,
  message = METERING.EMPTY.CHART,
}) => (
  <Flex h={`${height}px`} align="center" justify="center" direction="column" gap={3}>
    <HStack spacing={1} opacity={0.35} aria-hidden>
      {[16, 24, 12].map((h) => <Box key={h} w="7px" h={`${h}px`} bg="gray.400" borderRadius="sm" />)}
    </HStack>
    <Text color="gray.500" fontSize="sm" textAlign="center" px={4}>{message}</Text>
  </Flex>
);

export const MeteringSeriesLegend: React.FC<{
  items: ReadonlyArray<{ label: string; color: string }>;
}> = ({ items }) => (
  <HStack spacing={5} mt={3} px={1} fontSize="xs" color="gray.500">
    {items.map((item) => (
      <HStack key={item.label} spacing={2}>
        <Box w={2.5} h={2.5} borderRadius="sm" bg={item.color} />
        <Text>{item.label}</Text>
      </HStack>
    ))}
  </HStack>
);

export default MeteringChartPanel;
