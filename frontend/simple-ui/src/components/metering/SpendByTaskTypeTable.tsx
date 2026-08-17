import { Box, HStack, Table, Tbody, Td, Text, Thead, Tr } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import {
  aggregateTasks,
  formatSpendMoney,
  taskTypeColor,
  type AggregatedTaskUsage,
} from "../../utils/usageSpendHelpers";
import type { TenantTierBreakdown, TierTaskTypeUsage } from "../../types/usageSpend";
import { MeteringHeaderWithTip } from "./MeteringInfoTip";
import { TaskTypeLabel, TierBadge, UsageCell } from "./UsageSpendCells";

function quotaUsagePercentage(t: TierTaskTypeUsage | AggregatedTaskUsage): number {
  if ("percentage" in t && typeof t.percentage === "number") return t.percentage;
  const limit = t.quotaLimit ?? 0;
  if (limit <= 0) return 0;
  return (t.consumed / limit) * 100;
}

type SpendRow =
  | { kind: "tier"; tier: TenantTierBreakdown }
  | { kind: "task"; task: TierTaskTypeUsage | AggregatedTaskUsage; tierName?: string };

interface SpendByTaskTypeTableProps {
  /** Tier breakdown to render — pass a pre-filtered subset to narrow the table. */
  tierBreakdown: TenantTierBreakdown[];
  /** Denominator for each row's SHARE % — the tenant's overall (unfiltered) spend. */
  totalSpend: number;
  currency: string;
  emptyMessage?: string;
}

/**
 * Tier-grouped model-task-type spend table: one badge row per tier (when the
 * tenant has more than one), a row per task type with a usage bar, and a
 * Total row summing whatever is currently visible.
 */
const SpendByTaskTypeTable: React.FC<SpendByTaskTypeTableProps> = ({
  tierBreakdown,
  totalSpend,
  currency,
  emptyMessage = "No spend data for this period.",
}) => {
  const rows = useMemo<SpendRow[]>(() => {
    if (tierBreakdown.length > 1) {
      return tierBreakdown.flatMap((tier) => [
        { kind: "tier" as const, tier },
        ...(tier.taskTypes ?? []).map((t) => ({
          kind: "task" as const,
          task: t,
          tierName: tier.tierName,
        })),
      ]);
    }
    return aggregateTasks(tierBreakdown)
      .sort((a, b) => b.spend - a.spend)
      .map((t) => ({ kind: "task" as const, task: t }));
  }, [tierBreakdown]);

  const visibleSpend = useMemo(
    () => rows.reduce((s, r) => (r.kind === "task" ? s + r.task.spend : s), 0),
    [rows],
  );

  if (rows.length === 0) {
    return (
      <Text fontSize="sm" color="gray.400" py={8} textAlign="center">
        {emptyMessage}
      </Text>
    );
  }

  return (
    <Box overflowX="auto" borderWidth="1px" borderColor="gray.200" borderRadius="md">
      <Table size="sm" variant="simple">
        <Thead bg="gray.50">
          <Tr>
            <MeteringHeaderWithTip
              label="MODEL TASK TYPE"
              w="26%"
              sx={{ fontSize: "10.5px", letterSpacing: "0.04em", color: "gray.600" }}
            />
            <MeteringHeaderWithTip
              label="USAGE"
              tip={METERING.USAGE_SPEND.TOOLTIPS.USAGE}
              w="38%"
              sx={{ fontSize: "10.5px", letterSpacing: "0.04em", color: "gray.600" }}
            />
            <MeteringHeaderWithTip
              label="SPEND"
              tip={METERING.USAGE_SPEND.TOOLTIPS.SPEND}
              w="20%"
              sx={{ fontSize: "10.5px", letterSpacing: "0.04em", color: "gray.600" }}
            />
            <MeteringHeaderWithTip
              label="SHARE"
              tip={METERING.USAGE_SPEND.TOOLTIPS.SHARE}
              w="16%"
              sx={{ fontSize: "10.5px", letterSpacing: "0.04em", color: "gray.600" }}
            />
          </Tr>
        </Thead>
        <Tbody>
          {rows.map((row, idx) => {
            if (row.kind === "tier") {
              return (
                <Tr key={`tier-${row.tier.tierId}`}>
                  <Td colSpan={4} bg="gray.50" py={2}>
                    <HStack spacing={2}>
                      <TierBadge label={row.tier.tierName} />
                      <Text fontSize="10.5px" fontWeight="bold" color="gray.600">
                        {formatSpendMoney(row.tier.spend, currency)}
                      </Text>
                    </HStack>
                  </Td>
                </Tr>
              );
            }
            const t = row.task;
            const share = totalSpend > 0 ? ((t.spend / totalSpend) * 100).toFixed(1) : "0.0";
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
                <Td fontSize="sm">{formatSpendMoney(t.spend, currency)}</Td>
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
              {formatSpendMoney(visibleSpend, currency)}
            </Td>
            <Td fontWeight="bold" fontSize="sm">
              {totalSpend > 0 ? `${((visibleSpend / totalSpend) * 100).toFixed(0)}%` : "0%"}
            </Td>
          </Tr>
        </Tbody>
      </Table>
    </Box>
  );
};

export default SpendByTaskTypeTable;
