import { ChevronRightIcon } from "@chakra-ui/icons";
import { HStack, IconButton, Text, VStack } from "@chakra-ui/react";
import React, { useCallback, useMemo, useState } from "react";
import { METERING } from "../../config/meteringConstants";
import type { TenantTierBreakdown, TierTaskTypeUsage } from "../../types/usageSpend";
import {
  formatBillingMonth,
  formatSpendMoneyExact,
  formatSpendUnitCompact,
  taskTypeColor,
} from "../../utils/usageSpendHelpers";
import DataTable, { type DataTableColumn } from "../common/table";
import { UsageSpendCostBreakdownRows } from "./UsageSpendCostBreakdownRows";
import { TaskTypeLabel, TierBadge, UsageCell } from "./UsageSpendCells";

type TaskUsageRow = {
  task: TierTaskTypeUsage;
  /** Set only when the institution used more than one tier in the period. */
  tierName?: string;
};

const taskRowKey = (row: TaskUsageRow) => `${row.tierName ?? ""}-${row.task.taskType}`;

/** LLM rows carry a cost breakdown and can be expanded to show it. */
const hasCostBreakdown = (row: TaskUsageRow) =>
  (row.task.periodUsage.breakdown?.length ?? 0) > 0;

/** "USAGE VS. QUOTA (OCT 2026)" — every quota is for the same, current billing month. */
function quotaColumnLabel(rows: TaskUsageRow[]): string {
  const copy = METERING.USAGE_SPEND;
  const billingMonth = rows.find((row) => row.task.quota)?.task.quota?.billingMonth;
  const month = billingMonth ? formatBillingMonth(billingMonth).toUpperCase() : copy.THIS_MONTH;
  return `${copy.USAGE_VS_QUOTA} (${month})`;
}

interface SpendByTaskTypeTableProps {
  tierBreakdown: TenantTierBreakdown[];
  currency?: string;
  emptyMessage?: string;
}

const SpendByTaskTypeTable: React.FC<SpendByTaskTypeTableProps> = ({
  tierBreakdown,
  currency = "INR",
  emptyMessage = METERING.EMPTY.PERIOD,
}) => {
  const copy = METERING.USAGE_SPEND;
  const multiTier = tierBreakdown.length > 1;
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggleRow = useCallback((key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const taskRows = useMemo<TaskUsageRow[]>(
    () =>
      tierBreakdown.flatMap((tier) =>
        (tier.taskTypes ?? []).map((t) => ({
          task: t,
          tierName: multiTier ? tier.tierName : undefined,
        })),
      ),
    [tierBreakdown, multiTier],
  );

  const columns = useMemo<DataTableColumn<TaskUsageRow>[]>(() => {
    const cols: DataTableColumn<TaskUsageRow>[] = [
      {
        id: "taskType",
        header: "Model Task Type",
        sortable: true,
        sortAccessor: (row) => row.task.taskType,
        width: multiTier ? "22%" : "28%",
        cell: (row, idx) => {
          const key = taskRowKey(row);
          const isOpen = expanded.has(key);
          return (
            <HStack spacing={1}>
              <IconButton
                aria-label={`${copy.TOGGLE_COST_BREAKDOWN} ${row.task.taskType}`}
                aria-expanded={isOpen}
                icon={<ChevronRightIcon />}
                size="xs"
                variant="ghost"
                visibility={hasCostBreakdown(row) ? "visible" : "hidden"}
                transform={isOpen ? "rotate(90deg)" : undefined}
                transition="transform 0.15s ease"
                onClick={() => toggleRow(key)}
              />
              <TaskTypeLabel
                taskType={row.task.taskType}
                color={taskTypeColor(row.task.taskType, idx)}
                fontSize="sm"
                fontWeight="semibold"
              />
            </HStack>
          );
        },
      },
    ];

    if (multiTier) {
      cols.push({
        id: "tier",
        header: "Tier",
        sortable: true,
        sortAccessor: (row) => row.tierName ?? "",
        width: "14%",
        cell: (row) => (row.tierName ? <TierBadge label={row.tierName} /> : null),
      });
    }

    cols.push(
      {
        id: "periodUsage",
        header: copy.USAGE_IN_PERIOD,
        sortable: true,
        sortAccessor: (row) => row.task.periodUsage.cost,
        hint: copy.TOOLTIPS.PERIOD_USAGE,
        width: multiTier ? "24%" : "28%",
        cell: (row) => {
          const { periodUsage, unit } = row.task;
          return (
            <VStack align="flex-start" spacing={0}>
              <Text fontSize="13px" fontWeight="semibold" color="gray.800">
                {formatSpendUnitCompact(periodUsage.units, unit)}
              </Text>
              <Text fontSize="12px" color="gray.500">
                {formatSpendMoneyExact(periodUsage.cost, currency)}
              </Text>
            </VStack>
          );
        },
      },
      {
        id: "quota",
        header: quotaColumnLabel(taskRows),
        sortable: true,
        sortAccessor: (row) => row.task.quota?.used ?? 0,
        hint: copy.TOOLTIPS.USAGE,
        width: multiTier ? "40%" : "44%",
        cell: (row) => {
          const { quota, unit } = row.task;
          if (!quota) {
            return (
              <Text fontSize="12px" color="gray.500">
                {copy.NO_QUOTA_THIS_MONTH}
              </Text>
            );
          }
          return (
            <UsageCell
              consumed={quota.used}
              quotaLimit={quota.limit}
              remaining={quota.remaining}
              percentage={quota.percentageUsed}
              unit={unit}
              compact
            />
          );
        },
      },
    );

    return cols;
  }, [copy, multiTier, taskRows, currency, expanded, toggleRow]);

  return (
    <DataTable
      columns={columns}
      rows={taskRows}
      rowKey={taskRowKey}
      defaultSortKey="periodUsage"
      defaultSortDirection="desc"
      isEmpty={taskRows.length === 0}
      emptyMessage={emptyMessage}
      asyncStateHeight="auto"
      borderRadius="md"
      theadBg="gray.50"
      cellPy={2}
      tableMinWidth="400px"
      containerMt={0}
      tableProps={{ sx: { tableLayout: "fixed" } }}
      renderAfterRow={(row) =>
        hasCostBreakdown(row) && expanded.has(taskRowKey(row)) ? (
          <UsageSpendCostBreakdownRows
            task={row.task}
            currency={currency}
            leadingColSpan={multiTier ? 2 : 1}
          />
        ) : null
      }
    />
  );
};

export default SpendByTaskTypeTable;
