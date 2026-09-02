import { Box, Center, Flex, HStack, Spinner, Text, VStack } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import { INSTITUTIONS } from "../../config/constants";
import {
  aggregateTasks,
  formatSpendMoney,
  hasPopulatedQuotaUsage,
  isMultiTaskQuotaTenant,
  taskTypeColor,
  USAGE_SPEND_ACCENT,
  USAGE_SPEND_DANGER,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageItem, UsageSummaryResponse } from "../../types/usageSpend";
import InfoTip from "../common/InfoTip";
import { TaskTypeLabel, UsageCell } from "./UsageSpendCells";

const SPEND_CARD_BG = "#eef3fb";

function moneyOrDash(value: number | null | undefined, currency: string): string {
  return value == null ? "—" : formatSpendMoney(value, currency);
}

function SpendTotalCard({
  label,
  money,
  tooltip,
}: Readonly<{ label: string; money: string; tooltip?: string }>) {
  return (
    <Box
      bg={SPEND_CARD_BG}
      borderRadius="12px"
      borderWidth="1px"
      borderColor="gray.200"
      p="18px 20px"
      flex="1"
      minW={0}
    >
      <HStack spacing={1.5} mb={2} align="center">
        <Text
          fontSize="11px"
          fontWeight="semibold"
          letterSpacing="0.04em"
          color={USAGE_SPEND_ACCENT}
        >
          {label}
        </Text>
        {tooltip ? <InfoTip message={tooltip} /> : null}
      </HStack>
      <Text fontSize="22px" fontWeight="bold" lineHeight="1.1" color="gray.800" noOfLines={1}>
        {money}
      </Text>
    </Box>
  );
}

interface SpendOverviewPanelProps {
  summary?: UsageSummaryResponse;
  isLoading: boolean;
  error: string | null;
  currency: string;
  emptyStateMessage?: string;
  tenantDetail?: TenantUsageItem | null;
  showProgramMetrics?: boolean;
}

const cardFlex = {
  flex: { base: "none", md: "0 0 280px" },
  minW: { base: "full", md: "280px" },
} as const;

function TenantBudgetCard({
  detail,
  currency,
  isLoading,
}: {
  detail: TenantUsageItem;
  currency: string;
  isLoading: boolean;
}) {
  const { limit, spent, remaining, percentageUsed } = detail.budget;
  const cur = detail.currency || currency;
  const pct = percentageUsed || (limit > 0 ? (spent / limit) * 100 : 0);
  const over = spent - limit;

  return (
    <Box bg={SPEND_CARD_BG} borderRadius="12px" borderWidth="1px" borderColor="gray.200" p="22px 24px">
      {isLoading ? (
        <Center minH="120px"><Spinner color="blue.500" /></Center>
      ) : (
        <>
          <Text
            fontSize="11px"
            fontWeight="semibold"
            letterSpacing="0.04em"
            color={USAGE_SPEND_ACCENT}
            mb={2}
          >
            {METERING.USAGE_SPEND.BUDGET_SUMMARY}
          </Text>
          <Text fontSize="28px" fontWeight="bold" lineHeight="1" color="gray.800">
            {formatSpendMoney(spent, cur)}
          </Text>
          <Text fontSize="12.5px" color="gray.500" mt={1} mb={3}>
            of {formatSpendMoney(limit, cur)} · {pct.toFixed(0)}% used
          </Text>
          <Box h="6px" borderRadius="3px" bg="blackAlpha.100" overflow="hidden">
            <Box
              h="100%"
              w={`${Math.min(Math.max(pct, 0), 100)}%`}
              bg={over > 0 ? USAGE_SPEND_DANGER : USAGE_SPEND_ACCENT}
              borderRadius="3px"
            />
          </Box>
          <Text
            fontSize="12px"
            mt={2}
            fontWeight="semibold"
            color={over > 0 ? USAGE_SPEND_DANGER : "gray.600"}
          >
            {over > 0
              ? `${formatSpendMoney(over, cur)} over budget`
              : `${formatSpendMoney(remaining, cur)} remaining`}
          </Text>
          <Text fontSize="11.5px" color="gray.500" mt={2}>
            {METERING.USAGE_SPEND.BUDGET_ALL_TIME_NOTE}
          </Text>
        </>
      )}
    </Box>
  );
}

