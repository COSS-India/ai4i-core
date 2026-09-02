import { Box, Center, Flex, HStack, Spinner, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { INSTITUTION } from "../../config/constants";
import { METERING } from "../../config/meteringConstants";
import { formatBudgetEffectiveRange } from "../../utils/usageSpendHelpers";
import type { TenantUsageItem } from "../../types/usageSpend";
import BillingMonthSelect from "./BillingMonthSelect";
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
  isLoading?: boolean;
  billingPeriod?: string;
  onBillingPeriodChange?: (value: string) => void;
}

export const InstitutionUsageDetailContent: React.FC<InstitutionUsageDetailContentProps> = ({
  detail,
  isLoading = false,
  billingPeriod,
  onBillingPeriodChange,
}) => {
  const effectiveRange = formatBudgetEffectiveRange(
    detail.budget.budgetEffectiveFrom,
    detail.budget.budgetEffectiveTo,
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
            <Spinner color="blue.500" size="sm" />
          </Center>
        ) : (
          <BudgetCell
            limit={detail.budget.limit}
            spent={detail.budget.spent}
            remaining={detail.budget.remaining}
            percentageUsed={detail.budget.percentageUsed}
            currency={detail.currency}
          />
        )}
        <Text fontSize="11.5px" color="gray.500" mt={3}>
          {METERING.USAGE_SPEND.BUDGET_ALL_TIME_NOTE}
        </Text>
      </Box>

      <Box {...cardSx} opacity={isLoading ? 0.6 : 1}>
        <Flex justify="space-between" align="center" gap={3} mb={4} flexWrap="wrap">
          <Text {...sectionLabelSx}>{METERING.USAGE_SPEND.USAGE_BY_TASK_TYPE_ALL_TIME}</Text>
          {billingPeriod && onBillingPeriodChange ? (
            <BillingMonthSelect value={billingPeriod} onChange={onBillingPeriodChange} />
          ) : null}
        </Flex>
        <SpendByTaskTypeTable
          tierBreakdown={detail.tierBreakdown ?? []}
          usageColumnLabel={METERING.USAGE_SPEND.USAGE_VS_QUOTA_ALL_TIME}
        />
        {hasMultiTier ? (
          <Text fontSize="11.5px" color="gray.500" lineHeight="1.5" mt={3}>
            Grouped by tier since this {INSTITUTION.toLowerCase()} changed tier — cumulative
            all-time usage per task type.
          </Text>
        ) : (
          <Text fontSize="11.5px" color="gray.500" lineHeight="1.5" mt={3}>
            {METERING.USAGE_SPEND.TIER_BREAKDOWN_ALL_TIME_NOTE}
          </Text>
        )}
      </Box>
    </VStack>
  );
};

interface InstitutionUsageDetailPanelProps {
  detail: TenantUsageItem;
  organisationLabel?: string | null;
  isLoading?: boolean;
  billingPeriod?: string;
  onBillingPeriodChange?: (value: string) => void;
}

const InstitutionUsageDetailPanel: React.FC<InstitutionUsageDetailPanelProps> = ({
  detail,
  organisationLabel,
  isLoading = false,
  billingPeriod,
  onBillingPeriodChange,
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
        isLoading={isLoading}
        billingPeriod={billingPeriod}
        onBillingPeriodChange={onBillingPeriodChange}
      />
    </VStack>
  );
};

export default InstitutionUsageDetailPanel;
