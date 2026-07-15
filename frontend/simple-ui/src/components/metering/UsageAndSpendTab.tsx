import React, { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Box,
  Center,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerHeader,
  DrawerOverlay,
  Flex,
  FormControl,
  HStack,
  IconButton,
  Select,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
  useDisclosure,
} from "@chakra-ui/react";
import { ChevronDownIcon, ChevronRightIcon } from "@chakra-ui/icons";
import { Cell, Pie, PieChart } from "recharts";
import {
  fetchUsageSummary,
  fetchTenantUsageList,
  fetchTenantUsageById,
} from "../../services/usageSpendService";
import { fetchTiers } from "../../services/tierManagementService";
import { parseError } from "../../utils/errorHandler";
import { formatModelTaskTypeLabel } from "../../config/constants";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import { meteringColorAt } from "../../utils/meteringColors";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringChartPanel from "./MeteringChartPanel";
import type {
  SpendByTaskType,
  TenantTierBreakdown,
  TenantUsageDetail,
  TenantUsageItem,
  UsageSummaryResponse,
} from "../../types/usageSpend";

interface UsageAndSpendTabProps {
  readonly scopeTenantId?: string | null;
  readonly isTenantView?: boolean;
  readonly tenantId?: string | null;
  readonly refreshNonce?: number;
}

const STALE_MS = 60_000;
const ACCENT = "#2a67d6";
const DANGER = "#c0392b";
const WARNING = "#b8720a";

const AVATAR_COLORS = [
  "#d6336c",
  "#2f9e44",
  "#f08c00",
  "#1971c2",
  "#7048e8",
  "#e8590c",
  "#0ca678",
  "#74b816",
];

function billingPeriodValue(key: "current" | "last"): string {
  const d = new Date();
  if (key === "last") d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function billingPeriodLabel(key: "current" | "last"): string {
  return key === "current" ? "CURRENT MONTH" : "LAST MONTH";
}

const formatMoney = (n: number, currency = "INR") => {
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(n);
  } catch {
    return `₹${Math.round(n).toLocaleString("en-IN")}`;
  }
};

const formatUnit = (n: number, unit: string) => {
  const u = (unit || "").toLowerCase();
  if (u === "tokens" || u === "characters") {
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M ${unit}`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K ${unit}`;
    return `${Math.round(n)} ${unit}`;
  }
  if (u === "minutes") return `${Math.round(n).toLocaleString("en-IN")} min`;
  return `${Math.round(n).toLocaleString("en-IN")} ${unit || ""}`.trim();
};

const barColor = (pct: number) => {
  if (pct > 100) return DANGER;
  if (pct >= 90) return WARNING;
  return ACCENT;
};

const tenantInitials = (name: string) => {
  const words = name
    .trim()
    .split(/\s+/)
    .filter((w) => w.length > 2 || /[A-Z]/.test(w[0] ?? ""));
  const letters = words.map((w) => w[0]).join("");
  return (letters || name).slice(0, 2).toUpperCase();
};

const tenantAvatarBg = (name: string) => {
  let sum = 0;
  for (let i = 0; i < name.length; i++) sum += name.codePointAt(i) ?? 0;
  return AVATAR_COLORS[sum % AVATAR_COLORS.length];
};

const taskTypeColor = (taskType: string, index: number) =>
  meteringColorAt(index) || AVATAR_COLORS[index % AVATAR_COLORS.length];

/** Flat task list aggregated across tiers (quota from last tier write). */
function aggregateTasks(breakdown: TenantTierBreakdown[]) {
  const map = new Map<
    string,
    { taskType: string; unit: string; quotaLimit: number; consumed: number; remaining: number; spend: number }
  >();
  const order: string[] = [];
  for (const tier of breakdown) {
    for (const t of tier.taskTypes ?? []) {
      const existing = map.get(t.taskType);
      if (!existing) {
        map.set(t.taskType, {
          taskType: t.taskType,
          unit: t.unit,
          quotaLimit: t.quotaLimit,
          consumed: t.consumed,
          remaining: t.remaining,
          spend: t.spend,
        });
        order.push(t.taskType);
      } else {
        existing.consumed += t.consumed;
        existing.spend += t.spend;
        existing.quotaLimit = t.quotaLimit;
        existing.remaining = t.remaining;
        existing.unit = t.unit || existing.unit;
      }
    }
  }
  return order.map((k) => map.get(k)!);
}

function summaryFromDetail(detail: TenantUsageDetail): UsageSummaryResponse {
  const items = aggregateTasks(detail.tierBreakdown ?? []).map((i) => ({
    modelTaskType: i.taskType,
    unit: i.unit,
    consumption: i.consumed,
    spend: i.spend,
    percentage: 0,
  }));
  const total = items.reduce((s, i) => s + i.spend, 0) || detail.spend;
  return {
    billingPeriod: "",
    totalSpend: total,
    currency: detail.currency,
    activeTenants: 1,
    budgetExceededTenants: detail.budget.remaining < 0 || detail.budget.percentageUsed > 100 ? 1 : 0,
    spendChangePercent: 0,
    spendByModelTaskType: items.map((i) => ({
      ...i,
      percentage: total > 0 ? Number(((i.spend / total) * 100).toFixed(1)) : 0,
    })),
  };
}

