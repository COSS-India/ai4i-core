import { Box, Center, Flex, HStack, Spinner, Text, VStack } from "@chakra-ui/react";
import React, { useMemo, useState } from "react";
import { Cell, Pie, PieChart } from "recharts";
import { METERING } from "../../config/meteringConstants";
import {
  aggregateTasks,
  formatSpendMoney,
  formatSpendUnit,
  taskTypeColor,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageItem, UsageSummaryResponse } from "../../types/usageSpend";
import MeteringChartPanel from "./MeteringChartPanel";
import { TaskTypeLabel, UsageCell } from "./UsageSpendCells";

function spendChangeColor(spendChangePercent: number | null): string | undefined {
  if (spendChangePercent == null) return undefined;
  if (spendChangePercent > 0) return "#a8f0c6";
  if (spendChangePercent < 0) return "#ffb3ac";
  return undefined;
}

function spendChangeArrow(spendChangePercent: number): string {
  if (spendChangePercent > 0) return "↑";
  if (spendChangePercent < 0) return "↓";
  return "→";
}

function budgetExceededLabel(count: number | null | undefined): string {
  if (count == null) return "—";
  return `${count} tenant${count === 1 ? "" : "s"}`;
}

interface SpendOverviewPanelProps {
  summary?: UsageSummaryResponse;
  isLoading: boolean;
  error: string | null;
  currency: string;
  spendChangePercent: number | null;
  emptyStateMessage?: string;
  /** When set, show tenant Budget / Quota summary cards instead of platform totals. */
  tenantDetail?: TenantUsageItem | null;
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
    <Box bgGradient="linear(135deg, #184a9e, #2a67d6)" borderRadius="12px" p="22px 24px" color="white">
      {isLoading ? (
        <Center minH="120px"><Spinner color="whiteAlpha.700" /></Center>
      ) : (
        <>
          <Text fontSize="11px" fontWeight="semibold" letterSpacing="0.04em" opacity={0.85} mb={2}>
            {METERING.USAGE_SPEND.BUDGET_SUMMARY}
          </Text>
          <Text fontSize="28px" fontWeight="bold" lineHeight="1">
            {formatSpendMoney(spent, cur)}
          </Text>
          <Text fontSize="12.5px" opacity={0.8} mt={1} mb={3}>
            of {formatSpendMoney(limit, cur)} · {pct.toFixed(0)}% used
          </Text>
          <Box h="6px" borderRadius="3px" bg="whiteAlpha.300" overflow="hidden">
            <Box
              h="100%"
              w={`${Math.min(Math.max(pct, 0), 100)}%`}
              bg={over > 0 ? "#ffd7a8" : "white"}
              borderRadius="3px"
            />
          </Box>
          <Text fontSize="12px" mt={2} opacity={0.9} fontWeight="semibold">
            {over > 0
              ? `${formatSpendMoney(over, cur)} over budget`
              : `${formatSpendMoney(remaining, cur)} remaining`}
          </Text>
        </>
      )}
    </Box>
  );
}

/**
 * Quota Summary body for a single tenant. The API leaves the flat `usage` aggregate
 * unpopulated (consumed/quotaLimit null) when a tenant spans multiple task types, since
 * quotas can't be summed across heterogeneous units (characters vs. images vs. minutes).
 * So we render a per-task-type quota list from the same tierBreakdown the Spend section
 * uses, and fall back to a single bar only when there's exactly one task type.
 */
