import { Box, HStack, Icon, Text, Th, Tooltip } from "@chakra-ui/react";
import React from "react";
import { FiInfo } from "react-icons/fi";

interface MeteringInfoTipProps {
  label: string;
  tip: string;
  /** Icon size — KPIs use 3.5, table headers use 3. */
  boxSize?: number;
  maxW?: string;
}

/** Circled-i hover tip used on KPI labels and table column headers. */
export const MeteringInfoTip: React.FC<MeteringInfoTipProps> = ({
  label,
  tip,
  boxSize = 3.5,
  maxW = "260px",
}) => (
  <Tooltip label={tip} hasArrow placement="top" openDelay={200} maxW={maxW}>
    <Box as="span" display="inline-flex" cursor="help" color="gray.400" lineHeight={1}>
      <Icon as={FiInfo} boxSize={boxSize} aria-label={`${label} info`} />
    </Box>
  </Tooltip>
);

interface MeteringHeaderWithTipProps {
  label: string;
  tip?: string;
  isNumeric?: boolean;
  minW?: string | number;
  w?: string | number;
  /** Extra header styles (e.g. usage-spend letter-spacing). */
  sx?: Record<string, string | number>;
  onClick?: () => void;
  cursor?: string;
  userSelect?: "none" | "auto";
  children?: React.ReactNode;
}

/** Table `<Th>` with optional info tip beside the label. */
export const MeteringHeaderWithTip: React.FC<MeteringHeaderWithTipProps> = ({
  label,
  tip,
  isNumeric,
  minW,
  w,
  sx,
  onClick,
  cursor,
  userSelect,
  children,
}) => (
  <Th
    fontSize="xs"
    textTransform="uppercase"
    color="gray.500"
    isNumeric={isNumeric}
    minW={minW}
    w={w}
    sx={sx}
    onClick={onClick}
    cursor={cursor}
    userSelect={userSelect}
  >
    <HStack spacing={1} justify={isNumeric ? "flex-end" : "flex-start"}>
      {children ?? <Text as="span">{label}</Text>}
      {tip ? <MeteringInfoTip label={label} tip={tip} boxSize={3} maxW="240px" /> : null}
    </HStack>
  </Th>
);
