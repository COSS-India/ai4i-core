import { Box, Flex, Text, VStack } from "@chakra-ui/react";
import React from "react";
import {
  USAGE_SPEND_ACCENT,
  aggregateTasks,
  formatSpendMoney,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageItem } from "../../types/usageSpend";
import { TaskTypeLabel, TierBadge, UsageCell } from "./UsageSpendCells";

interface UsageSpendExpandRowProps {
  row: TenantUsageItem;
  taskColorByType: Map<string, string>;
}

const UsageSpendExpandRow: React.FC<UsageSpendExpandRowProps> = ({ row, taskColorByType }) => {
  const tiers = row.tierBreakdown ?? [];
  const hasMultiTier = tiers.length > 1;

  if (hasMultiTier) {
    return (
      <VStack align="stretch" spacing={0} maxH="236px" overflowY="auto" py={1}>
        {tiers.map((tier) => (
          <Box
            key={tier.tierId}
            px={4}
            py="10px"
            borderTopWidth="1px"
            borderColor="gray.200"
            _first={{ borderTopWidth: 0 }}
          >
            <Flex align="center" gap={3} mb={2}>
              <TierBadge label={tier.tierName} />
              <Text ml="auto" fontWeight="bold" fontSize="13px">
                {formatSpendMoney(tier.spend, row.currency)}
              </Text>
            </Flex>
            {(tier.taskTypes ?? []).map((t) => (
              <Box
                key={`${tier.tierId}-${t.taskType}`}
                display="grid"
                gridTemplateColumns="26% 48% 26%"
                alignItems="center"
                py="7px"
                gap="10px"
              >
                <TaskTypeLabel
                  taskType={t.taskType}
                  color={taskColorByType.get(t.taskType) ?? USAGE_SPEND_ACCENT}
                  fontSize="12.5px"
                />
                <UsageCell
                  consumed={t.consumed}
                  quotaLimit={t.quotaLimit}
                  remaining={t.remaining}
                  percentage={t.percentage}
                  unit={t.unit}
                />
                <Text fontWeight="semibold" fontSize="12.5px" textAlign="right">
                  {formatSpendMoney(t.spend, row.currency)}
                </Text>
              </Box>
            ))}
          </Box>
        ))}
      </VStack>
    );
  }

  const tasks = [...aggregateTasks(tiers)].sort(
    (a, b) => b.consumed / Math.max(b.quotaLimit, 1) - a.consumed / Math.max(a.quotaLimit, 1),
  );

  return (
    <VStack align="stretch" spacing={0} maxH="236px" overflowY="auto" py={1}>
      {tasks.map((t) => (
        <Box
          key={t.taskType}
          display="grid"
          gridTemplateColumns={{ base: "1fr", md: "32% 14% 22% 32%" }}
          alignItems="center"
          px={4}
          py={2}
          gap={3}
        >
          <Box pl={{ base: 0, md: "36px" }}>
            <TaskTypeLabel
              taskType={t.taskType}
              color={taskColorByType.get(t.taskType) ?? USAGE_SPEND_ACCENT}
            />
          </Box>
          <Text fontWeight="bold" fontSize="13px">
            {formatSpendMoney(t.spend, row.currency)}
          </Text>
          <Box />
          <UsageCell
            consumed={t.consumed}
            quotaLimit={t.quotaLimit}
            remaining={t.remaining}
            percentage={t.quotaLimit > 0 ? (t.consumed / t.quotaLimit) * 100 : 0}
            unit={t.unit}
          />
        </Box>
      ))}
    </VStack>
  );
};

export default UsageSpendExpandRow;
