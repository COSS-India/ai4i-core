import { Box, Center, Flex, HStack, Spinner, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import {
  formatBudgetEffectiveRange,
  formatSpendMoneyExact,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageItem } from "../../types/usageSpend";
import SpendByTaskTypeTable from "./SpendByTaskTypeTable";
import { BudgetCell, TenantAvatar, TierBadge } from "./UsageSpendCells";

const sectionLabelSx = {
  fontSize: "11px",
  letterSpacing: "0.04em",
  color: "gray.600",
  fontWeight: "semibold",
  textTransform: "uppercase" as const,
};

const cardSx = {
  bg: "white",
  borderWidth: "1px",
  borderColor: "gray.200",
  borderRadius: "12px",
  p: { base: "16px", md: "20px 22px" },
};

interface InstitutionUsageDetailContentProps {
  detail: TenantUsageItem;
  /** Selected period, e.g. "Last 7 days". */
  periodTitle: string;
  isLoading?: boolean;
}

export const InstitutionUsageDetailContent: React.FC<InstitutionUsageDetailContentProps> = ({
  detail,
  periodTitle,
  isLoading = false,
}) => {
  const budget = detail.budget;
  const effectiveRange = formatBudgetEffectiveRange(
    budget?.budgetEffectiveFrom,
    budget?.budgetEffectiveTo,
  );
  const hasMultiTier = (detail.tierBreakdown?.length ?? 0) > 1;

  return (
    <VStack align="stretch" spacing={4}>
      <Box {...cardSx} opacity={isLoading ? 0.6 : 1}>
        <Flex justify="space-between" align="flex-start" gap={3} mb={4} flexWrap="wrap">
          <Text {...sectionLabelSx}>{METERING.USAGE_SPEND.BUDGET}</Text>
          {effectiveRange ? (
            <Text fontSize="12px" color="gray.500" textAlign="right">
              {effectiveRange}
            </Text>
          ) : null}
        </Flex>
        {isLoading ? (
          <Center minH="72px">
            <Spinner size="sm" />
          </Center>
        ) : budget ? (
          <BudgetCell
            limit={budget.limit}
            spent={budget.spent}
            remaining={budget.remaining}
            percentageUsed={budget.percentageUsed}
            currency={detail.currency}
          />
        ) : (
          <Text fontSize="sm" color="gray.500">
            No budget assigned.
          </Text>
        )}
        <Text fontSize="11.5px" color="gray.500" mt={3}>
          {METERING.USAGE_SPEND.BUDGET_TOTALS_NOTE}
        </Text>
      </Box>

      <Box {...cardSx} opacity={isLoading ? 0.6 : 1}>
        <Flex justify="space-between" align="flex-start" gap={3} mb={2} flexWrap="wrap">
          <Text {...sectionLabelSx}>{METERING.USAGE_SPEND.PERIOD_SPEND}</Text>
          <Text fontSize="12px" color="gray.500" textAlign="right">
            {periodTitle}
          </Text>
        </Flex>
        <Text fontSize="22px" fontWeight="bold" color="gray.800">
          {formatSpendMoneyExact(detail.periodSpend, detail.currency)}
        </Text>
      </Box>

      <Box {...cardSx} opacity={isLoading ? 0.6 : 1}>
        <Flex justify="space-between" align="flex-start" gap={3} mb={4} flexWrap="wrap">
          <Text {...sectionLabelSx}>{METERING.USAGE_SPEND.USAGE_BY_TASK_TYPE}</Text>
          <Text fontSize="12px" color="gray.500" textAlign="right">
            {periodTitle}
          </Text>
        </Flex>
        <SpendByTaskTypeTable
          tierBreakdown={detail.tierBreakdown ?? []}
          currency={detail.currency}
        />
        <Text fontSize="11.5px" color="gray.500" lineHeight="1.5" mt={3}>
          {hasMultiTier
            ? METERING.USAGE_SPEND.MULTI_TIER_NOTE
            : METERING.USAGE_SPEND.TIER_BREAKDOWN_NOTE}
        </Text>
      </Box>
    </VStack>
  );
};

interface InstitutionUsageDetailPanelProps {
  detail: TenantUsageItem;
  periodTitle: string;
  organisationLabel?: string | null;
  isLoading?: boolean;
}

const InstitutionUsageDetailPanel: React.FC<InstitutionUsageDetailPanelProps> = ({
  detail,
  periodTitle,
  organisationLabel,
  isLoading = false,
}) => {
  const displayName = organisationLabel?.trim() || detail.tenantName;

  return (
    <VStack align="stretch" spacing={5}>
      <Text fontSize={{ base: "xl", md: "2xl" }} fontWeight="bold" color="gray.800">
        {METERING.USAGE_SPEND.TENANT_DETAIL_TITLE}
      </Text>

      <HStack spacing="14px" align="center">
        <TenantAvatar name={displayName} size="md" />
        <Text fontSize="16px" fontWeight="semibold" color="gray.800">
          {displayName}
        </Text>
        <TierBadge label={detail.tier} />
      </HStack>

      <InstitutionUsageDetailContent
        detail={detail}
        periodTitle={periodTitle}
        isLoading={isLoading}
      />
    </VStack>
  );
};

export default InstitutionUsageDetailPanel;
