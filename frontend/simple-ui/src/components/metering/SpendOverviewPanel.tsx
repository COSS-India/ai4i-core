import { Box, Center, Flex, HStack, Spinner, Text, VStack } from "@chakra-ui/react";
import React, { useMemo, useState } from "react";
import { Cell, Pie, PieChart } from "recharts";
import {
  formatSpendMoney,
  formatSpendUnit,
  taskTypeColor,
} from "../../utils/usageSpendHelpers";
import type { UsageSummaryResponse } from "../../types/usageSpend";
import MeteringChartPanel from "./MeteringChartPanel";
import { TaskTypeLabel } from "./UsageSpendCells";

interface SpendOverviewPanelProps {
  summary?: UsageSummaryResponse;
  isLoading: boolean;
  error: string | null;
  currency: string;
  spendChangePercent: number | null;
  emptyStateMessage?: string;
}

const SpendOverviewPanel: React.FC<SpendOverviewPanelProps> = ({
  summary,
  isLoading,
  error,
  currency,
  spendChangePercent,
  emptyStateMessage = "No spend data for this period.",
}) => {
  const [hlKey, setHlKey] = useState<string | null>(null);
  const items = summary?.spendByModelTaskType ?? [];
  const sorted = useMemo(() => [...items].sort((a, b) => b.spend - a.spend), [items]);
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
        <Text fontSize="12px" letterSpacing="0.04em" color="gray.600" fontWeight="semibold" mb={4}>
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
            {emptyStateMessage}
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
                    cursor="default"
                    onMouseEnter={() => setHlKey(item.modelTaskType)}
                    onMouseLeave={() => setHlKey(null)}
                  >
                    <HStack spacing="9px" minW={0}>
                      <TaskTypeLabel
                        taskType={item.modelTaskType}
                        color={color}
                        fontWeight="semibold"
                      />
                      <Text fontSize="12px" color="gray.500" noOfLines={1}>
                        {formatSpendUnit(item.consumption, item.unit)}
                      </Text>
                    </HStack>
                    <Box textAlign="right" flexShrink={0}>
                      <Text fontSize="13px" fontWeight="semibold" display="block">
                        {formatSpendMoney(item.spend, currency)}
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
};

export default SpendOverviewPanel;
