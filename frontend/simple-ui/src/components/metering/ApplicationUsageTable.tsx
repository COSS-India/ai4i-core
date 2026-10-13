import { Badge, HStack, Text } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import type { ApplicationUsageListItem } from "../../types/applicationUsage";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import DataTable, { type DataTableColumn } from "../common/table";
import {
  AllocatedPctPill,
  ApplicationRemainingCell,
  ApplicationSpendCell,
  PeriodSpendCell,
} from "./ApplicationUsageCells";
import { TenantAvatar } from "./UsageSpendCells";

interface ApplicationUsageTableProps {
  applications: ApplicationUsageListItem[];
  isLoading: boolean;
  errorMessage: string | null;
  emptyMessage: string;
  currency?: string;
  onApplicationClick: (row: ApplicationUsageListItem) => void;
}

const tips = METERING.APPLICATION_USAGE.TOOLTIPS;
const cols = METERING.APPLICATION_USAGE.TABLE;

const ApplicationUsageTable: React.FC<ApplicationUsageTableProps> = ({
  applications,
  isLoading,
  errorMessage,
  emptyMessage,
  currency = "INR",
  onApplicationClick,
}) => {
  const columns = useMemo((): DataTableColumn<ApplicationUsageListItem>[] => {
    return [
      {
        id: "name",
        header: cols.APPLICATION,
        sortable: true,
        sortAccessor: (row) => row.name,
        width: "22%",
        cell: (row) => (
          <HStack spacing="11px">
            <TenantAvatar name={row.name} />
            <Text fontWeight="bold" fontSize="14px" color="gray.800">
              {row.name}
            </Text>
          </HStack>
        ),
      },
      {
        id: "domain",
        header: cols.DOMAIN,
        sortable: true,
        sortAccessor: (row) => row.domain ?? "",
        width: "10%",
        cell: (row) => (
          <Badge variant="subtle" colorScheme="gray" fontSize="11px" textTransform="none">
            {row.domain || "—"}
          </Badge>
        ),
      },
      {
        id: "allocated",
        header: cols.ALLOCATED,
        tip: tips.ALLOCATED_COL,
        sortable: true,
        sortAccessor: (row) => row.allocatedBudget.amount,
        width: "16%",
        cell: (row) => {
          const limit = row.allocatedBudget.amount;
          if (limit <= 0) {
            return (
              <Text fontSize="12.5px" color="gray.500" fontStyle="italic">
                {cols.NO_BUDGET}
              </Text>
            );
          }
          return (
            <Text fontSize="14px" fontWeight="bold" color="gray.800">
              {formatSpendMoney(limit, currency)}
              <AllocatedPctPill pct={row.allocatedBudget.percentage} />
            </Text>
          );
        },
      },
      {
        id: "periodSpend",
        header: cols.PERIOD_SPEND,
        tip: tips.PERIOD_SPEND_COL,
        sortable: true,
        sortAccessor: (row) => row.periodSpend.amount,
        width: "14%",
        cell: (row) => (
          <PeriodSpendCell
            amount={row.periodSpend.amount}
            percentage={row.periodSpend.percentage}
            currency={currency}
            hasBudget={row.allocatedBudget.amount > 0}
            ofAllocationLabel={cols.PERIOD_OF_ALLOCATION}
          />
        ),
      },
      {
        id: "spend",
        header: cols.SPEND,
        tip: tips.SPEND_COL,
        sortable: true,
        sortAccessor: (row) => row.spendBudget.amount,
        width: "22%",
        cell: (row) => {
          const limit = row.allocatedBudget.amount;
          const spent = row.spendBudget.amount;
          const remaining = row.remainingBudget.amount;
          const hasBudget = limit > 0;
          const pctUsed = hasBudget ? (spent / limit) * 100 : 0;
          return (
            <ApplicationSpendCell
              spent={spent}
              remaining={remaining}
              pctUsed={pctUsed}
              currency={currency}
              hasBudget={hasBudget}
              noBudgetLabel={cols.NO_BUDGET}
            />
          );
        },
      },
      {
        id: "remaining",
        header: cols.REMAINING,
        tip: tips.REMAINING_COL,
        sortable: true,
        sortAccessor: (row) => row.remainingBudget.amount,
        width: "16%",
        cell: (row) => {
          const limit = row.allocatedBudget.amount;
          const hasBudget = limit > 0;
          return (
            <ApplicationRemainingCell
              remaining={row.remainingBudget.amount}
              pctOfAllocation={row.remainingBudget.percentage}
              currency={currency}
              hasBudget={hasBudget}
              ofAllocationLabel={cols.REMAINING_OF_ALLOCATION}
            />
          );
        },
      },
    ];
  }, [currency]);

  return (
    <DataTable
      columns={columns}
      rows={applications}
      rowKey={(row) => row.applicationId}
      defaultSortKey="periodSpend"
      defaultSortDirection="desc"
      isLoading={isLoading}
      isEmpty={!isLoading && applications.length === 0}
      errorMessage={errorMessage}
      emptyMessage={emptyMessage}
      onRowClick={onApplicationClick}
      rowAriaLabel={(row) => `View spend details for ${row.name}`}
      showRowChevron
    />
  );
};

export default ApplicationUsageTable;
