import { Box, Center, Spinner } from "@chakra-ui/react";
import React, { useEffect, useRef, useState } from "react";

interface MeteringChartContainerProps {
  height?: number;
  minWidth?: number;
  children: (size: { width: number; height: number }) => React.ReactNode;
}

/**
 * Measures a chart area after client mount so Recharts gets non-zero width/height.
 */
const MeteringChartContainer: React.FC<MeteringChartContainerProps> = ({
  height = 340,
  minWidth = 320,
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

  return (
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
};

export default MeteringChartContainer;
