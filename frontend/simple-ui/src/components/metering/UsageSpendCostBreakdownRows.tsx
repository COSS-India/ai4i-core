import { Td, Text, Tr, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import type { TierTaskTypeUsage } from "../../types/usageSpend";
import { formatSpendMoneyExact, formatSpendUnitCompact } from "../../utils/usageSpendHelpers";

const childTd = { borderColor: "gray.100", py: 2 } as const;

function PeriodFigure({
  units,
  unit,
  detail,
  isTotal = false,
}: Readonly<{ units: number; unit: string; detail: string; isTotal?: boolean }>) {
  return (
    <VStack align="flex-start" spacing={0}>
      <Text fontSize="13px" fontWeight={isTotal ? "bold" : "medium"} color="gray.800">
        {formatSpendUnitCompact(units, unit)}
      </Text>
      <Text fontSize="12px" color="gray.500">
        {detail}
      </Text>
    </VStack>
  );
}

/**
 * LLM cost breakdown under a task-type row: one row per token category, in
 * the API's order, then a Total row from `periodUsage`. Figures sit under the
 * "Usage in period" column; the quota column is left blank.
 */
export function UsageSpendCostBreakdownRows({
  task,
  currency,
  leadingColSpan,
}: Readonly<{
  task: TierTaskTypeUsage;
  currency: string;
  /** Columns before "Usage in period": task type, plus tier when grouped by tier. */
  leadingColSpan: number;
}>) {
  const copy = METERING.USAGE_SPEND;
  const { periodUsage, unit } = task;

  return (
    <>
      {(periodUsage.breakdown ?? []).map((share) => (
        <Tr key={share.key} bg="gray.50">
          <Td pl={10} colSpan={leadingColSpan} {...childTd}>
            <Text fontSize="13px" color="gray.700">
              {share.label}
            </Text>
          </Td>
          <Td {...childTd}>
            <PeriodFigure
              units={share.units}
              unit={unit}
              detail={`${formatSpendMoneyExact(share.cost, currency)} · ${share.costShare.toFixed(2)}${copy.COST_SHARE_SUFFIX}`}
            />
          </Td>
          <Td {...childTd} />
        </Tr>
      ))}
      <Tr bg="gray.50">
        <Td pl={10} colSpan={leadingColSpan} {...childTd}>
          <Text fontSize="13px" fontWeight="bold" color="gray.800">
            {copy.BREAKDOWN_TOTAL}
          </Text>
        </Td>
        <Td {...childTd}>
          <PeriodFigure
            units={periodUsage.units}
            unit={unit}
            detail={formatSpendMoneyExact(periodUsage.cost, currency)}
            isTotal
          />
        </Td>
        <Td {...childTd} />
      </Tr>
    </>
  );
}
