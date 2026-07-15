import { ChevronDownIcon, ChevronRightIcon } from "@chakra-ui/icons";
import {
  Box,
  HStack,
  IconButton,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
} from "@chakra-ui/react";
import React from "react";
import {
  USAGE_SPEND_ACCENT,
  aggregateTasks,
  formatSpendMoney,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageItem } from "../../types/usageSpend";
import MeteringAsyncState from "./MeteringAsyncState";
import { BudgetCell, TenantAvatar, TierBadge, UsageCell } from "./UsageSpendCells";
import UsageSpendExpandRow from "./UsageSpendExpandRow";

interface UsageSpendTenantTableProps {
  tenants: TenantUsageItem[];
  isLoading: boolean;
  errorMessage: string | null;
  emptyMessage: string;
  filterTaskType: string;
  sortOrder: "asc" | "desc";
  expanded: Set<string>;
  taskColorByType: Map<string, string>;
  onToggleSort: () => void;
  onToggleExpand: (tenantId: string) => void;
  onTenantClick: (row: TenantUsageItem) => void;
}

const UsageSpendTenantTable: React.FC<UsageSpendTenantTableProps> = ({
  tenants,
  isLoading,
  errorMessage,
  emptyMessage,
  filterTaskType,
  sortOrder,
  expanded,
  taskColorByType,
  onToggleSort,
  onToggleExpand,
  onTenantClick,
}) => (
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
              onClick={onToggleSort}
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
                  color={USAGE_SPEND_ACCENT}
                  fontSize="13px"
                  fontWeight="semibold"
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleExpand(row.tenantId);
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
                  <Td>
                    <TierBadge label={row.tier} />
                  </Td>
                  <Td>
                    <Text fontWeight="bold" fontSize="14px">
                      {formatSpendMoney(row.spend, row.currency)}
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
                      <UsageSpendExpandRow row={row} taskColorByType={taskColorByType} />
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
);

export default UsageSpendTenantTable;
