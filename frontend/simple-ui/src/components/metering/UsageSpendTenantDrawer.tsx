import {
  Box,
  Center,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerHeader,
  DrawerOverlay,
  FormControl,
  HStack,
  Select,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import {
  aggregateTasks,
  billingPeriodLabel,
  formatSpendMoney,
  taskTypeColor,
  type AggregatedTaskUsage,
  type BillingPeriodKey,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageDetail, TierTaskTypeUsage } from "../../types/usageSpend";
import { BudgetCell, TaskTypeLabel, TenantAvatar, TierBadge, UsageCell } from "./UsageSpendCells";

interface UsageSpendTenantDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  detail: TenantUsageDetail | null;
  isLoading: boolean;
  /** Value shown in the period selector (may be pending while loading). */
  periodKey: BillingPeriodKey;
  /** Period that `detail` was fetched for — used for the spend section label. */
  loadedPeriodKey: BillingPeriodKey;
  onPeriodChange: (periodKey: BillingPeriodKey) => void;
}

function quotaUsagePercentage(t: TierTaskTypeUsage | AggregatedTaskUsage): number {
  if ("percentage" in t && typeof t.percentage === "number") return t.percentage;
  const limit = t.quotaLimit ?? 0;
  if (limit <= 0) return 0;
  return (t.consumed / limit) * 100;
}

const UsageSpendTenantDrawer: React.FC<UsageSpendTenantDrawerProps> = ({
  isOpen,
  onClose,
  detail,
  isLoading,
  periodKey,
  loadedPeriodKey,
  onPeriodChange,
}) => {
  const taskRows = useMemo(() => {
    if (!detail) return [];
    const tiers = detail.tierBreakdown ?? [];
    if (tiers.length > 1) {
      return tiers.flatMap((tier) => [
        { kind: "tier" as const, tier },
        ...(tier.taskTypes ?? []).map((t) => ({
          kind: "task" as const,
          task: t,
          tierName: tier.tierName,
        })),
      ]);
    }
    return aggregateTasks(tiers)
      .sort((a, b) => b.spend - a.spend)
      .map((t) => ({ kind: "task" as const, task: t }));
  }, [detail]);

  const spend = detail?.spend ?? 0;
  const hasMultiTier = (detail?.tierBreakdown?.length ?? 0) > 1;
  const periodLabel = billingPeriodLabel(loadedPeriodKey);

  let body: React.ReactNode = null;
  if (isLoading && !detail) {
    body = (
      <Center py={12}>
        <Spinner color="blue.500" />
      </Center>
    );
  } else if (detail) {
    body = (
      <VStack align="stretch" spacing={5}>
        <HStack spacing="11px">
          <TenantAvatar name={detail.tenantName} size="md" />
          <Text fontSize="16px" fontWeight="bold">
            {detail.tenantName}
          </Text>
          <TierBadge label={detail.tier} />
        </HStack>

        <FormControl>
          <Text
            fontSize="11px"
            letterSpacing="0.04em"
            color="gray.600"
            fontWeight="semibold"
            mb={2}
          >
            {METERING.USAGE_SPEND.BILLING_PERIOD}
          </Text>
          <Select
            size="sm"
            value={periodKey}
            onChange={(e) => onPeriodChange(e.target.value as BillingPeriodKey)}
            borderRadius="8px"
            bg="white"
            maxW="220px"
            isDisabled={isLoading}
          >
            <option value="current">{METERING.USAGE_SPEND.CURRENT_MONTH}</option>
            <option value="last">{METERING.USAGE_SPEND.LAST_MONTH}</option>
          </Select>
        </FormControl>

        <Box>
          <Text fontSize="11px" letterSpacing="0.04em" color="gray.600" fontWeight="semibold" mb="10px">
            BUDGET
          </Text>
          <Box bg="gray.50" borderRadius="10px" p="16px 18px" opacity={isLoading ? 0.55 : 1}>
            <BudgetCell
              limit={detail.budget.limit}
              spent={detail.budget.spent}
              remaining={detail.budget.remaining}
              percentageUsed={detail.budget.percentageUsed}
              currency={detail.currency}
            />
          </Box>
        </Box>

        <Box position="relative" opacity={isLoading ? 0.55 : 1}>
          {isLoading ? (
            <Center position="absolute" inset={0} zIndex={1}>
              <Spinner color="blue.500" size="sm" />
            </Center>
          ) : null}
          <Text fontSize="11px" letterSpacing="0.04em" color="gray.600" fontWeight="semibold" mb="10px">
            SPEND BY MODEL TASK TYPE — {periodLabel}
          </Text>
          <Box overflowX="auto" borderWidth="1px" borderColor="gray.200" borderRadius="md">
            <Table size="sm" variant="simple">
              <Thead bg="gray.50">
                <Tr>
                  <Th fontSize="10.5px" letterSpacing="0.04em" color="gray.600" w="26%">
                    MODEL TASK TYPE
                  </Th>
                  <Th fontSize="10.5px" letterSpacing="0.04em" color="gray.600" w="38%">
                    USAGE
                  </Th>
                  <Th fontSize="10.5px" letterSpacing="0.04em" color="gray.600" w="20%">
                    SPEND
                  </Th>
                  <Th fontSize="10.5px" letterSpacing="0.04em" color="gray.600" w="16%">
                    SHARE
                  </Th>
                </Tr>
              </Thead>
              <Tbody>
                {taskRows.map((row, idx) => {
                  if (row.kind === "tier") {
                    return (
                      <Tr key={`tier-${row.tier.tierId}`}>
                        <Td colSpan={4} bg="gray.50" py={2}>
                          <HStack spacing={2}>
                            <TierBadge label={row.tier.tierName} />
                            <Text fontSize="10.5px" fontWeight="bold" color="gray.600">
                              {formatSpendMoney(row.tier.spend, detail.currency)}
                            </Text>
                          </HStack>
                        </Td>
                      </Tr>
                    );
                  }
                  const t = row.task;
                  const share = spend > 0 ? ((t.spend / spend) * 100).toFixed(1) : "0.0";
                  const color = taskTypeColor(t.taskType, idx);
                  return (
                    <Tr key={`${"tierName" in row ? row.tierName : ""}-${t.taskType}-${idx}`}>
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
                        />
                      </Td>
                      <Td fontSize="sm">{formatSpendMoney(t.spend, detail.currency)}</Td>
                      <Td fontSize="12.5px" color="gray.500">
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
                  <Td fontWeight="bold" fontSize="sm">
                    {formatSpendMoney(spend, detail.currency)}
                  </Td>
                  <Td fontWeight="bold" fontSize="sm">
                    100%
                  </Td>
                </Tr>
              </Tbody>
            </Table>
          </Box>
          {hasMultiTier ? (
            <Text fontSize="11.5px" color="gray.500" lineHeight="1.5" mt="10px">
              Grouped by tier since this tenant changed tier during the period — spend and usage
              above the group total are cumulative across all tiers.
            </Text>
          ) : null}
        </Box>
      </VStack>
    );
  }

  return (
    <Drawer isOpen={isOpen} placement="right" onClose={onClose} size="md">
      <DrawerOverlay bg="rgba(15,18,25,0.4)" />
      <DrawerContent maxW="640px">
        <DrawerCloseButton top={4} right={4} />
        <DrawerHeader fontSize="17px" fontWeight="bold" pb={2}>
          Tenant Spend Details
        </DrawerHeader>
        <DrawerBody pb={10}>{body}</DrawerBody>
      </DrawerContent>
    </Drawer>
  );
};

export default UsageSpendTenantDrawer;
