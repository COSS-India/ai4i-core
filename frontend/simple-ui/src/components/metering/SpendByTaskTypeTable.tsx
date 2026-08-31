import { Box, HStack, Table, Tbody, Td, Text, Thead, Tr } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import {
  aggregateTasks,
  formatSpendMoney,
  taskTypeColor,
  type AggregatedTaskUsage,
} from "../../utils/usageSpendHelpers";
import { useMeteringTableSort } from "../../utils/meteringTableSort";
import type { TenantTierBreakdown, TierTaskTypeUsage } from "../../types/usageSpend";
import { TaskTypeLabel, TierBadge, UsageCell } from "./UsageSpendCells";
import SortableTh from "./SortableTh";

function quotaUsagePercentage(t: TierTaskTypeUsage | AggregatedTaskUsage): number {
  if ("percentage" in t && typeof t.percentage === "number") return t.percentage;
  const limit = t.quotaLimit ?? 0;
  if (limit <= 0) return 0;
  return (t.consumed / limit) * 100;
}

type TaskSpendRow = {
  kind: "task";
  task: TierTaskTypeUsage | AggregatedTaskUsage;
  tierName?: string;
};

type SpendRow = { kind: "tier"; tier: TenantTierBreakdown } | TaskSpendRow;

interface SpendByTaskTypeTableProps {
  tierBreakdown: TenantTierBreakdown[];
  totalSpend: number;
  currency: string;
  emptyMessage?: string;
}

const SpendByTaskTypeTable: React.FC<SpendByTaskTypeTableProps> = ({
  tierBreakdown,
  totalSpend,
  currency,
  emptyMessage = "No spend data for this period.",
}) => {
  const multiTier = tierBreakdown.length > 1;

  const taskRows = useMemo<TaskSpendRow[]>(() => {
    if (multiTier) {
      return tierBreakdown.flatMap((tier) =>
        (tier.taskTypes ?? []).map((t) => ({
          kind: "task" as const,
          task: t,
          tierName: tier.tierName,
        })),
      );
    }
    return aggregateTasks(tierBreakdown).map((t) => ({ kind: "task" as const, task: t }));
  }, [tierBreakdown, multiTier]);

  const sortAccessors = useMemo(
    () => ({
      taskType: (row: TaskSpendRow) => row.task.taskType,
      consumed: (row: TaskSpendRow) => row.task.consumed,
      spend: (row: TaskSpendRow) => row.task.spend,
      share: (row: TaskSpendRow) =>
        totalSpend > 0 ? (row.task.spend / totalSpend) * 100 : 0,
    }),
    [totalSpend],
  );

  const { sortedRows, sortKey, sortDirection, toggleSort } = useMeteringTableSort(
    taskRows,
    "spend",
    sortAccessors,
  );

  const displayRows = useMemo((): SpendRow[] => {
    if (!multiTier) return sortedRows;
    return tierBreakdown.flatMap((tier) => {
      const tierTasks = sortedRows.filter((r) => r.tierName === tier.tierName);
      return [{ kind: "tier" as const, tier }, ...tierTasks];
    });
  }, [multiTier, tierBreakdown, sortedRows]);

  const visibleSpend = useMemo(
    () => sortedRows.reduce((s, r) => s + r.task.spend, 0),
    [sortedRows],
  );

  if (taskRows.length === 0) {
    return (
      <Text fontSize="sm" color="gray.400" py={8} textAlign="center">
        {emptyMessage}
      </Text>
    );
  }

  const thSx = { fontSize: "10.5px", letterSpacing: "0.04em", color: "gray.600" } as const;

  return (
    <Box overflowX="auto" borderWidth="1px" borderColor="gray.200" borderRadius="md">
      <Table size="sm" variant="simple" minW="540px" sx={{ tableLayout: "fixed" }}>
        <Thead bg="gray.50">
          <Tr>
            <SortableTh
              sortKey="taskType"
              activeSortKey={sortKey}
              sortDirection={sortDirection}
              onSort={toggleSort}
              w="28%"
              sx={thSx}
            >
              MODEL TASK TYPE
            </SortableTh>
            <SortableTh
              sortKey="consumed"
              activeSortKey={sortKey}
              sortDirection={sortDirection}
              onSort={toggleSort}
              message={METERING.USAGE_SPEND.TOOLTIPS.USAGE}
              w="40%"
              sx={thSx}
            >
              USAGE
            </SortableTh>
            <SortableTh
              sortKey="spend"
              activeSortKey={sortKey}
              sortDirection={sortDirection}
              onSort={toggleSort}
              message={METERING.USAGE_SPEND.TOOLTIPS.SPEND}
              w="18%"
              isNumeric
              sx={thSx}
            >
              SPEND
            </SortableTh>
            <SortableTh
              sortKey="share"
              activeSortKey={sortKey}
              sortDirection={sortDirection}
              onSort={toggleSort}
              message={METERING.USAGE_SPEND.TOOLTIPS.SHARE}
              w="14%"
              isNumeric
              sx={thSx}
            >
              SHARE
            </SortableTh>
          </Tr>
        </Thead>
        <Tbody>
          {displayRows.map((row, idx) => {
            if (row.kind === "tier") {
              return (
                <Tr key={`tier-${row.tier.tierId}`}>
                  <Td colSpan={4} bg="gray.50" py={2}>
                    <HStack spacing={2}>
                      <TierBadge label={row.tier.tierName} />
                      <Text fontSize="10.5px" fontWeight="bold" color="gray.600">
                        {formatSpendMoney(row.tier.spend, currency)}
                      </Text>
                    </HStack>
                  </Td>
                </Tr>
              );
            }
            const t = row.task;
            const share = totalSpend > 0 ? ((t.spend / totalSpend) * 100).toFixed(1) : "0.0";
            const color = taskTypeColor(t.taskType, idx);
            return (
              <Tr key={`${row.tierName ?? ""}-${t.taskType}-${idx}`}>
                <Td>
                  <TaskTypeLabel
                    taskType={t.taskType}
                    color={color}
                    fontSize="sm"
                    fontWeight="semibold"
                  />
                </Td>
                <Td>
                  <UsageCell
                    consumed={t.consumed}
                    quotaLimit={t.quotaLimit}
                    remaining={t.remaining}
                    percentage={quotaUsagePercentage(t)}
                    unit={t.unit}
                    compact
                  />
                </Td>
                <Td fontSize="sm" isNumeric>
                  {formatSpendMoney(t.spend, currency)}
                </Td>
                <Td fontSize="12.5px" color="gray.500" isNumeric>
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
            <Td fontWeight="bold" fontSize="sm" isNumeric>
              {formatSpendMoney(visibleSpend, currency)}
            </Td>
            <Td fontWeight="bold" fontSize="sm" isNumeric>
              {totalSpend > 0 ? `${((visibleSpend / totalSpend) * 100).toFixed(0)}%` : "0%"}
            </Td>
          </Tr>
        </Tbody>
      </Table>
    </Box>
  );
};

export default SpendByTaskTypeTable;
