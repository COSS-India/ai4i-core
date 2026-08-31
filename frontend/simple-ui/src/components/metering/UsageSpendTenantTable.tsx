import { ChevronDownIcon, ChevronRightIcon } from "@chakra-ui/icons";
import {
  Box,
  HStack,
  IconButton,
  Table,
  Tbody,
  Td,
  Text,
  Thead,
  Tr,
} from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import {
  USAGE_SPEND_ACCENT,
  aggregateTasks,
  formatSpendMoney,
  hasPopulatedQuotaUsage,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageItem } from "../../types/usageSpend";
import { useMeteringTableSort } from "../../utils/meteringTableSort";
import MeteringAsyncState from "./MeteringAsyncState";
import { ThWithTip } from "../common/InfoTip";
import { BudgetCell, TenantAvatar, TierBadge } from "./UsageSpendCells";
import { UsageSpendExpandRows } from "./UsageSpendExpandRows";
import SortableTh from "./SortableTh";

interface UsageSpendTenantTableProps {
  tenants: TenantUsageItem[];
  isLoading: boolean;
  errorMessage: string | null;
  emptyMessage: string;
  expanded: Set<string>;
  onToggleExpand: (tenantId: string) => void;
  onTenantClick: (row: TenantUsageItem) => void;
}

const thSx = { fontSize: "11px", letterSpacing: "0.04em", color: "gray.600" } as const;

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

  const sortAccessors = useMemo(
    () => ({
      tenantName: (row: TenantUsageItem) => row.tenantName,
      tier: (row: TenantUsageItem) => row.tier,
      budgetLimit: (row: TenantUsageItem) => row.budget.limit,
      budgetSpent: (row: TenantUsageItem) => row.budget.spent,
      taskTypeCount: (row: TenantUsageItem) =>
        row.usage?.taskTypeCount ?? aggregateTasks(row.tierBreakdown ?? []).length,
    }),
    [],
  );

  const { sortedRows, sortKey, sortDirection, toggleSort } = useMeteringTableSort(
    tenants,
    "budgetSpent",
    sortAccessors,
  );

  return (
  <MeteringAsyncState
    isLoading={isLoading}
    isEmpty={!isLoading && tenants.length === 0}
    errorMessage={errorMessage}
    emptyMessage={emptyMessage}
  >
    <Box overflowX="auto" borderWidth="1px" borderColor="gray.200" borderRadius="12px" bg="white">
      <Table size="sm" variant="simple" sx={{ "th, td": { verticalAlign: "middle" } }}>
        <Thead bg="gray.50">
          <Tr>
            <SortableTh
              sortKey="tenantName"
              activeSortKey={sortKey}
              sortDirection={sortDirection}
              onSort={toggleSort}
              w={COLUMN_WIDTHS.institution}
              sx={thSx}
            >
              INSTITUTION
            </SortableTh>
            <SortableTh
              sortKey="tier"
              activeSortKey={sortKey}
              sortDirection={sortDirection}
              onSort={toggleSort}
              w={COLUMN_WIDTHS.tier}
              sx={thSx}
            >
              TIER
            </SortableTh>
            <SortableTh
              sortKey="budgetLimit"
              activeSortKey={sortKey}
              sortDirection={sortDirection}
              onSort={toggleSort}
              message={tips.ALLOCATED_BUDGET}
              w={COLUMN_WIDTHS.allocatedBudget}
              sx={thSx}
            >
              ALLOCATED BUDGET (INR)
            </SortableTh>
            <SortableTh
              sortKey="budgetSpent"
              activeSortKey={sortKey}
              sortDirection={sortDirection}
              onSort={toggleSort}
              message={tips.BUDGET}
              w={COLUMN_WIDTHS.budget}
              sx={thSx}
            >
              BUDGET
            </SortableTh>
            <SortableTh
              sortKey="taskTypeCount"
              activeSortKey={sortKey}
              sortDirection={sortDirection}
              onSort={toggleSort}
              message={tips.TASK_TYPES}
              w={COLUMN_WIDTHS.taskTypes}
              sx={thSx}
            >
              {METERING.USAGE_SPEND.TABLE_TASK_TYPES}
            </SortableTh>
          </Tr>
        </Thead>
        <Tbody>
          {sortedRows.map((row) => {
            const isOpen = expanded.has(row.tenantId);
            const tiers = row.tierBreakdown ?? [];
            const taskCount =
              row.usage?.taskTypeCount ?? aggregateTasks(tiers).length;
            const multiTiers = tiers.length > 1;
            const canExpand = multiTiers;

            return (
              <React.Fragment key={row.tenantId}>
                <Tr _hover={{ bg: "gray.50" }}>
                  <Td>
                    <HStack spacing="10px">
                      <IconButton
                        aria-label={`Toggle tier breakdown for ${row.tenantName}`}
                        icon={<ChevronRightIcon />}
                        size="xs"
                        variant="ghost"
                        visibility={canExpand ? "visible" : "hidden"}
                        transform={isOpen ? "rotate(90deg)" : undefined}
                        transition="transform 0.15s ease"
                        onClick={() => onToggleExpand(row.tenantId)}
                      />
                      <TenantAvatar name={row.tenantName} />
                      <Text
                        as="button"
                        fontSize="13px"
                        color={USAGE_SPEND_ACCENT}
                        fontWeight="semibold"
                        textAlign="left"
                        onClick={() => onTenantClick(row)}
                      >
                        {row.tenantName}
                      </Text>
                    </HStack>
                  </Td>
                  <Td><TierBadge label={row.tier} /></Td>
                  <Td>
                    <Text fontWeight="semibold" fontSize="13px">
                      {formatSpendMoney(row.budget.limit, row.currency)}
                    </Text>
                  </Td>
                  <Td>
                    <BudgetCell {...row.budget} currency={row.currency} layout="topRight" />
                  </Td>
                  <Td>
                    {taskCount === 0 ? (
                      <Text fontSize="12px" color="gray.500">
                        Not used this period
                      </Text>
                    ) : (
                      <HStack
                        as="button"
                        spacing={1.5}
                        color={USAGE_SPEND_ACCENT}
                        fontSize="13px"
                        fontWeight="semibold"
                        onClick={() => onTenantClick(row)}
                      >
                        <Text>
                          {taskCount} task type{taskCount === 1 ? "" : "s"}
                        </Text>
                        <ChevronRightIcon boxSize={3.5} />
                      </HStack>
                    )}
                  </Td>
                </Tr>
                {isOpen && canExpand ? (
                  <UsageSpendExpandRows row={row} trailingColSpan={1} />
                ) : null}
              </React.Fragment>
            );
          })}
        </Tbody>
      </Table>
    </Box>
  </MeteringAsyncState>
  );
};

export default UsageSpendTenantTable;