function TenantQuotaSummary({ detail }: Readonly<{ detail: TenantUsageItem }>) {
  const tasks = useMemo(
    () => aggregateTasks(detail.tierBreakdown ?? []).sort((a, b) => b.consumed - a.consumed),
    [detail.tierBreakdown],
  );

  if (tasks.length === 0) {
    return (
      <Text fontSize="sm" color="gray.400">
        No quota data for this period.
      </Text>
    );
  }

  if (!isMultiTaskQuotaTenant(detail.usage) && hasPopulatedQuotaUsage(detail.usage)) {
    const u = detail.usage;
    return (
      <UsageCell
        consumed={u.consumed ?? 0}
        quotaLimit={u.quotaLimit}
        remaining={u.remaining}
        percentage={u.percentage}
        unit={u.unit ?? tasks[0]?.unit ?? ""}
      />
    );
  }

  if (!isMultiTaskQuotaTenant(detail.usage) && tasks.length === 1) {
    const t = tasks[0];
    if (!t) return null;
    return (
      <UsageCell
        consumed={t.consumed}
        quotaLimit={t.quotaLimit}
        remaining={t.remaining}
        unit={t.unit}
      />
    );
  }

  return (
    <VStack align="stretch" spacing="14px" maxH="240px" overflowY="auto" pr={1}>
      {tasks.map((t, i) => (
        <Box key={t.taskType}>
          <TaskTypeLabel
            taskType={t.taskType}
            color={taskTypeColor(t.taskType, i)}
            fontSize="12px"
            fontWeight="semibold"
          />
          <Box mt="7px">
            <UsageCell
              consumed={t.consumed}
              quotaLimit={t.quotaLimit}
              remaining={t.remaining}
              unit={t.unit}
            />
          </Box>
        </Box>
      ))}
    </VStack>
  );
}

const SpendOverviewPanel: React.FC<SpendOverviewPanelProps> = ({
  summary,
  isLoading,
  error,
  currency,
  tenantDetail = null,
  showProgramMetrics = true,
}) => {
  const totalCards = useMemo(() => {
    const tips = METERING.USAGE_SPEND.TOOLTIPS;
    return [
      {
        label: METERING.USAGE_SPEND.TOTAL_ALLOCATED,
        money: moneyOrDash(summary?.totalAllocatedBudget, currency),
        tooltip: tips.TOTAL_ALLOCATED,
      },
      {
        label: METERING.USAGE_SPEND.TOTAL_USED,
        money: moneyOrDash(summary?.totalSpend, currency),
        tooltip: tips.TOTAL_USED,
      },
      {
        label: METERING.USAGE_SPEND.TOTAL_REMAINING,
        money: moneyOrDash(summary?.totalRemainingBudget, currency),
        tooltip: tips.TOTAL_REMAINING,
      },
    ];
  }, [summary, currency]);

  if (error) {
    return <Text fontSize="sm" color="red.500">{error}</Text>;
  }

  if (tenantDetail) {
    return (
      <Flex gap={4} direction={{ base: "column", md: "row" }} align="stretch">
        <VStack align="stretch" spacing={4} {...cardFlex}>
          <TenantBudgetCard detail={tenantDetail} currency={currency} isLoading={isLoading} />
          <Box bg="white" borderRadius="12px" borderWidth="1px" borderColor="gray.200" p="22px 24px">
            {isLoading ? (
              <Center minH="100px"><Spinner color="blue.500" /></Center>
            ) : (
              <>
                <Text fontSize="11px" fontWeight="semibold" letterSpacing="0.04em" color="gray.600" mb={3}>
                  {METERING.USAGE_SPEND.QUOTA_SUMMARY}
                </Text>
                <TenantQuotaSummary detail={tenantDetail} />
              </>
            )}
          </Box>
        </VStack>
      </Flex>
    );
  }

  if (isLoading) {
    return (
      <Center minH="140px" w="full">
        <Spinner color="blue.500" />
      </Center>
    );
  }

  return (
    <VStack align="stretch" spacing={4} w="full">
      <Flex gap={4} direction={{ base: "column", sm: "row" }}>
        {totalCards.map((card) => (
          <SpendTotalCard
            key={card.label}
            label={card.label}
            money={card.money}
            tooltip={card.tooltip}
          />
        ))}
      </Flex>
      {showProgramMetrics ? (
        <Box bg={SPEND_CARD_BG} borderRadius="12px" borderWidth="1px" borderColor="gray.200" p="14px 20px">
          <Flex
            direction={{ base: "column", sm: "row" }}
            gap={{ base: "9px", sm: 6 }}
            justify="space-between"
            fontSize="12.5px"
            flexWrap="wrap"
          >
            <HStack spacing={1.5}>
              <Text color="gray.500">Active {INSTITUTIONS.toLowerCase()}:</Text>
              <InfoTip message={METERING.USAGE_SPEND.TOOLTIPS.ACTIVE_TENANTS} />
              <Text fontWeight="semibold" color="gray.800">{summary?.activeTenants ?? "—"}</Text>
            </HStack>
            <HStack spacing={1.5}>
              <Text color="gray.500">Budget exceeded:</Text>
              <Text fontWeight="semibold" color="gray.800">
                {summary?.budgetExceededTenants ?? "—"}
              </Text>
            </HStack>
          </Flex>
        </Box>
      ) : null}
    </VStack>
  );
};

export default SpendOverviewPanel;
