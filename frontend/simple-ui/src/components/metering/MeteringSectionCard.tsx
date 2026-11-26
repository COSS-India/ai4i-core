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
import { METERING } from "../../config/meteringConstants";
import InfoTip from "../common/InfoTip";

/** "↑ 12.5% vs previous", or "—" when the comparison is unavailable. */
function formatTrend(pctChange: number | null): string {
  if (pctChange === null) return METERING.GRAPH.EMPTY_VALUE;
  let arrow = "→";
  if (pctChange > 0) arrow = "↑";
  else if (pctChange < 0) arrow = "↓";
  return `${arrow} ${Math.abs(pctChange).toFixed(1)}% vs previous`;
}

interface MeteringSectionCardProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  /** Small grey section label (reference design). */
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
          <Text fontSize="sm" fontWeight="semibold" color="gray.600">
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
  /** Change vs the previous period. Omit for a card with no comparison; null shows "—" (comparison unavailable). */
  pctChange?: number | null;
  /** Sub-text under the value; a node when part of it needs its own hover tip. */
  helper?: React.ReactNode;
  valueColor?: string;
  /** Override default 3xl — use a smaller size for long string values. */
  valueFontSize?: string;
  invertTrend?: boolean;   // true = an increase is "bad" (red), e.g. Failed
  /** Hover explanation for computed / non-obvious metrics. */
  tooltip?: string;
}

export const KpiCard: React.FC<KpiCardProps> = ({
  label,
  value,
  pctChange,
  helper,
  valueColor = "gray.800",
  valueFontSize = "3xl",
  invertTrend = false,
  tooltip,
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
        <VStack align="stretch" spacing={3}>
          <HStack spacing={1.5} align="center">
            <Text fontSize="sm" fontWeight="semibold" color="gray.600">
              {label}
            </Text>
            {tooltip ? <InfoTip message={tooltip} /> : null}
          </HStack>
          <Text
            as="div"
            fontSize={valueFontSize}
            fontWeight="bold"
            color={valueColor}
            lineHeight="1.1"
            minW={0}
          >
            {value ?? "—"}
          </Text>
          {pctChange === undefined ? null : (
            <Text fontSize="sm" fontWeight="medium" color={trendColor}>
              {formatTrend(pctChange)}
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
