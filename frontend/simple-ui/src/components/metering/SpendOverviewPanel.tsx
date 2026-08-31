import { Box, Center, Flex, HStack, Spinner, Text, VStack } from "@chakra-ui/react";
import React, { useMemo, useState } from "react";
import { Cell, Pie, PieChart } from "recharts";
import { METERING } from "../../config/meteringConstants";
import { INSTITUTION, INSTITUTIONS } from "../../config/constants";
import {
  aggregateTasks,
  formatSpendMoney,
  formatSpendUnit,
  hasPopulatedQuotaUsage,
  isMultiTaskQuotaTenant,
  summarizeSpendTokens,
  taskTypeColor,
  USAGE_SPEND_ACCENT,
  USAGE_SPEND_DANGER,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageItem, UsageSummaryResponse } from "../../types/usageSpend";
import MeteringChartPanel from "./MeteringChartPanel";
import InfoTip from "../common/InfoTip";
import { TaskTypeLabel, UsageCell } from "./UsageSpendCells";

const SPEND_CARD_BG = "#eef3fb";

function spendChangeColor(spendChangePercent: number | null): string | undefined {
  if (spendChangePercent == null) return undefined;
  if (spendChangePercent > 0) return "#c0392b";
  if (spendChangePercent < 0) return "#2f9e44";
  return undefined;
}

function spendChangeArrow(spendChangePercent: number): string {
  if (spendChangePercent > 0) return "↑";
  if (spendChangePercent < 0) return "↓";
  return "→";
}

function budgetExceededLabel(count: number | null | undefined): string {
  if (count == null) return "—";
  return `${count} ${count === 1 ? INSTITUTION.toLowerCase() : INSTITUTIONS.toLowerCase()}`;
}

function moneyOrDash(value: number | null | undefined, currency: string): string {
  return value == null ? "—" : formatSpendMoney(value, currency);
}

function tokensOrDash(value: number | null | undefined, unit: string): string {
  return value == null ? "—" : formatSpendUnit(value, unit);
}

function SpendTotalCard({
  label,
  money,
  tokens,
  tooltip,
}: Readonly<{ label: string; money: string; tokens: string; tooltip?: string }>) {
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
      <Text fontSize="12.5px" color="gray.500" mt="6px" noOfLines={1}>
        {tokens}
      </Text>
    </Box>
  );
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
  /** Program-wide summary strip (Active institutions, Budget exceeded, vs last month). Hidden for Institution Admin / scoped views. */
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
        </>
      )}
    </Box>
  );
}

/**
 * Quota Summary for a single tenant.
 *
 * - One task type: show the API's flat `usage` quota bar (homogeneous unit + limit).
 * - Multiple task types: list each type from `tierBreakdown` — no cross-unit summary.
 *   The flat `usage` block is intentionally null in that case (can't sum characters +
 *   images + minutes into one consumed/quotaLimit).
 */
function TenantQuotaSummary({ detail }: Readonly<{ detail: TenantUsageItem }>) {
  const tasks = useMemo(
    () => aggregateTasks(detail.tierBreakdown ?? []).sort((a, b) => b.spend - a.spend),
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
  spendChangePercent,
  emptyStateMessage = "No spend data for this period.",
  tenantDetail = null,
  showProgramMetrics = true,
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

  const totalCards = useMemo(() => {
    const rows = summary?.spendByModelTaskType ?? [];
    const tokens = summarizeSpendTokens(rows);
    const tips = METERING.USAGE_SPEND.TOOLTIPS;
    return [
      {
        label: METERING.USAGE_SPEND.TOTAL_ALLOCATED,
        money: moneyOrDash(summary?.totalAllocatedBudget, currency),
        tokens: tokensOrDash(tokens.tokensAllocated, tokens.unit),
        tooltip: tips.TOTAL_ALLOCATED,
      },
      {
        label: METERING.USAGE_SPEND.TOTAL_USED,
        money: moneyOrDash(summary?.totalSpend, currency),
        tokens: tokensOrDash(tokens.tokensUsed, tokens.unit),
        tooltip: tips.TOTAL_USED,
      },
      {
        label: METERING.USAGE_SPEND.TOTAL_REMAINING,
        money: moneyOrDash(summary?.totalRemainingBudget, currency),
        tokens: tokensOrDash(tokens.tokensRemaining, tokens.unit),
        tooltip: tips.TOTAL_REMAINING,
      },
    ];
  }, [summary, currency]);

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
  ) : isLoading ? (
    <Center minH="140px" w="full">
      <Spinner color="blue.500" />
    </Center>
  ) : (
    <VStack align="stretch" spacing={4} w="full">
      <Flex gap={4} direction={{ base: "column", sm: "row" }}>
        {totalCards.map((card) => (
          <SpendTotalCard
            key={card.label}
            label={card.label}
            money={card.money}
            tokens={card.tokens}
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
              <InfoTip message={METERING.USAGE_SPEND.TOOLTIPS.BUDGET_EXCEEDED} />
              <Text
                fontWeight="semibold"
                color={(summary?.budgetExceededTenants ?? 0) > 0 ? USAGE_SPEND_DANGER : "gray.800"}
              >
                {budgetExceededLabel(summary?.budgetExceededTenants)}
              </Text>
            </HStack>
            <HStack spacing={1.5}>
              <Text color="gray.500">vs last month:</Text>
              <InfoTip message={METERING.USAGE_SPEND.TOOLTIPS.VS_LAST_MONTH} />
              <Text fontWeight="semibold" color={spendChangeColor(spendChangePercent) ?? "gray.800"}>
                {spendChangePercent == null
                  ? "—"
                  : `${spendChangeArrow(spendChangePercent)} ${Math.abs(spendChangePercent).toFixed(1)}%`}
              </Text>
            </HStack>
          </Flex>
        </Box>
      ) : null}
    </VStack>
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
      {/* SPEND BY MODEL TASK TYPE removed from adopter Usage & Spend.
          UNDO — restore the panel below (and keep spendBody / donut logic above).
      <Box flex={1} bg="white" borderRadius="12px" borderWidth="1px" borderColor="gray.200" p="20px 24px">
        <Text fontSize="12px" letterSpacing="0.04em" color="gray.600" fontWeight="semibold" mb={4}>
          {METERING.USAGE_SPEND.SPEND_BY_TASK_TYPE}
        </Text>
        {spendBody}
      </Box>
      */}
      {/* Keep spendBody referenced so the unused-code path stays easy to restore. */}
      {false ? spendBody : null}
    </Flex>
  );
};

export default SpendOverviewPanel;
