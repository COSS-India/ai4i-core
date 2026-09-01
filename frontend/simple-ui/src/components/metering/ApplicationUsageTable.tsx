import { ChevronRightIcon } from "@chakra-ui/icons";
import {
  Badge,
  Box,
  HStack,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
} from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import type { ApplicationUsageListItem } from "../../types/applicationUsage";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import { useMeteringTableSort } from "../../utils/meteringTableSort";
import { ThWithTip } from "../common/InfoTip";
import MeteringAsyncState from "./MeteringAsyncState";
import {
  AllocatedPctPill,
  ApplicationRemainingCell,
  ApplicationSpendCell,
} from "./ApplicationUsageCells";
import { TenantAvatar } from "./UsageSpendCells";
import SortableTh from "./SortableTh";

interface ApplicationUsageTableProps {
  applications: ApplicationUsageListItem[];
  isLoading: boolean;
  errorMessage: string | null;
  emptyMessage: string;
  currency?: string;
  onApplicationClick: (row: ApplicationUsageListItem) => void;
}

const thSx = { fontSize: "11.5px", letterSpacing: "0.05em", color: "gray.500" } as const;
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
  const sortAccessors = useMemo(
    () => ({
      name: (row: ApplicationUsageListItem) => row.name,
      domain: (row: ApplicationUsageListItem) => row.domain ?? "",
      allocated: (row: ApplicationUsageListItem) => row.allocatedBudget.amount,
      remaining: (row: ApplicationUsageListItem) => row.remainingBudget.amount,
    }),
    [],
  );

  const { sortedRows, sortKey, sortDirection, toggleSort } = useMeteringTableSort(
    applications,
    "name",
    sortAccessors,
  );

  return (
    <MeteringAsyncState
      isLoading={isLoading}
      isEmpty={!isLoading && applications.length === 0}
      errorMessage={errorMessage}
      emptyMessage={emptyMessage}
    >
      <Box
        overflowX="auto"
        mt={1}
        borderWidth="1px"
        borderColor="gray.300"
        borderRadius="14px"
        bg="white"
      >
        <Table size="sm" variant="simple" sx={{ "th, td": { verticalAlign: "middle" } }}>
          <Thead bg="#FAFBFD">
            <Tr>
              <SortableTh
                sortKey="name"
                activeSortKey={sortKey}
                sortDirection={sortDirection}
                onSort={toggleSort}
                w="24%"
                sx={thSx}
              >
                {cols.APPLICATION}
              </SortableTh>
              <SortableTh
                sortKey="domain"
                activeSortKey={sortKey}
                sortDirection={sortDirection}
                onSort={toggleSort}
                w="12%"
                sx={thSx}
              >
                {cols.DOMAIN}
              </SortableTh>
              <SortableTh
                sortKey="allocated"
                activeSortKey={sortKey}
                sortDirection={sortDirection}
                onSort={toggleSort}
                message={tips.ALLOCATED_COL}
                w="18%"
                sx={thSx}
              >
                {cols.ALLOCATED}
              </SortableTh>
              <ThWithTip message={tips.SPEND_COL} w="22%" sx={thSx}>
                {cols.SPEND}
              </ThWithTip>
              <SortableTh
                sortKey="remaining"
                activeSortKey={sortKey}
                sortDirection={sortDirection}
                onSort={toggleSort}
                message={tips.REMAINING_COL}
                w="16%"
                sx={thSx}
              >
                {cols.REMAINING}
              </SortableTh>
              <Th w="4%" borderBottomWidth="1px" sx={thSx} />
            </Tr>
          </Thead>
          <Tbody>
            {sortedRows.map((row) => {
              const limit = row.allocatedBudget.amount;
              const spent = row.spendBudget.amount;
              const remaining = row.remainingBudget.amount;
              const hasBudget = limit > 0;
              const pctUsed = hasBudget ? (spent / limit) * 100 : 0;

              return (
                <Tr
                  key={row.applicationId}
                  role="button"
                  tabIndex={0}
                  aria-label={`View spend details for ${row.name}`}
                  _hover={{ bg: "#FAFBFE", cursor: "pointer", "& .row-chevron": { color: "blue.500" } }}
                  onClick={() => onApplicationClick(row)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onApplicationClick(row);
                    }
                  }}
                >
                  <Td py={4}>
                    <HStack spacing="11px">
                      <TenantAvatar name={row.name} />
                      <Text fontWeight="bold" fontSize="14px" color="gray.800">
                        {row.name}
                      </Text>
                    </HStack>
                  </Td>
                  <Td py={4}>
                    <Badge
                      variant="subtle"
                      colorScheme="gray"
                      fontSize="11px"
                      textTransform="none"
                    >
                      {row.domain || "—"}
                    </Badge>
                  </Td>
                  <Td py={4}>
                    {hasBudget ? (
                      <Text fontSize="14px" fontWeight="bold" color="gray.800">
                        {formatSpendMoney(limit, currency)}
                        <AllocatedPctPill pct={row.allocatedBudget.percentage} />
                      </Text>
                    ) : (
                      <Text fontSize="12.5px" color="gray.500" fontStyle="italic">
                        {cols.NO_BUDGET}
                      </Text>
                    )}
                  </Td>
                  <Td py={4}>
                    <ApplicationSpendCell
                      spent={spent}
                      remaining={remaining}
                      pctUsed={pctUsed}
                      currency={currency}
                      hasBudget={hasBudget}
                      noBudgetLabel={cols.NO_BUDGET}
                    />
                  </Td>
                  <Td py={4}>
                    <ApplicationRemainingCell
                      remaining={remaining}
                      pctOfAllocation={row.remainingBudget.percentage}
                      currency={currency}
                      hasBudget={hasBudget}
                      ofAllocationLabel={cols.REMAINING_OF_ALLOCATION}
                    />
                  </Td>
                  <Td py={4} textAlign="right">
                    <ChevronRightIcon className="row-chevron" boxSize={3.5} color="gray.300" />
                  </Td>
                </Tr>
              );
            })}
          </Tbody>
        </Table>
      </Box>
    </MeteringAsyncState>
  );
};

export default ApplicationUsageTable;