function TenantQuotaSummary({ detail }: { detail: TenantUsageItem }) {
  const tasks = useMemo(
    () => aggregateTasks(detail.tierBreakdown ?? []).sort((a, b) => b.spend - a.spend),
    [detail],
  );

  if (tasks.length === 0) {
    return (
      <Text fontSize="sm" color="gray.400">
        No quota data for this period.
      </Text>
    );
  }

  if (tasks.length === 1) {
    const t = tasks[0];
    return (
      <UsageCell
        consumed={t.consumed}
        quotaLimit={t.quotaLimit}
        remaining={t.remaining}
        percentage={0}
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
              percentage={0}
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
  spendChangePercent,
  emptyStateMessage = "No spend data for this period.",
  tenantDetail = null,
}) => {
  const [hlKey, setHlKey] = useState<string | null>(null);
  const sorted = useMemo(
    () => [...(summary?.spendByModelTaskType ?? [])].sort((a, b) => b.spend - a.spend),
    [summary?.spendByModelTaskType],
  );
  const donutData = sorted.map((item, i) => ({
    name: item.modelTaskType,
    value: item.spend,
    color: taskTypeColor(item.modelTaskType, i),
  }));

  const leftPanel = tenantDetail ? (
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
  ) : (
    <Box
      bgGradient="linear(135deg, #184a9e, #2a67d6)"
      borderRadius="12px"
      p="22px 24px"
      color="white"
      {...cardFlex}
    >
      {isLoading ? (
        <Center minH="140px"><Spinner color="whiteAlpha.700" /></Center>
      ) : (
        <>
          <Text fontSize="11px" fontWeight="semibold" letterSpacing="0.04em" opacity={0.85} mb={2}>
            TOTAL SPEND
          </Text>
          <Text fontSize="28px" fontWeight="bold" lineHeight="1">
            {summary ? formatSpendMoney(summary.totalSpend, currency) : "—"}
          </Text>
          <Box mt="18px" pt="14px" borderTopWidth="1px" borderColor="whiteAlpha.300">
            <VStack align="stretch" spacing="9px">
              <Flex justify="space-between" fontSize="12.5px">
                <Text opacity={0.8}>Active tenants</Text>
                <Text fontWeight="semibold">{summary?.activeTenants ?? "—"}</Text>
              </Flex>
              <Flex justify="space-between" fontSize="12.5px">
                <Text opacity={0.8}>Budget exceeded</Text>
                <Text
                  fontWeight="semibold"
                  color={(summary?.budgetExceededTenants ?? 0) > 0 ? "#ffd7a8" : undefined}
                >
                  {budgetExceededLabel(summary?.budgetExceededTenants)}
                </Text>
              </Flex>
              <Flex justify="space-between" fontSize="12.5px">
                <Text opacity={0.8}>vs last month</Text>
                <Text fontWeight="semibold" color={spendChangeColor(spendChangePercent)}>
                  {spendChangePercent == null
                    ? "—"
                    : `${spendChangeArrow(spendChangePercent)} ${Math.abs(spendChangePercent).toFixed(1)}%`}
                </Text>
              </Flex>
            </VStack>
          </Box>
        </>
      )}
    </Box>
  );

  let spendBody: React.ReactNode;
  if (isLoading) {
    spendBody = <Center h="150px"><Spinner color="blue.500" /></Center>;
  } else if (error) {
    spendBody = <Text fontSize="sm" color="red.500">{error}</Text>;
  } else if (sorted.length === 0) {
    spendBody = (
      <Text fontSize="sm" color="gray.400" py={8} textAlign="center">
        {emptyStateMessage}
      </Text>
    );
  } else {
    spendBody = (
      <Flex align="flex-start" gap={7} direction={{ base: "column", sm: "row" }}>
        <Box position="relative" flexShrink={0} w="150px" h="150px" mt={{ base: 0, sm: "34px" }}>
          <MeteringChartPanel height={150} minWidth={150}>
            {(size) => (
              <PieChart width={size.width} height={size.height}>
                <Pie
                  data={donutData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={48}
                  outerRadius={68}
                  paddingAngle={1}
                  stroke="none"
                  onMouseEnter={(_, i) => setHlKey(donutData[i]?.name ?? null)}
                  onMouseLeave={() => setHlKey(null)}
                >
                  {donutData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={entry.color}
                      opacity={hlKey && hlKey !== entry.name ? 0.45 : 1}
                      cursor="pointer"
                    />
                  ))}
                </Pie>
              </PieChart>
            )}
          </MeteringChartPanel>
          <Center position="absolute" inset={0} pointerEvents="none" textAlign="center" px="22px">
            <Text fontSize="11px" fontWeight="bold" letterSpacing="0.04em" color="gray.600" lineHeight="1.3">
              All Services
            </Text>
          </Center>
        </Box>
        <Box flex={1} minW={0} maxH="272px" overflowY="auto" pr={2}>
          {sorted.map((item, i) => {
            const color = taskTypeColor(item.modelTaskType, i);
            const isHl = hlKey === item.modelTaskType;
            return (
              <Flex
                key={item.modelTaskType}
                align="center"
                justify="space-between"
                gap={3}
                px={2}
                py={2}
                borderRadius="6px"
                borderBottomWidth="1px"
                borderColor="gray.50"
                bg={isHl ? "gray.50" : "transparent"}
                onMouseEnter={() => setHlKey(item.modelTaskType)}
                onMouseLeave={() => setHlKey(null)}
              >
                <HStack spacing="9px" minW={0}>
                  <TaskTypeLabel taskType={item.modelTaskType} color={color} fontWeight="semibold" />
                  <Text fontSize="12px" color="gray.500" noOfLines={1}>
                    {formatSpendUnit(item.consumption, item.unit)}
                  </Text>
                </HStack>
                <Box textAlign="right" flexShrink={0}>
                  <Text fontSize="13px" fontWeight="semibold" display="block">
                    {formatSpendMoney(item.spend, currency)}
                  </Text>
                  <Text fontSize="11.5px" color="gray.500">{item.percentage.toFixed(1)}%</Text>
                </Box>
              </Flex>
            );
          })}
        </Box>
      </Flex>
    );
  }

  return (
    <Flex gap={4} direction={{ base: "column", md: "row" }} align="stretch">
      {leftPanel}
      <Box flex={1} bg="white" borderRadius="12px" borderWidth="1px" borderColor="gray.200" p="20px 24px">
        <Text fontSize="12px" letterSpacing="0.04em" color="gray.600" fontWeight="semibold" mb={4}>
          {METERING.USAGE_SPEND.SPEND_BY_TASK_TYPE}
        </Text>
        {spendBody}
      </Box>
    </Flex>
  );
};

export default SpendOverviewPanel;
