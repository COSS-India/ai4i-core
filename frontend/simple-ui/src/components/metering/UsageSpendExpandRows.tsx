import { Box, HStack, Td, Text, Tr, VStack } from "@chakra-ui/react";
import React from "react";
import {
  USAGE_SPEND_ACCENT,
  aggregateTasks,
  formatSpendMoney,
} from "../../utils/usageSpendHelpers";
import type { TenantTierBreakdown, TenantUsageItem } from "../../types/usageSpend";
import { TaskTypeLabel, TierBadge, UsageCell } from "./UsageSpendCells";

const childTd = { borderColor: "gray.100" } as const;

function TierUsageCell({
  tier,
  taskColorByType,
}: {
  tier: TenantTierBreakdown;
  taskColorByType: Map<string, string>;
}) {
  const tasks = tier.taskTypes ?? [];
  if (tasks.length === 0) {
    return <Text fontSize="12px" color="gray.500">Not used this period</Text>;
  }
  if (tasks.length === 1) return <UsageCell {...tasks[0]} />;
  return (
    <VStack align="stretch" spacing={2} py={1}>
      {tasks.map((t) => (
        <HStack key={t.taskType} spacing={3}>
          <Box minW="90px">
            <TaskTypeLabel
              taskType={t.taskType}
              color={taskColorByType.get(t.taskType) ?? USAGE_SPEND_ACCENT}
              fontSize="12px"
            />
          </Box>
          <UsageCell {...t} />
        </HStack>
      ))}
    </VStack>
  );
}

/** Column-aligned expand rows: multi-tier or multi-task-type under a tenant. */
export function UsageSpendExpandRows({
  row,
  multiTiers,
  taskColorByType,
}: {
  row: TenantUsageItem;
  multiTiers: boolean;
  taskColorByType: Map<string, string>;
}) {
  const tiers = row.tierBreakdown ?? [];

  if (multiTiers) {
    return (
      <>
        {tiers.map((tier) => (
          <Tr key={`${row.tenantId}-${tier.tierId}`} bg="gray.50">
            <Td pl={12} {...childTd} />
            <Td {...childTd}><TierBadge label={tier.tierName} /></Td>
            <Td {...childTd}>
              <Text fontWeight="bold" fontSize="13px">
                {formatSpendMoney(tier.spend, row.currency)}
              </Text>
            </Td>
            <Td {...childTd} />
            <Td {...childTd}>
              <TierUsageCell tier={tier} taskColorByType={taskColorByType} />
            </Td>
          </Tr>
        ))}
      </>
    );
  }

  const tasks = [...aggregateTasks(tiers)].sort(
    (a, b) =>
      b.consumed / Math.max(b.quotaLimit, 1) - a.consumed / Math.max(a.quotaLimit, 1),
  );

  return (
    <>
      {tasks.map((t) => (
        <Tr key={`${row.tenantId}-${t.taskType}`} bg="gray.50">
          <Td pl={12} {...childTd}>
            <TaskTypeLabel
              taskType={t.taskType}
              color={taskColorByType.get(t.taskType) ?? USAGE_SPEND_ACCENT}
              fontSize="12.5px"
            />
          </Td>
          <Td {...childTd} />
          <Td {...childTd}>
            <Text fontWeight="bold" fontSize="13px">
              {formatSpendMoney(t.spend, row.currency)}
            </Text>
          </Td>
          <Td {...childTd} />
          <Td {...childTd}>
            <UsageCell
              {...t}
              percentage={t.quotaLimit > 0 ? (t.consumed / t.quotaLimit) * 100 : 0}
            />
          </Td>
        </Tr>
      ))}
    </>
  );
}
