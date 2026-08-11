import { Box, Flex, HStack, Select, Text, VStack } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import { formatModelTaskTypeLabel } from "../../config/constants";
import {
  filterTierBreakdown,
  formatSpendMoney,
  USAGE_SPEND_ACCENT,
  USAGE_SPEND_DANGER,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageItem } from "../../types/usageSpend";
import SpendByTaskTypeTable from "./SpendByTaskTypeTable";

interface TenantSpendPanelProps {
  detail: TenantUsageItem;
  currency: string;
  filterTierId: string;
  filterTaskType: string;
  onFilterTierChange: (tierId: string) => void;
  onFilterTaskTypeChange: (taskType: string) => void;
}

const SPEND_CARD_BG = "#eef3fb";

function TotalSpendBanner({
  detail,
  currency,
}: Readonly<{ detail: TenantUsageItem; currency: string }>) {
  const { limit, spent, remaining, percentageUsed } = detail.budget;
  const cur = detail.currency || currency;
  const pct = percentageUsed || (limit > 0 ? (spent / limit) * 100 : 0);
  const over = spent - limit;
  const fillPct = Math.min(Math.max(pct, 0), 100);

  return (
    <Box
      bg={SPEND_CARD_BG}
      borderRadius="12px"
      borderWidth="1px"
      borderColor="gray.200"
      p="22px 24px"
      w="full"
    >
      <Text
        fontSize="11px"
        fontWeight="semibold"
        letterSpacing="0.04em"
        color={USAGE_SPEND_ACCENT}
        mb={2}
      >
        TOTAL SPEND
      </Text>
      <Text fontSize="28px" fontWeight="bold" lineHeight="1" color="gray.800">
        {formatSpendMoney(spent, cur)}
      </Text>
      <Box mt={4} h="8px" borderRadius="4px" bg="blackAlpha.100" overflow="hidden">
        <Box
          h="100%"
          w={`${fillPct}%`}
          bg={over > 0 ? USAGE_SPEND_DANGER : USAGE_SPEND_ACCENT}
          borderRadius="4px"
        />
      </Box>
      <Flex
        mt="14px"
        pt="14px"
        borderTopWidth="1px"
        borderColor="gray.200"
        direction={{ base: "column", sm: "row" }}
        gap={{ base: "9px", sm: 6 }}
        justify="space-between"
        fontSize="12.5px"
        flexWrap="wrap"
      >
        <HStack spacing={1.5}>
          <Text color="gray.500">Budget used:</Text>
          <Text fontWeight="semibold" color="gray.800">{pct.toFixed(0)}%</Text>
        </HStack>
        <HStack spacing={1.5}>
          <Text color="gray.500">Limit:</Text>
          <Text fontWeight="semibold" color="gray.800">{formatSpendMoney(limit, cur)}</Text>
        </HStack>
        <HStack spacing={1.5}>
          <Text color="gray.500">{over > 0 ? "Over budget:" : "Remaining:"}</Text>
          <Text fontWeight="semibold" color={over > 0 ? USAGE_SPEND_DANGER : "gray.800"}>
            {over > 0 ? formatSpendMoney(over, cur) : formatSpendMoney(remaining, cur)}
          </Text>
        </HStack>
      </Flex>
    </Box>
  );
}

/**
 * Tenant admin's own Usage and Spend view: a full-width spend-vs-budget banner
 * followed by a tier-grouped model-task-type table, filterable client-side
 * since the single-tenant endpoint has no tier/task-type query params.
 */
const TenantSpendPanel: React.FC<TenantSpendPanelProps> = ({
  detail,
  currency,
  filterTierId,
  filterTaskType,
  onFilterTierChange,
  onFilterTaskTypeChange,
}) => {
  const tierBreakdown = detail.tierBreakdown ?? [];

  const taskTypeOptions = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    tierBreakdown.forEach((tier) =>
      (tier.taskTypes ?? []).forEach((t) => {
        const name = t.taskType.trim();
        if (name && !seen.has(name)) {
          seen.add(name);
          out.push(name);
        }
      }),
    );
    return out;
  }, [tierBreakdown]);

  const filteredBreakdown = useMemo(
    () => filterTierBreakdown(tierBreakdown, filterTierId, filterTaskType),
    [tierBreakdown, filterTierId, filterTaskType],
  );

  return (
    <VStack align="stretch" spacing={5}>
      <TotalSpendBanner detail={detail} currency={currency} />

      {tierBreakdown.length > 0 ? (
        <HStack spacing={3} flexWrap="wrap">
          <Select
            size="sm"
            w={{ base: "full", sm: "220px" }}
            value={filterTierId}
            onChange={(e) => onFilterTierChange(e.target.value)}
            borderRadius="8px"
            bg="white"
          >
            <option value="">Filter by tier · All tiers</option>
            {tierBreakdown.map((t) => (
              <option key={t.tierId} value={t.tierId}>
                {t.tierName}
              </option>
            ))}
          </Select>
          <Select
            size="sm"
            w={{ base: "full", sm: "260px" }}
            value={filterTaskType}
            onChange={(e) => onFilterTaskTypeChange(e.target.value)}
            borderRadius="8px"
            bg="white"
          >
            <option value="">Filter by model task type · All</option>
            {taskTypeOptions.map((t) => (
              <option key={t} value={t}>
                {formatModelTaskTypeLabel(t)}
              </option>
            ))}
          </Select>
        </HStack>
      ) : null}

      <Box bg="white" borderRadius="12px" borderWidth="1px" borderColor="gray.200" p="20px 24px">
        <Text fontSize="12px" letterSpacing="0.04em" color="gray.600" fontWeight="semibold" mb={4}>
          {METERING.USAGE_SPEND.SPEND_BY_TASK_TYPE}
        </Text>
        <SpendByTaskTypeTable
          tierBreakdown={filteredBreakdown}
          totalSpend={detail.spend}
          currency={currency}
          emptyMessage="No spend data matches the selected filters."
        />
      </Box>
    </VStack>
  );
};

export default TenantSpendPanel;