function RatioBar({
  pct,
  main,
  of,
  caption,
  captionTone,
}: {
  pct: number;
  main: string;
  of: string;
  caption: string;
  captionTone?: "over" | "warn" | "muted";
}) {
  const fillPct = Math.min(Math.max(pct, 0), 100);
  const captionColor =
    captionTone === "over" ? DANGER : captionTone === "warn" ? WARNING : "gray.500";
  return (
    <Box minW="170px">
      <Flex justify="space-between" fontSize="12.5px" mb="6px">
        <Text fontWeight="semibold">{main}</Text>
        <Text color="gray.500" fontWeight="normal">
          {of}
        </Text>
      </Flex>
      <Box
        h="6px"
        borderRadius="3px"
        bg="gray.100"
        borderWidth="1px"
        borderColor="gray.200"
        overflow="hidden"
      >
        <Box h="100%" w={`${fillPct}%`} bg={barColor(pct)} borderRadius="3px" />
      </Box>
      <Text
        fontSize="11.5px"
        mt="5px"
        color={captionColor}
        fontWeight={captionTone === "over" || captionTone === "warn" ? "semibold" : "normal"}
      >
        {caption}
      </Text>
    </Box>
  );
}

function BudgetCell({
  limit,
  spent,
  remaining,
  percentageUsed,
  currency,
}: {
  limit: number;
  spent: number;
  remaining: number;
  percentageUsed: number;
  currency: string;
}) {
  const pct = percentageUsed || (limit > 0 ? (spent / limit) * 100 : 0);
  const over = spent - limit;
  let caption: string;
  let tone: "over" | "warn" | "muted" = "muted";
  if (over > 0) {
    caption = `${formatMoney(over, currency)} over budget`;
    tone = "over";
  } else if (pct >= 90) {
    caption = `${formatMoney(remaining, currency)} left · ${pct.toFixed(0)}% used`;
    tone = "warn";
  } else {
    caption = `${formatMoney(remaining, currency)} left`;
  }
  return (
    <RatioBar
      pct={pct}
      main={`${pct.toFixed(0)}% used`}
      of={`of ${formatMoney(limit, currency)}`}
      caption={caption}
      captionTone={tone}
    />
  );
}

function UsageCell({
  consumed,
  quotaLimit,
  remaining,
  percentage,
  unit,
}: {
  consumed: number;
  quotaLimit: number;
  remaining: number;
  percentage: number;
  unit: string;
}) {
  const pct = percentage || (quotaLimit > 0 ? (consumed / quotaLimit) * 100 : 0);
  return (
    <RatioBar
      pct={pct}
      main={formatUnit(consumed, unit)}
      of={`of ${formatUnit(quotaLimit, unit)}`}
      caption={`${formatUnit(Math.max(remaining, 0), unit)} left · ${pct.toFixed(0)}%`}
    />
  );
}

