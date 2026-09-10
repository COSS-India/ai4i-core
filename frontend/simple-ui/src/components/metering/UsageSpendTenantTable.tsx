import { ChevronRightIcon } from "@chakra-ui/icons";
import { HStack, IconButton, Text } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import {
  USAGE_SPEND_ACCENT,
  aggregateTasks,
  formatSpendMoney,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageItem } from "../../types/usageSpend";
import DataTable, { type DataTableColumn } from "../common/table";
import { BudgetCell, TenantAvatar, TierBadge } from "./UsageSpendCells";
import { UsageSpendExpandRows } from "./UsageSpendExpandRows";

interface UsageSpendTenantTableProps {
  tenants: TenantUsageItem[];
  isLoading: boolean;
  errorMessage: string | null;
  emptyMessage: string;
  expanded: Set<string>;
  onToggleExpand: (tenantId: string) => void;
  onTenantClick: (row: TenantUsageItem) => void;
}

const COLUMN_WIDTHS = {
  institution: "26%",
  tier: "12%",
  allocatedBudget: "18%",
  budget: "24%",
  taskTypes: "20%",
} as const;

const UsageSpendTenantTable: React.FC<UsageSpendTenantTableProps> = ({
  tenants,
  isLoading,
  errorMessage,
  emptyMessage,
  expanded,
  onToggleExpand,
  onTenantClick,
}) => {
  const tips = METERING.USAGE_SPEND.TOOLTIPS;

  const columns = useMemo<DataTableColumn<TenantUsageItem>[]>(
    () => [
      {
        id: "tenantName",
        header: "Institution",
        sortable: true,
        sortAccessor: (row) => row.tenantName,
        width: COLUMN_WIDTHS.institution,
        cell: (row) => {
          const tiers = row.tierBreakdown ?? [];
          const canExpand = tiers.length > 1;
          const isOpen = expanded.has(row.tenantId);
          return (
            <HStack spacing="10px">
              <IconButton
                aria-label={`Toggle tier breakdown for ${row.tenantName}`}
                icon={<ChevronRightIcon />}
                size="xs"
                variant="ghost"
                visibility={canExpand ? "visible" : "hidden"}
                transform={isOpen ? "rotate(90deg)" : undefined}
                transition="transform 0.15s ease"
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleExpand(row.tenantId);
                }}
              />
              <TenantAvatar name={row.tenantName} />
              <Text
                as="button"
                fontSize="13px"
                color={USAGE_SPEND_ACCENT}
                fontWeight="semibold"
                textAlign="left"
                onClick={(e) => {
                  e.stopPropagation();
                  onTenantClick(row);
                }}
              >
                {row.tenantName}
              </Text>
            </HStack>
          );
        },
      },
      {
        id: "tier",
        header: "Tier",
        sortable: true,
        sortAccessor: (row) => row.tier,
        width: COLUMN_WIDTHS.tier,
        cell: (row) => <TierBadge label={row.tier} />,
      },
      {
        id: "budgetLimit",
        header: "Allocated Budget (INR)",
        sortable: true,
        sortAccessor: (row) => row.budget?.limit ?? 0,
        hint: tips.ALLOCATED_BUDGET,
        width: COLUMN_WIDTHS.allocatedBudget,
        cell: (row) => (
          <Text fontWeight="semibold" fontSize="13px">
            {formatSpendMoney(row.budget?.limit ?? 0, row.currency)}
          </Text>
        ),
      },
      {
        id: "budgetSpent",
        header: "Budget",
        sortable: true,
        sortAccessor: (row) => row.budget?.spent ?? 0,
        hint: tips.BUDGET,
        width: COLUMN_WIDTHS.budget,
        cell: (row) =>
          row.budget ? (
            <BudgetCell {...row.budget} currency={row.currency} layout="topRight" />
          ) : (
            <Text fontSize="12px" color="gray.500">
              —
            </Text>
          ),
      },
      {
        id: "taskTypeCount",
        header: METERING.USAGE_SPEND.TABLE_TASK_TYPES,
        sortable: true,
        sortAccessor: (row) =>
          row.usage?.taskTypeCount ?? aggregateTasks(row.tierBreakdown ?? []).length,
        hint: tips.TASK_TYPES,
        width: COLUMN_WIDTHS.taskTypes,
        cell: (row) => {
          const taskCount =
            row.usage?.taskTypeCount ?? aggregateTasks(row.tierBreakdown ?? []).length;
          if (taskCount === 0) {
            return (
              <Text fontSize="12px" color="gray.500">
                Not used this period
              </Text>
            );
          }
          return (
            <HStack
              as="button"
              spacing={1.5}
              color={USAGE_SPEND_ACCENT}
              fontSize="13px"
              fontWeight="semibold"
              onClick={(e) => {
                e.stopPropagation();
                onTenantClick(row);
              }}
            >
              <Text>
                {taskCount} task type{taskCount === 1 ? "" : "s"}
              </Text>
              <ChevronRightIcon boxSize={3.5} />
            </HStack>
          );
        },
      },
    ],
    [expanded, onTenantClick, onToggleExpand, tips],
  );

  return (
    <DataTable
      columns={columns}
      rows={tenants}
      rowKey={(row) => row.tenantId}
      defaultSortKey="budgetSpent"
      defaultSortDirection="desc"
      isLoading={isLoading}
      isEmpty={!isLoading && tenants.length === 0}
      errorMessage={errorMessage}
      emptyMessage={emptyMessage}
      borderRadius="12px"
      theadBg="gray.50"
      containerMt={0}
      renderAfterRow={(row) => {
        const canExpand = (row.tierBreakdown ?? []).length > 1;
        if (!canExpand || !expanded.has(row.tenantId)) return null;
        return <UsageSpendExpandRows row={row} trailingColSpan={1} />;
      }}
    />
  );
};

export default UsageSpendTenantTable;
