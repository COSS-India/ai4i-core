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
import React from "react";
import { METERING } from "../../config/meteringConstants";
import {
  USAGE_SPEND_ACCENT,
  aggregateTasks,
  formatSpendMoney,
  formatSpendUnit,
  hasPopulatedQuotaUsage,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageItem } from "../../types/usageSpend";
import MeteringAsyncState from "./MeteringAsyncState";
import { ThWithTip } from "../common/InfoTip";
import { BudgetCell, TenantAvatar, TierBadge, UsageCell } from "./UsageSpendCells";
import { UsageSpendExpandRows } from "./UsageSpendExpandRows";

interface UsageSpendTenantTableProps {
  tenants: TenantUsageItem[];
  isLoading: boolean;
  errorMessage: string | null;
  emptyMessage: string;
  filterTaskType: string;
  /**
   * Token usage is only meaningful for a single task type, so the column is
   * hidden while the task-type filter is on "All" (drill-down stays available
   * via the row chevron and the institution name).
   */
  showTokenUsage: boolean;
  sortOrder: "asc" | "desc";
  expanded: Set<string>;
  onToggleSort: () => void;
  onToggleExpand: (tenantId: string) => void;
  onTenantClick: (row: TenantUsageItem) => void;
}

const thSx = { fontSize: "11px", letterSpacing: "0.04em", color: "gray.600" } as const;

/**
 * Column widths for each layout, so the table still fills the container either
 * way. Each layout lists every column it renders and must sum to 100%.
 */
const COLUMN_WIDTHS = {
  withTokenUsage: {
    institution: "18%",
    tier: "8%",
    allocatedBudget: "14%",
    budget: "20%",
    allocatedTokens: "14%",
    tokenUsage: "26%",
  },
  withoutTokenUsage: {
    institution: "24%",
    tier: "12%",
    allocatedBudget: "18%",
    budget: "26%",
    allocatedTokens: "20%",
  },
} as const;

function TenantUsageColumn({
  row,
  taskCount,
  showBar,
  multiTiers,
  tiersCount,
  isOpen,
  onToggleExpand,
  onTenantClick,
}: Readonly<{
  row: TenantUsageItem;
  taskCount: number;
  showBar: boolean;
  multiTiers: boolean;
  tiersCount: number;
  isOpen: boolean;
  onToggleExpand: (tenantId: string) => void;
  onTenantClick: (row: TenantUsageItem) => void;
}>) {
  if (taskCount === 0) {
    return <Text fontSize="12px" color="gray.500">Not used this period</Text>;
  }

  if (showBar) {
    const consumed = row.usage.consumed ?? 0;
    return (
      <UsageCell
        consumed={consumed}
        quotaLimit={row.usage.quotaLimit}
        remaining={row.usage.remaining}
        percentage={row.usage.percentage}
        unit={row.usage.unit ?? ""}
        layout="topRight"
      />
    );
  }

  if (multiTiers) {
    return (
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
        <Text>{tiersCount} tiers</Text>
        <ChevronDownIcon
          boxSize={3.5}
          transform={isOpen ? "rotate(180deg)" : undefined}
          transition="transform 0.15s ease"
        />
      </HStack>
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
      <Text>{taskCount} task type{taskCount === 1 ? "" : "s"}</Text>
      <ChevronRightIcon boxSize={3.5} />
    </HStack>
  );
}

const UsageSpendTenantTable: React.FC<UsageSpendTenantTableProps> = ({
  tenants,
  isLoading,
  errorMessage,
  emptyMessage,
  filterTaskType,
  showTokenUsage,
  sortOrder,
  expanded,
  onToggleSort,
  onToggleExpand,
  onTenantClick,
}) => {
  const widths = showTokenUsage
    ? COLUMN_WIDTHS.withTokenUsage
    : COLUMN_WIDTHS.withoutTokenUsage;
  const tips = METERING.USAGE_SPEND.TOOLTIPS;

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
            <ThWithTip w={widths.institution} sx={thSx}>
              INSTITUTION
            </ThWithTip>
            <ThWithTip w={widths.tier} sx={thSx}>
              TIER
            </ThWithTip>
            <ThWithTip
              message={tips.ALLOCATED_BUDGET}
              w={widths.allocatedBudget}
              sx={thSx}
            >
              ALLOCATED BUDGET (INR)
            </ThWithTip>
            <ThWithTip
              message={tips.BUDGET}
              w={widths.budget}
              sx={thSx}
              cursor="pointer"
              userSelect="none"
              onClick={onToggleSort}
            >
              <Text as="span">
                BUDGET{" "}
                <Text as="span" fontSize="10px">
                  {sortOrder === "desc" ? "↓" : "↑"}
                </Text>
              </Text>
            </ThWithTip>
            <ThWithTip
              message={tips.ALLOCATED_TOKENS}
              w={widths.allocatedTokens}
              sx={thSx}
            >
              ALLOCATED TOKENS
            </ThWithTip>
            {showTokenUsage ? (
              <ThWithTip
                message={tips.TOKEN_USAGE}
                w={COLUMN_WIDTHS.withTokenUsage.tokenUsage}
                sx={thSx}
              >
                TOKEN USAGE
              </ThWithTip>
            ) : null}
          </Tr>
        </Thead>
        <Tbody>
          {tenants.map((row) => {
            const isOpen = expanded.has(row.tenantId);
            const tiers = row.tierBreakdown ?? [];
            const taskCount = row.usage?.taskTypeCount ?? aggregateTasks(tiers).length;
            const multiTiers = tiers.length > 1;
            const canExpand = !filterTaskType && multiTiers;
            const showBar =
              taskCount > 0 && hasPopulatedQuotaUsage(row.usage) && Boolean(filterTaskType);

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
                    <Text fontWeight="semibold" fontSize="13px">
                      {hasPopulatedQuotaUsage(row.usage) && row.usage.quotaLimit != null
                        ? formatSpendUnit(row.usage.quotaLimit, row.usage.unit ?? "tokens")
                        : "—"}
                    </Text>
                  </Td>
                  {showTokenUsage ? (
                    <Td>
                      <TenantUsageColumn
                        row={row}
                        taskCount={taskCount}
                        showBar={showBar}
                        multiTiers={multiTiers}
                        tiersCount={tiers.length}
                        isOpen={isOpen}
                        onToggleExpand={onToggleExpand}
                        onTenantClick={onTenantClick}
                      />
                    </Td>
                  ) : null}
                </Tr>
                {isOpen && canExpand ? (
                  <UsageSpendExpandRows row={row} trailingColSpan={showTokenUsage ? 2 : 1} />
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
