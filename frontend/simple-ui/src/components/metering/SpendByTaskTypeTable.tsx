import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import type { TenantTierBreakdown, TierTaskTypeUsage } from "../../types/usageSpend";
import {
  aggregateTasks,
  taskTypeColor,
  type AggregatedTaskUsage,
} from "../../utils/usageSpendHelpers";
import DataTable, { type DataTableColumn } from "../common/table";
import { TaskTypeLabel, TierBadge, UsageCell } from "./UsageSpendCells";

function quotaUsagePercentage(t: TierTaskTypeUsage | AggregatedTaskUsage): number {
  const limit = t.quotaLimit ?? 0;
  if (limit <= 0) return 0;
  return (t.consumed / limit) * 100;
}

type TaskUsageRow = {
  task: TierTaskTypeUsage | AggregatedTaskUsage;
  tierName?: string;
};

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
          task: t,
          tierName: tier.tierName,
        })),
      );
    }
    return aggregateTasks(tierBreakdown).map((t) => ({ task: t }));
  }, [tierBreakdown, multiTier]);

  const columns = useMemo<DataTableColumn<TaskUsageRow>[]>(() => {
    const cols: DataTableColumn<TaskUsageRow>[] = [
      {
        id: "taskType",
        header: "Model Task Type",
        sortable: true,
        sortAccessor: (row) => row.task?.taskType ?? "",
        width: multiTier ? "28%" : "36%",
        cell: (row, idx) => {
          const t = row.task;
          if (!t) return null;
          return (
            <TaskTypeLabel
              taskType={t.taskType}
              color={taskTypeColor(t.taskType, idx)}
              fontSize="sm"
              fontWeight="semibold"
            />
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
        width: "16%",
        cell: (row) => (row.tierName ? <TierBadge label={row.tierName} /> : null),
      });
    }

    cols.push({
      id: "consumed",
      header: usageColumnLabel,
      sortable: true,
      sortAccessor: (row) => row.task?.consumed ?? 0,
      hint: METERING.USAGE_SPEND.TOOLTIPS.USAGE,
      width: multiTier ? "56%" : "64%",
      cell: (row) => {
        const t = row.task;
        if (!t) return null;
        return (
          <UsageCell
            consumed={t.consumed}
            quotaLimit={t.quotaLimit}
            remaining={t.remaining}
            percentage={quotaUsagePercentage(t)}
            unit={t.unit}
            compact
          />
        );
      },
    });

    return cols;
  }, [multiTier, usageColumnLabel]);

  return (
    <DataTable
      columns={columns}
      rows={taskRows}
      rowKey={(row) => `${row.tierName ?? ""}-${row.task?.taskType ?? "unknown"}`}
      defaultSortKey="consumed"
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
    />
  );
};

export default SpendByTaskTypeTable;