function SpendOverviewPanel({
  summary,
  isLoading,
  error,
  currency,
  spendChangePercent,
}: {
  summary?: UsageSummaryResponse;
  isLoading: boolean;
  error: string | null;
  currency: string;
  /** Resolved MoM change; null means loading/unavailable (show em dash). */
  spendChangePercent: number | null;
}) {
  const [hlKey, setHlKey] = useState<string | null>(null);
  const items = summary?.spendByModelTaskType ?? [];
  const sorted = useMemo(
    () => [...items].sort((a, b) => b.spend - a.spend),
    [items],
  );
  const total = summary?.totalSpend ?? 0;
  const donutData = sorted.map((item, i) => ({
    name: item.modelTaskType,
    value: item.spend,
    color: taskTypeColor(item.modelTaskType, i),
  }));

  return (
    <Flex gap={4} direction={{ base: "column", md: "row" }} align="stretch">
      <Box
        bgGradient="linear(135deg, #184a9e, #2a67d6)"
        borderRadius="12px"
        p="22px 24px"
        color="white"
        flex={{ base: "none", md: "0 0 280px" }}
        minW={{ base: "full", md: "280px" }}
      >
        {isLoading ? (
          <Center minH="140px">
            <Spinner color="whiteAlpha.700" />
          </Center>
        ) : (
          <>
            <Text fontSize="11px" fontWeight="semibold" letterSpacing="0.04em" opacity={0.85} mb={2}>
              TOTAL SPEND
            </Text>
            <Text fontSize="28px" fontWeight="bold" lineHeight="1">
              {summary ? formatMoney(summary.totalSpend, currency) : "—"}
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
                    {summary?.budgetExceededTenants != null
                      ? `${summary.budgetExceededTenants} tenant${summary.budgetExceededTenants === 1 ? "" : "s"}`
                      : "—"}
                  </Text>
                </Flex>
                <Flex justify="space-between" fontSize="12.5px">
                  <Text opacity={0.8}>vs last month</Text>
                  <Text
                    fontWeight="semibold"
                    color={
                      spendChangePercent == null
                        ? undefined
                        : spendChangePercent > 0
                          ? "#a8f0c6"
                          : spendChangePercent < 0
                            ? "#ffb3ac"
                            : undefined
                    }
                  >
                    {spendChangePercent == null
                      ? "—"
                      : `${spendChangePercent > 0 ? "↑" : spendChangePercent < 0 ? "↓" : "→"} ${Math.abs(spendChangePercent).toFixed(1)}%`}
                  </Text>
                </Flex>
              </VStack>
            </Box>
          </>
        )}
      </Box>

      <Box
        flex={1}
        bg="white"
        borderRadius="12px"
        borderWidth="1px"
        borderColor="gray.200"
        p="20px 24px"
      >
        <Text
          fontSize="12px"
          letterSpacing="0.04em"
          color="gray.600"
          fontWeight="semibold"
          mb={4}
        >
          SPEND BY MODEL TASK TYPE
        </Text>
        {isLoading ? (
          <Center h="150px">
            <Spinner color="blue.500" />
          </Center>
        ) : error ? (
          <Text fontSize="sm" color="red.500">
            {error}
          </Text>
        ) : sorted.length === 0 ? (
          <Text fontSize="sm" color="gray.400" py={8} textAlign="center">
            No spend data for this period.
          </Text>
        ) : (
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
              <Center
                position="absolute"
                inset={0}
                pointerEvents="none"
                textAlign="center"
                px="22px"
              >
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
                    cursor="default"
                    onMouseEnter={() => setHlKey(item.modelTaskType)}
                    onMouseLeave={() => setHlKey(null)}
                  >
                    <HStack spacing="9px" minW={0}>
                      <Box w="9px" h="9px" borderRadius="full" bg={color} flexShrink={0} />
                      <Text fontSize="13px" fontWeight="semibold" whiteSpace="nowrap">
                        {formatModelTaskTypeLabel(item.modelTaskType)}
                      </Text>
                      <Text fontSize="12px" color="gray.500" noOfLines={1}>
                        {formatUnit(item.consumption, item.unit)}
                      </Text>
                    </HStack>
                    <Box textAlign="right" flexShrink={0}>
                      <Text fontSize="13px" fontWeight="semibold" display="block">
                        {formatMoney(item.spend, currency)}
                      </Text>
                      <Text fontSize="11.5px" color="gray.500">
                        {item.percentage.toFixed(1)}%
                      </Text>
                    </Box>
                  </Flex>
                );
              })}
            </Box>
          </Flex>
        )}
      </Box>
    </Flex>
  );
}

function TenantExpandRow({
  row,
  taskColorByType,
}: {
  row: TenantUsageItem;
  taskColorByType: Map<string, string>;
}) {
  const tiers = row.tierBreakdown ?? [];
  const hasMultiTier = tiers.length > 1;

  if (hasMultiTier) {
    return (
      <VStack align="stretch" spacing={0} maxH="236px" overflowY="auto" py={1}>
        {tiers.map((tier) => (
          <Box key={tier.tierId} px={4} py="10px" borderTopWidth="1px" borderColor="gray.200" _first={{ borderTopWidth: 0 }}>
            <Flex align="center" gap={3} mb={2}>
              <Text
                fontSize="10px"
                fontWeight="bold"
                letterSpacing="0.03em"
                bg="gray.50"
                borderWidth="1px"
                borderColor="gray.200"
                color="gray.600"
                px="9px"
                py="3px"
                borderRadius="5px"
              >
                {tier.tierName.toUpperCase()}
              </Text>
              <Text ml="auto" fontWeight="bold" fontSize="13px">
                {formatMoney(tier.spend, row.currency)}
              </Text>
            </Flex>
            {(tier.taskTypes ?? []).map((t) => (
              <Box
                key={`${tier.tierId}-${t.taskType}`}
                display="grid"
                gridTemplateColumns="26% 48% 26%"
                alignItems="center"
                py="7px"
                gap="10px"
              >
                <HStack spacing={2} fontSize="12.5px" fontWeight="medium">
                  <Box
                    w="8px"
                    h="8px"
                    borderRadius="full"
                    bg={taskColorByType.get(t.taskType) ?? ACCENT}
                    flexShrink={0}
                  />
                  <Text>{formatModelTaskTypeLabel(t.taskType)}</Text>
                </HStack>
                <UsageCell
                  consumed={t.consumed}
                  quotaLimit={t.quotaLimit}
                  remaining={t.remaining}
                  percentage={t.percentage}
                  unit={t.unit}
                />
                <Text fontWeight="semibold" fontSize="12.5px" textAlign="right">
                  {formatMoney(t.spend, row.currency)}
                </Text>
              </Box>
            ))}
          </Box>
        ))}
      </VStack>
    );
  }

  const tasks = [...aggregateTasks(tiers)].sort(
    (a, b) => b.consumed / Math.max(b.quotaLimit, 1) - a.consumed / Math.max(a.quotaLimit, 1),
  );

  return (
    <VStack align="stretch" spacing={0} maxH="236px" overflowY="auto" py={1}>
      {tasks.map((t) => (
        <Box
          key={t.taskType}
          display="grid"
          gridTemplateColumns={{ base: "1fr", md: "32% 14% 22% 32%" }}
          alignItems="center"
          px={4}
          py={2}
          gap={3}
        >
          <HStack spacing={2} fontSize="13px" fontWeight="medium" pl={{ base: 0, md: "36px" }}>
            <Box
              w="8px"
              h="8px"
              borderRadius="full"
              bg={taskColorByType.get(t.taskType) ?? ACCENT}
              flexShrink={0}
            />
            <Text>{formatModelTaskTypeLabel(t.taskType)}</Text>
          </HStack>
          <Text fontWeight="bold" fontSize="13px">
            {formatMoney(t.spend, row.currency)}
          </Text>
          <Box />
          <UsageCell
            consumed={t.consumed}
            quotaLimit={t.quotaLimit}
            remaining={t.remaining}
            percentage={t.quotaLimit > 0 ? (t.consumed / t.quotaLimit) * 100 : 0}
            unit={t.unit}
          />
        </Box>
      ))}
    </VStack>
  );
}

