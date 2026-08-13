import { Td, Text, Tr } from "@chakra-ui/react";
import React from "react";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import type { TenantUsageItem } from "../../types/usageSpend";
import { TierBadge } from "./UsageSpendCells";

const childTd = { borderColor: "gray.100" } as const;

/**
 * Tier-level drill-down under a tenant: one row per tier showing the tier and
 * its total spend. Task-type detail lives in the tenant drawer, so it is
 * intentionally omitted here to avoid duplicating that breakdown.
 */
export function UsageSpendExpandRows({ row }: { row: TenantUsageItem }) {
  const tiers = row.tierBreakdown ?? [];

  return (
    <>
      {tiers.map((tier) => (
        <Tr key={`${row.tenantId}-${tier.tierId}`} bg="gray.50">
          <Td pl={12} colSpan={3} {...childTd}>
            <TierBadge label={tier.tierName} />
          </Td>
          <Td {...childTd}>
            <Text fontWeight="bold" fontSize="13px">
              {formatSpendMoney(tier.spend, row.currency)}
            </Text>
          </Td>
          <Td colSpan={2} {...childTd} />
        </Tr>
      ))}
    </>
  );
}
