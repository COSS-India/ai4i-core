import { Box, Td, Text, Tr } from "@chakra-ui/react";
import React from "react";
import type { MeteringTokenShare, ModelConsumptionRow } from "../../types/metering";
import { formatModelNativeUnits } from "../../utils/meteringFormatters";
import { sortHeaderTrailingWidthPx } from "../common/TableControls";
import { TokenShareBar } from "./UsageSpendCells";

/** Cached input is omitted when it is zero; the API already drops it, this keeps the rule local. */
function visibleShares(shares: MeteringTokenShare[] | null | undefined): MeteringTokenShare[] {
  return (shares ?? []).filter((share) => share.key !== "cached_input" || share.units > 0);
}

const childTd = { borderColor: "gray.100", py: 2 } as const;
/** Same inset as the parent row's numeric cells, so values end under the header text. */
const VALUE_INSET = `${sortHeaderTrailingWidthPx(true)}px`;
/** Equal-width digits so the share % lines up down the rows (inherited by TokenShareBar). */
const TABULAR_NUMS = { fontVariantNumeric: "tabular-nums" } as const;

/**
 * LLM token breakdown under a Model drill-down row: one row per token
 * category, in the API's order. There is no Total row: the parent row's
 * Total Native Units already shows it. Column layout mirrors the parent table
 * (7 columns): the label spans Task Type → Total Requests, the share of tokens
 * sits under Successful + Failed, and the units sit under Total Native Units.
 */
export function ModelTokenBreakdownRows({ row }: Readonly<{ row: ModelConsumptionRow }>) {
  const shares = visibleShares(row.native_breakdown);
  return (
    <>
      {shares.map((share) => (
        <Tr key={share.key} bg="gray.50">
          <Td pl={12} colSpan={4} {...childTd}>
            <Text fontSize="sm" color="gray.700">
              {share.label}
            </Text>
          </Td>
          <Td colSpan={2} {...childTd} sx={TABULAR_NUMS}>
            <Box pr={VALUE_INSET}>
              <TokenShareBar pct={share.percentage} decimals={1} />
            </Box>
          </Td>
          <Td textAlign="right" {...childTd}>
            <Text fontSize="sm" color="gray.600" whiteSpace="nowrap" pr={VALUE_INSET} sx={TABULAR_NUMS}>
              {formatModelNativeUnits(share.units)}
            </Text>
          </Td>
        </Tr>
      ))}
    </>
  );
}