function TenantDetailDrawer({
  isOpen,
  onClose,
  detail,
  isLoading,
  periodLabel,
}: {
  isOpen: boolean;
  onClose: () => void;
  detail: TenantUsageDetail | null;
  isLoading: boolean;
  periodLabel: string;
}) {
  const taskRows = useMemo(() => {
    if (!detail) return [];
    const tiers = detail.tierBreakdown ?? [];
    if (tiers.length > 1) {
      return tiers.flatMap((tier) => [
        { kind: "tier" as const, tier },
        ...(tier.taskTypes ?? []).map((t) => ({ kind: "task" as const, task: t, tierName: tier.tierName })),
      ]);
    }
    return aggregateTasks(tiers)
      .sort((a, b) => b.spend - a.spend)
      .map((t) => ({ kind: "task" as const, task: t }));
  }, [detail]);

  const spend = detail?.spend ?? 0;
  const hasMultiTier = (detail?.tierBreakdown?.length ?? 0) > 1;

  return (
    <Drawer isOpen={isOpen} placement="right" onClose={onClose} size="md">
      <DrawerOverlay bg="rgba(15,18,25,0.4)" />
      <DrawerContent maxW="640px">
        <DrawerCloseButton top={4} right={4} />
        <DrawerHeader fontSize="17px" fontWeight="bold" pb={2}>
          Tenant Spend Details
        </DrawerHeader>
        <DrawerBody pb={10}>
          {isLoading ? (
            <Center py={12}>
              <Spinner color="blue.500" />
            </Center>
          ) : detail ? (
            <VStack align="stretch" spacing={5}>
              <HStack spacing="11px">
                <Center
                  w="36px"
                  h="36px"
                  borderRadius="full"
                  bg={tenantAvatarBg(detail.tenantName)}
                  color="white"
                  fontSize="14px"
                  fontWeight="bold"
                  flexShrink={0}
                >
                  {tenantInitials(detail.tenantName)}
                </Center>
                <Text fontSize="16px" fontWeight="bold">
                  {detail.tenantName}
                </Text>
                <Text
                  fontSize="10px"
                  fontWeight="bold"
                  letterSpacing="0.03em"
                  bg="gray.50"
                  borderWidth="1px"
                  borderColor="gray.200"
                  color="gray.600"
                  px="9px"
                  py="3px"
                  borderRadius="5px"
                >
                  {detail.tier.toUpperCase()}
                </Text>
              </HStack>

              <Box>
                <Text fontSize="11px" letterSpacing="0.04em" color="gray.600" fontWeight="semibold" mb="10px">
                  BUDGET
                </Text>
                <Box bg="gray.50" borderRadius="10px" p="16px 18px">
                  <BudgetCell
                    limit={detail.budget.limit}
                    spent={detail.budget.spent}
                    remaining={detail.budget.remaining}
                    percentageUsed={detail.budget.percentageUsed}
                    currency={detail.currency}
                  />
                </Box>
              </Box>

              <Box>
                <Text fontSize="11px" letterSpacing="0.04em" color="gray.600" fontWeight="semibold" mb="10px">
                  SPEND BY MODEL TASK TYPE — {periodLabel}
                </Text>
                <Box overflowX="auto" borderWidth="1px" borderColor="gray.200" borderRadius="md">
                  <Table size="sm" variant="simple">
                    <Thead bg="gray.50">
                      <Tr>
                        <Th fontSize="10.5px" letterSpacing="0.04em" color="gray.600" w="26%">
                          MODEL TASK TYPE
                        </Th>
                        <Th fontSize="10.5px" letterSpacing="0.04em" color="gray.600" w="38%">
                          USAGE
                        </Th>
                        <Th fontSize="10.5px" letterSpacing="0.04em" color="gray.600" w="20%">
                          SPEND
                        </Th>
                        <Th fontSize="10.5px" letterSpacing="0.04em" color="gray.600" w="16%">
                          SHARE
                        </Th>
                      </Tr>
                    </Thead>
                    <Tbody>
                      {taskRows.map((row, idx) => {
                        if (row.kind === "tier") {
                          return (
                            <Tr key={`tier-${row.tier.tierId}`}>
                              <Td
                                colSpan={4}
                                bg="gray.50"
                                fontWeight="bold"
                                fontSize="10.5px"
                                letterSpacing="0.03em"
                                color="gray.600"
                                py={2}
                              >
                                {row.tier.tierName.toUpperCase()} · {formatMoney(row.tier.spend, detail.currency)}
                              </Td>
                            </Tr>
                          );
                        }
                        const t = row.task;
                        const share = spend > 0 ? ((t.spend / spend) * 100).toFixed(1) : "0.0";
                        const color = taskTypeColor(t.taskType, idx);
                        return (
                          <Tr key={`${"tierName" in row ? row.tierName : ""}-${t.taskType}-${idx}`}>
                            <Td>
                              <HStack spacing={2} fontWeight="semibold">
                                <Box w="9px" h="9px" borderRadius="full" bg={color} flexShrink={0} />
                                <Text fontSize="sm">{formatModelTaskTypeLabel(t.taskType)}</Text>
                              </HStack>
                            </Td>
                            <Td>
                              <UsageCell
                                consumed={t.consumed}
                                quotaLimit={t.quotaLimit}
                                remaining={t.remaining}
                                percentage={
                                  "percentage" in t && typeof t.percentage === "number"
                                    ? t.percentage
                                    : t.quotaLimit > 0
                                      ? (t.consumed / t.quotaLimit) * 100
                                      : 0
                                }
                                unit={t.unit}
                              />
                            </Td>
                            <Td fontSize="sm">{formatMoney(t.spend, detail.currency)}</Td>
                            <Td fontSize="12.5px" color="gray.500">
                              {share}%
                            </Td>
                          </Tr>
                        );
                      })}
                      <Tr bg="gray.50">
                        <Td fontWeight="bold" fontSize="sm">
                          Total
                        </Td>
                        <Td color="gray.500" fontWeight="normal" fontSize="12px">
                          —
                        </Td>
                        <Td fontWeight="bold" fontSize="sm">
                          {formatMoney(spend, detail.currency)}
                        </Td>
                        <Td fontWeight="bold" fontSize="sm">
                          100%
                        </Td>
                      </Tr>
                    </Tbody>
                  </Table>
                </Box>
                {hasMultiTier ? (
                  <Text fontSize="11.5px" color="gray.500" lineHeight="1.5" mt="10px">
                    Grouped by tier since this tenant changed tier during the period — spend and usage
                    above the group total are cumulative across all tiers.
                  </Text>
                ) : null}
              </Box>
            </VStack>
          ) : null}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}

const UsageAndSpendTab: React.FC<UsageAndSpendTabProps> = ({
  scopeTenantId = null,
  isTenantView = false,
  tenantId = null,
  refreshNonce = 0,
}) => {
  const [periodKey, setPeriodKey] = useState<"current" | "last">("current");
  const [filterTierId, setFilterTierId] = useState("");
  const [filterTaskType, setFilterTaskType] = useState("");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedTenant, setSelectedTenant] = useState<TenantUsageDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const { isOpen: isDetailOpen, onOpen: onDetailOpen, onClose: onDetailClose } = useDisclosure();
  const { taskTypeNames } = useInferenceTypes();

  const billingPeriod = billingPeriodValue(periodKey);
  const previousBillingPeriod = billingPeriodValue("last");
  const scopedId = (isTenantView ? tenantId : scopeTenantId)?.trim() || null;
  const isScoped = Boolean(scopedId);

  const summaryQuery = useQuery({
    queryKey: ["usage-summary", billingPeriod, refreshNonce],
    queryFn: () => fetchUsageSummary({ billingPeriod }),
    enabled: !isScoped,
    staleTime: STALE_MS,
    retry: 1,
  });

  // Fallback when usage-summary omits spendChangePercent: compare current vs prior month.
  const previousSummaryQuery = useQuery({
    queryKey: ["usage-summary", previousBillingPeriod, refreshNonce],
    queryFn: () => fetchUsageSummary({ billingPeriod: previousBillingPeriod }),
    enabled: !isScoped && periodKey === "current",
    staleTime: STALE_MS,
    retry: 1,
  });

  const scopedQuery = useQuery({
    queryKey: ["usage-tenant", scopedId, billingPeriod, refreshNonce],
    queryFn: () => {
      if (!scopedId) throw new Error("Tenant id is required");
      return fetchTenantUsageById(scopedId, billingPeriod);
    },
    enabled: isScoped,
    staleTime: STALE_MS,
    retry: 1,
  });

  const tenantsQuery = useQuery({
    queryKey: [
      "usage-tenants",
      billingPeriod,
      filterTierId,
      filterTaskType,
      sortOrder,
      refreshNonce,
    ],
    queryFn: () =>
      fetchTenantUsageList({
        billingPeriod,
        tierId: filterTierId || undefined,
        modelTaskType: filterTaskType || undefined,
        sortOrder,
        limit: 100,
        offset: 0,
      }),
    enabled: !isScoped,
    staleTime: STALE_MS,
    retry: 1,
  });

  const tiersQuery = useQuery({
    queryKey: ["tiers", refreshNonce],
    queryFn: () => fetchTiers(),
    staleTime: 5 * STALE_MS,
    retry: 1,
  });

  const tenants: TenantUsageItem[] = useMemo(() => {
    if (isScoped) return scopedQuery.data ? [scopedQuery.data] : [];
    return tenantsQuery.data?.data ?? [];
  }, [isScoped, scopedQuery.data, tenantsQuery.data?.data]);

  const summaryData: UsageSummaryResponse | undefined = useMemo(() => {
    if (isScoped) return scopedQuery.data ? summaryFromDetail(scopedQuery.data) : undefined;
    const summary = summaryQuery.data;
    if (!summary) return undefined;

    let next: UsageSummaryResponse = summary;
    if (filterTaskType) {
      const spendByModelTaskType = summary.spendByModelTaskType.filter(
        (i) => i.modelTaskType.trim().toLowerCase() === filterTaskType.trim().toLowerCase(),
      );
      const totalSpend = spendByModelTaskType.reduce((s, i) => s + i.spend, 0);
      next = {
        ...summary,
        totalSpend,
        spendByModelTaskType: spendByModelTaskType.map((i) => ({
          ...i,
          percentage: totalSpend > 0 ? Number(((i.spend / totalSpend) * 100).toFixed(1)) : 0,
        })),
      };
    }

    // Derive tenant stats from the table when summary API omits them.
    if (next.activeTenants == null || next.budgetExceededTenants == null) {
      const rows = tenantsQuery.data?.data ?? [];
      next = {
        ...next,
        activeTenants: next.activeTenants ?? (tenantsQuery.data?.total ?? rows.length),
        budgetExceededTenants:
          next.budgetExceededTenants ??
          rows.filter((r) => r.budget.percentageUsed > 100 || r.budget.remaining < 0).length,
      };
    }

    return next;
  }, [
    isScoped,
    scopedQuery.data,
    summaryQuery.data,
    filterTaskType,
    tenantsQuery.data?.data,
    tenantsQuery.data?.total,
  ]);

  const spendChangePercent = useMemo((): number | null => {
    if (periodKey !== "current") return null;

    const apiValue = summaryData?.spendChangePercent ?? summaryQuery.data?.spendChangePercent;
    if (typeof apiValue === "number" && Number.isFinite(apiValue)) return apiValue;

    if (isScoped) return null;

    if (!previousSummaryQuery.isFetched && (previousSummaryQuery.isLoading || previousSummaryQuery.isFetching)) {
      return null;
    }

    const currentTotal = summaryQuery.data?.totalSpend;
    if (currentTotal == null) return null;

    const prevTotal = previousSummaryQuery.data?.totalSpend;
    if (prevTotal == null) {
      // Prior period request failed or empty — still show a MoM figure from current spend alone.
      return currentTotal > 0 ? 100 : 0;
    }
    if (prevTotal <= 0) return currentTotal > 0 ? 100 : 0;
    return Number((((currentTotal - prevTotal) / prevTotal) * 100).toFixed(1));
  }, [
    periodKey,
    isScoped,
    summaryData?.spendChangePercent,
    summaryQuery.data?.spendChangePercent,
    summaryQuery.data?.totalSpend,
    previousSummaryQuery.data?.totalSpend,
    previousSummaryQuery.isFetched,
    previousSummaryQuery.isLoading,
    previousSummaryQuery.isFetching,
  ]);

  const taskTypeOptions = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    const add = (t: string) => {
      const n = t.trim();
      if (n && !seen.has(n)) {
        seen.add(n);
        out.push(n);
      }
    };
    taskTypeNames.forEach(add);
    (summaryQuery.data?.spendByModelTaskType ?? []).forEach((i: SpendByTaskType) =>
      add(i.modelTaskType),
    );
    (scopedQuery.data?.tierBreakdown ?? []).forEach((tier) =>
      (tier.taskTypes ?? []).forEach((t) => add(t.taskType)),
    );
    return out;
  }, [taskTypeNames, summaryQuery.data?.spendByModelTaskType, scopedQuery.data?.tierBreakdown]);

  const taskColorByType = useMemo(() => {
    const map = new Map<string, string>();
    taskTypeOptions.forEach((t, i) => map.set(t, taskTypeColor(t, i)));
    return map;
  }, [taskTypeOptions]);

  const errMsg = (e: unknown) => (e ? parseError(e).message : null);
  const summaryError = isScoped ? errMsg(scopedQuery.error) : errMsg(summaryQuery.error);
  const tenantsError = isScoped ? errMsg(scopedQuery.error) : errMsg(tenantsQuery.error);
  const isSummaryLoading = isScoped ? scopedQuery.isLoading : summaryQuery.isLoading;
  const isTenantsLoading = isScoped ? scopedQuery.isLoading : tenantsQuery.isLoading;
  const currency = summaryData?.currency || tenants[0]?.currency || "INR";

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleTenantClick = useCallback(
    async (row: TenantUsageItem) => {
      setIsDetailLoading(true);
      onDetailOpen();
      try {
        setSelectedTenant(await fetchTenantUsageById(row.tenantId, billingPeriod));
      } catch {
        setSelectedTenant(row);
      } finally {
        setIsDetailLoading(false);
      }
    },
    [onDetailOpen, billingPeriod],
  );

  const toggleSort = () => setSortOrder((o) => (o === "desc" ? "asc" : "desc"));

  return (
    <VStack align="stretch" spacing={5}>
      <Flex justify="space-between" align="flex-start" gap={6} flexWrap="wrap">
        <Box>
          <Text fontSize="26px" fontWeight="semibold" lineHeight="1.2" mb={1}>
            Usage and Spend
          </Text>
          <Text fontSize="14px" color="gray.600">
            Monitor model task type consumption and spend across all tenants
          </Text>
        </Box>
        <FormControl w="auto">
          <Text
            fontSize="12px"
            color="gray.500"
            fontWeight="semibold"
            letterSpacing="0.03em"
            textAlign="right"
            mb={1}
          >
            BILLING PERIOD
          </Text>
          <Select
            size="sm"
            value={periodKey}
            onChange={(e) => setPeriodKey(e.target.value as "current" | "last")}
            borderRadius="8px"
            minW="180px"
            bg="white"
          >
            <option value="current">Current month</option>
            <option value="last">Last month</option>
          </Select>
        </FormControl>
      </Flex>

      <SpendOverviewPanel
        summary={summaryData}
        isLoading={isSummaryLoading}
        error={summaryError}
        currency={currency}
        spendChangePercent={spendChangePercent}
      />

      {!isScoped ? (
        <HStack spacing={3} flexWrap="wrap">
          <Select
            size="sm"
            w={{ base: "full", sm: "220px" }}
            value={filterTierId}
            onChange={(e) => setFilterTierId(e.target.value)}
            borderRadius="8px"
            bg="white"
          >
            <option value="">Filter by tier · All tiers</option>
            {(tiersQuery.data?.data ?? []).map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
          <Select
            size="sm"
            w={{ base: "full", sm: "260px" }}
            value={filterTaskType}
            onChange={(e) => setFilterTaskType(e.target.value)}
            borderRadius="8px"
            bg="white"
          >
            <option value="">Filter by model task type · All</option>
            {taskTypeOptions.map((t) => (
              <option key={t} value={t}>
                {formatModelTaskTypeLabel(t)}
              </option>
            ))}
          </Select>
        </HStack>
      ) : null}

      <MeteringAsyncState
        isLoading={isTenantsLoading}
        isEmpty={!isTenantsLoading && tenants.length === 0}
        errorMessage={tenantsError}
        emptyMessage={
          isScoped
            ? "No usage data available for this tenant."
            : "No tenant usage data available."
        }
      >
        <Box
          overflowX="auto"
          borderWidth="1px"
          borderColor="gray.200"
          borderRadius="12px"
          bg="white"
        >
          <Table size="sm" variant="simple" sx={{ "th, td": { verticalAlign: "middle" } }}>
            <Thead bg="gray.50">
              <Tr>
                <Th fontSize="11px" letterSpacing="0.04em" color="gray.600" w="22%">
                  TENANT
                </Th>
                <Th fontSize="11px" letterSpacing="0.04em" color="gray.600" w="10%">
                  TIER
                </Th>
                <Th
                  fontSize="11px"
                  letterSpacing="0.04em"
                  color="gray.600"
                  w="14%"
                  cursor="pointer"
                  userSelect="none"
                  onClick={toggleSort}
                >
                  SPEND <Text as="span" fontSize="10px">{sortOrder === "desc" ? "↓" : "↑"}</Text>
                </Th>
                <Th fontSize="11px" letterSpacing="0.04em" color="gray.600" w="22%">
                  BUDGET
                </Th>
                <Th fontSize="11px" letterSpacing="0.04em" color="gray.600" w="32%">
                  USAGE
                </Th>
              </Tr>
            </Thead>
            <Tbody>
              {tenants.map((row) => {
                const isOpen = expanded.has(row.tenantId);
                const taskCount =
                  row.usage?.taskTypeCount ?? aggregateTasks(row.tierBreakdown ?? []).length;
                const canExpand = !filterTaskType && taskCount > 1;

                let usageCell: React.ReactNode;
                if (taskCount === 0) {
                  usageCell = (
                    <Text fontSize="12px" color="gray.500">
                      Not used this period
                    </Text>
                  );
                } else if (filterTaskType || taskCount === 1) {
                  usageCell = (
                    <UsageCell
                      consumed={row.usage.consumed}
                      quotaLimit={row.usage.quotaLimit}
                      remaining={row.usage.remaining}
                      percentage={row.usage.percentage}
                      unit={row.usage.unit}
                    />
                  );
                } else {
                  usageCell = (
                    <HStack
                      as="button"
                      spacing={1.5}
                      color={ACCENT}
                      fontSize="13px"
                      fontWeight="semibold"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleExpand(row.tenantId);
                      }}
                    >
                      <Text>{taskCount} task types</Text>
                      <ChevronDownIcon
                        boxSize={3.5}
                        transform={isOpen ? "rotate(180deg)" : undefined}
                        transition="transform 0.15s ease"
                      />
                    </HStack>
                  );
                }

                return (
                  <React.Fragment key={row.tenantId}>
                    <Tr _hover={{ bg: "gray.50" }}>
                      <Td>
                        <HStack spacing="10px">
                          <IconButton
                            aria-label={`Toggle usage breakdown for ${row.tenantName}`}
                            icon={<ChevronRightIcon />}
                            size="xs"
                            variant="ghost"
                            visibility={canExpand ? "visible" : "hidden"}
                            transform={isOpen ? "rotate(90deg)" : undefined}
                            transition="transform 0.15s ease"
                            onClick={() => toggleExpand(row.tenantId)}
                          />
                          <Center
                            w="26px"
                            h="26px"
                            borderRadius="full"
                            bg={tenantAvatarBg(row.tenantName)}
                            color="white"
                            fontSize="11px"
                            fontWeight="bold"
                            flexShrink={0}
                          >
                            {tenantInitials(row.tenantName)}
                          </Center>
                          <Text
                            as="button"
                            fontSize="13px"
                            color={ACCENT}
                            fontWeight="semibold"
                            textAlign="left"
                            onClick={() => handleTenantClick(row)}
                          >
                            {row.tenantName}
                          </Text>
                        </HStack>
                      </Td>
                      <Td>
                        <Text
                          fontSize="10px"
                          fontWeight="bold"
                          letterSpacing="0.03em"
                          bg="gray.50"
                          borderWidth="1px"
                          borderColor="gray.200"
                          color="gray.600"
                          px="9px"
                          py="3px"
                          borderRadius="5px"
                          display="inline-block"
                        >
                          {row.tier.toUpperCase()}
                        </Text>
                      </Td>
                      <Td>
                        <Text fontWeight="bold" fontSize="14px">
                          {formatMoney(row.spend, row.currency)}
                        </Text>
                      </Td>
                      <Td>
                        <BudgetCell
                          limit={row.budget.limit}
                          spent={row.budget.spent}
                          remaining={row.budget.remaining}
                          percentageUsed={row.budget.percentageUsed}
                          currency={row.currency}
                        />
                      </Td>
                      <Td>{usageCell}</Td>
                    </Tr>
                    {isOpen && canExpand ? (
                      <Tr>
                        <Td colSpan={5} bg="gray.50" p={0} borderBottomWidth="1px" borderColor="gray.200">
                          <TenantExpandRow row={row} taskColorByType={taskColorByType} />
                        </Td>
                      </Tr>
                    ) : null}
                  </React.Fragment>
                );
              })}
            </Tbody>
          </Table>
        </Box>
      </MeteringAsyncState>

      <Text fontSize="12px" color="gray.500" lineHeight="1.6">
        Spend is a sortable column. Budget shows utilization against the allocated limit. Units follow
        each service&apos;s metering definition. Tier and task type filters apply to the table; expand
        a tenant to see task-type breakdown, grouped by tier when the tenant changed tiers mid-period.
      </Text>

      <TenantDetailDrawer
        isOpen={isDetailOpen}
        onClose={onDetailClose}
        detail={selectedTenant}
        isLoading={isDetailLoading}
        periodLabel={billingPeriodLabel(periodKey)}
      />
    </VStack>
  );
};

export default UsageAndSpendTab;
