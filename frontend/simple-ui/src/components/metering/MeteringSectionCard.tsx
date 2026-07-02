import {
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
  valueColor?: string;
  invertTrend?: boolean;   // true = an increase is "bad" (red), e.g. Failed
}

export const KpiCard: React.FC<KpiCardProps> = ({
  label,
  value,
  pctChange,
  helper,
  valueColor = "gray.800",
  invertTrend = false,
}) => {
  const trendColor =
    pctChange == null || pctChange === 0
      ? "gray.500"
      : (pctChange > 0) !== invertTrend
        ? "green.500"
        : "red.500";

  return (
    <Card variant="outline" borderColor="gray.200" bg="white" shadow="sm" borderRadius="lg" h="full">
      <CardBody py={5} px={5}>
        <VStack align="flex-start" spacing={3}>
          <Text
            fontSize="xs"
            fontWeight="semibold"
            color="gray.500"
            textTransform="uppercase"
            letterSpacing="wider"
          >
            {label}
          </Text>
          <Text fontSize="3xl" fontWeight="bold" color={valueColor} lineHeight="1.1">
            {value ?? "—"}
          </Text>
          {pctChange == null ? null : (
            <Text fontSize="sm" fontWeight="medium" color={trendColor}>
              {pctChange === 0 ? "→" : pctChange > 0 ? "↑" : "↓"}{" "}
              {Math.abs(pctChange).toFixed(1)}% vs previous
            </Text>
          )}
          {helper ? (
            <Text fontSize="xs" color="gray.500" lineHeight="short">
              {helper}
            </Text>
          ) : null}
        </VStack>
      </CardBody>
    </Card>
  );
};
