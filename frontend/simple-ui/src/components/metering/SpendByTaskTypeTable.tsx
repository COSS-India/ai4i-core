import { Box, HStack, Table, Tbody, Td, Text, Thead, Tr } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import {
  aggregateTasks,
  taskTypeColor,
  type AggregatedTaskUsage,
} from "../../utils/usageSpendHelpers";
import { useMeteringTableSort } from "../../utils/meteringTableSort";
import type { TenantTierBreakdown, TierTaskTypeUsage } from "../../types/usageSpend";
import { TaskTypeLabel, TierBadge, UsageCell } from "./UsageSpendCells";
import SortableTh from "./SortableTh";

function quotaUsagePercentage(t: TierTaskTypeUsage | AggregatedTaskUsage): number {
  const limit = t.quotaLimit ?? 0;
  if (limit <= 0) return 0;
  return (t.consumed / limit) * 100;
}

type TaskUsageRow = {
  kind: "task";
  task: TierTaskTypeUsage | AggregatedTaskUsage;
  tierName?: string;
};

type DisplayRow = { kind: "tier"; tier: TenantTierBreakdown } | TaskUsageRow;

interface SpendByTaskTypeTableProps {
  tierBreakdown: TenantTierBreakdown[];
  emptyMessage?: string;
  usageColumnLabel?: string;
}

const SpendByTaskTypeTable: React.FC<SpendByTaskTypeTableProps> = ({
  tierBreakdown,
  emptyMessage = "No usage data for this period.",
  usageColumnLabel = METERING.USAGE_SPEND.USAGE_VS_MONTHLY_QUOTA,
}) => {
  const multiTier = tierBreakdown.length > 1;

  const taskRows = useMemo<TaskUsageRow[]>(() => {
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
      taskType: (row: TaskUsageRow) => row.task.taskType,
      consumed: (row: TaskUsageRow) => row.task.consumed,
    }),
    [],
  );

  const { sortedRows, sortKey, sortDirection, toggleSort } = useMeteringTableSort(
    taskRows,
    "consumed",
    sortAccessors,
  );

  const displayRows = useMemo((): DisplayRow[] => {
    if (!multiTier) return sortedRows;
    return tierBreakdown.flatMap((tier) => {
      const tierTasks = sortedRows.filter((r) => r.tierName === tier.tierName);
      return [{ kind: "tier" as const, tier }, ...tierTasks];
    });
  }, [multiTier, tierBreakdown, sortedRows]);

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
      <Table size="sm" variant="simple" minW="400px" sx={{ tableLayout: "fixed" }}>
        <Thead bg="gray.50">
          <Tr>
            <SortableTh
              sortKey="taskType"
              activeSortKey={sortKey}
              sortDirection={sortDirection}
              onSort={toggleSort}
              w="36%"
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
              w="64%"
              sx={thSx}
            >
              {usageColumnLabel}
            </SortableTh>
          </Tr>
        </Thead>
        <Tbody>
          {displayRows.map((row, idx) => {
            if (row.kind === "tier") {
              return (
                <Tr key={`tier-${row.tier.tierId}`}>
                  <Td colSpan={2} bg="gray.50" py={2}>
                    <HStack spacing={2}>
                      <TierBadge label={row.tier.tierName} />
                    </HStack>
                  </Td>
                </Tr>
              );
            }
            const t = row.task;
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
              </Tr>
            );
          })}
        </Tbody>
      </Table>
    </Box>
  );
};

export default SpendByTaskTypeTable;
