import {
  Badge,
  Box,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
  Text,
  VStack,
} from "@chakra-ui/react";
import React from "react";

interface MeteringSectionCardProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  /** Uppercase grey section label (reference design). */
  sectionLabel?: boolean;
  /** Render title block only — no card wrapper. */
  bare?: boolean;
}

const MeteringSectionCard: React.FC<MeteringSectionCardProps> = ({
  title,
  subtitle,
  action,
  children,
  sectionLabel = false,
  bare = false,
}) => {
  const titleBlock = (
    <HStack justify="space-between" align="flex-start" flexWrap="wrap" gap={2} mb={sectionLabel || bare ? 3 : 0}>
      <VStack align="flex-start" spacing={0}>
        {sectionLabel ? (
          <Text
            fontSize="xs"
            fontWeight="semibold"
            color="gray.500"
            textTransform="uppercase"
            letterSpacing="wider"
          >
            {title}
          </Text>
        ) : (
          <Heading size="sm" color="gray.800">
            {title}
          </Heading>
        )}
        {subtitle ? (
          <Text fontSize="xs" color="gray.500" mt={0.5}>
            {subtitle}
          </Text>
        ) : null}
      </VStack>
      {action}
    </HStack>
  );

  if (bare) {
    return (
      <Box>
        {titleBlock}
        {children}
      </Box>
    );
  }

  return (
    <Card variant="outline" borderColor="gray.200" bg="white" shadow="sm">
      <CardHeader pb={subtitle ? 1 : 3}>{titleBlock}</CardHeader>
      <CardBody pt={subtitle ? 2 : 0}>{children}</CardBody>
    </Card>
  );
};

export default MeteringSectionCard;

interface KpiCardProps {
  label: string;
  value: React.ReactNode;
  pctChange?: number | null;
  helper?: string;
  accent?: string;
  invertTrend?: boolean;   // true = an increase is "bad" (red), e.g. Failed
}

export const KpiCard: React.FC<KpiCardProps> = ({
  label,
  value,
  pctChange,
  helper,
  accent = "orange",
  invertTrend = false,
}) => (
  <Card variant="outline" borderColor="gray.200" bg="white" shadow="sm" h="full">
    <CardBody>
      <VStack align="flex-start" spacing={2}>
        <Text fontSize="xs" fontWeight="semibold" color="gray.500" textTransform="uppercase" letterSpacing="wide">
          {label}
        </Text>
        <Box fontSize="2xl" fontWeight="bold" color={`${accent}.600`} lineHeight="1.2">
          {value ?? "—"}
        </Box>
        {pctChange == null ? null : (
          <HStack spacing={1}>
            <Badge
              colorScheme={pctChange === 0 ? "gray" : (pctChange > 0) !== invertTrend ? "green" : "red"}
              fontSize="xs"
              borderRadius="md"
            >
              {pctChange === 0 ? "→" : pctChange > 0 ? "↑" : "↓"} {Math.abs(pctChange)}% vs previous
            </Badge>
          </HStack>
        )}
        {helper ? (
          <Text fontSize="xs" color="gray.500">
            {helper}
          </Text>
        ) : null}
      </VStack>
    </CardBody>
  </Card>
);

interface SummaryMetricCardProps {
  label: string;
  value: React.ReactNode;
  helper?: string;
  leftBorderColor: string;
  valueColor?: string;
  helperColor?: string;
}

/** KPI card with a coloured left border (request volume & health summary). */
export const SummaryMetricCard: React.FC<SummaryMetricCardProps> = ({
  label,
  value,
  helper,
  leftBorderColor,
  valueColor = "gray.800",
  helperColor = "gray.500",
}) => (
  <Box
    p={5}
    bg="white"
    borderRadius="lg"
    borderWidth="1px"
    borderColor="gray.200"
    borderLeftWidth="4px"
    borderLeftColor={leftBorderColor}
    shadow="sm"
    h="full"
  >
    <Text
      fontSize="xs"
      color="gray.500"
      fontWeight="semibold"
      textTransform="uppercase"
      letterSpacing="wide"
    >
      {label}
    </Text>
    <Text fontSize="2xl" fontWeight="bold" color={valueColor} mt={2} lineHeight="1.2">
      {value}
    </Text>
    {helper ? (
      <Text fontSize="sm" color={helperColor} mt={1}>
        {helper}
      </Text>
    ) : null}
  </Box>
);

interface InlineMetricCardProps {
  label: string;
  value: React.ReactNode;
  helper?: string;
  accent?: string;
  valueSize?: "lg" | "2xl";
}

/** Compact metric tile used in throughput grids. */
export const InlineMetricCard: React.FC<InlineMetricCardProps> = ({
  label,
  value,
  helper,
  accent = "gray.800",
  valueSize = "2xl",
}) => (
  <Box p={4} borderWidth="1px" borderColor="gray.200" borderRadius="md" bg="white" h="full">
    <Text fontSize="xs" color="gray.500" fontWeight="semibold" textTransform="uppercase">
      {label}
    </Text>
    <Text fontSize={valueSize} fontWeight="bold" color={accent} mt={1}>
      {value}
    </Text>
    {helper ? (
      <Text fontSize="xs" color="gray.500" mt={1}>
        {helper}
      </Text>
    ) : null}
  </Box>
);
