import { Td, Text, Tr } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import type { ModelConsumptionRow } from "../../types/metering";
import { formatNativeConsumption } from "../../utils/meteringFormatters";

const childTd = { borderColor: "gray.100", py: 2 } as const;

/**
 * LLM token breakdown under a Model drill-down row: one row per token
 * category, in the API's order. Units sit under Native Consumption (the 5th
 * of the table's 7 columns) and the share of tokens under the two rate columns.
 */
export function ModelTokenBreakdownRows({ row }: Readonly<{ row: ModelConsumptionRow }>) {
  const section = METERING.SECTIONS.MODEL;
  return (
    <>
      {(row.native_breakdown ?? []).map((share) => (
        <Tr key={share.key} bg="gray.50">
          <Td pl={12} colSpan={4} {...childTd}>
            <Text fontSize="sm" color="gray.700">
              {share.label}
            </Text>
          </Td>
          <Td isNumeric {...childTd}>
            <Text fontSize="sm" color="gray.600">
              {formatNativeConsumption(share.units, row.native_unit_suffix)}
            </Text>
          </Td>
          <Td colSpan={2} {...childTd}>
            <Text fontSize="sm" color="gray.500">
              {share.percentage.toFixed(2)}
              {section.TOKEN_SHARE_SUFFIX}
            </Text>
          </Td>
        </Tr>
      ))}
    </>
  );
}
