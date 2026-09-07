import { Td, Tr } from "@chakra-ui/react";
import React from "react";
import type { TenantUsageItem } from "../../types/usageSpend";
import { TierBadge } from "./UsageSpendCells";

const childTd = { borderColor: "gray.100" } as const;

/**
 * Tier-level drill-down under a tenant: one row per tier.
 * Task-type quota detail lives in the tenant drawer.
 */
export function UsageSpendExpandRows({
  row,
  trailingColSpan = 2,
}: Readonly<{
  row: TenantUsageItem;
  /** Number of trailing parent columns to blank out (2 with token usage, 1 without). */
  trailingColSpan?: number;
}>) {
  const tiers = row.tierBreakdown ?? [];

  return (
    <>
      {tiers.map((tier) => (
        <Tr key={`${row.tenantId}-${tier.tierId}`} bg="gray.50">
          <Td pl={12} colSpan={3} {...childTd}>
            <TierBadge label={tier.tierName} />
          </Td>
          <Td colSpan={trailingColSpan} {...childTd} />
        </Tr>
      ))}
    </>
  );
}
