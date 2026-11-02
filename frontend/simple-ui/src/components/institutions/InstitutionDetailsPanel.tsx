// Read-only Institution details — the Institution Admin's own institution.

import React from "react";
import {
  Alert,
  AlertIcon,
  Box,
  Card,
  CardBody,
  Center,
  HStack,
  Spinner,
  Text,
  VStack,
} from "@chakra-ui/react";
import { FiEye, FiInfo } from "react-icons/fi";
import {
  INSTITUTION,
  TIER_RATE_LIMIT_PLATFORM_DEFAULT,
  formatModelTaskTypeLabel,
} from "../../config/constants";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import {
  EMPTY_VALUE,
  dash,
  formatMonthlyQuota,
} from "../../utils/valueFormatters";
import type { TenantView, TierLimits, TierQuotaLimit } from "../../types/tenant";
import DataTable, { DATA_TABLE_HEADER_SX, type DataTableColumn } from "../common/table";
import InstitutionOverview from "./InstitutionOverview";

/** Shown for Tier/Budget when the call behind them failed — not the same as unassigned. */
const UNAVAILABLE = "Unavailable";

const QUOTA_COLUMNS: DataTableColumn<TierQuotaLimit>[] = [
  {
    id: "task_type",
    header: "Task Type",
    width: "45%",
    cell: (row) => formatModelTaskTypeLabel(row.task_type),
  },
  {
    id: "monthly_quota",
    header: "Quota",
    cell: (row) => formatMonthlyQuota(row.monthly_quota, row.unit),
  },
];

/** Rate limit and per-task-type monthly quotas of the assigned tier — view only. */
function TierUsageLimits({
  tierLimits,
}: Readonly<{ tierLimits: TierLimits | null }>) {
  const rateLimit = tierLimits?.rate_limit;
  if (!tierLimits) {
    return <Text color="ink.500">{UNAVAILABLE}</Text>;
  }
  return (
    <VStack align="stretch" spacing={4}>
      <Box>
        <Text fontWeight="semibold" color={DATA_TABLE_HEADER_SX.color} mb={1}>
          Rate Limit
        </Text>
        <Text>
          {rateLimit == null
            ? TIER_RATE_LIMIT_PLATFORM_DEFAULT
            : `${rateLimit.toLocaleString("en-US")} requests/min`}
        </Text>
      </Box>
      <Box>
        <DataTable
          variant="compact"
          columns={QUOTA_COLUMNS}
          rows={tierLimits.quotas}
          rowKey={(row) => row.task_type}
          sortable={false}
          isEmpty={tierLimits.quotas.length === 0}
          emptyMessage="No task types are configured for this tier."
          asyncStateHeight="48px"
        />
      </Box>
    </VStack>
  );
}

export type InstitutionDetailsPanelProps = Readonly<{
  institution: TenantView | null;
  /** Assigned tier name; null renders as an em dash, matching the adopter view. */
  tierName?: string | null;
  /** Assigned tier's rate limit and quotas; the section is hidden when no tier is assigned. */
  tierLimits?: TierLimits | null;
  /** Assigned budget limit; null renders as an em dash, matching the adopter view. */
  budgetLimit?: number | null;
  currency?: string;
  isLoading?: boolean;
  errorMessage?: string | null;
  /** Set when Tier/Budget could not be read; the two fields then read "Unavailable". */
  tierBudgetErrorMessage?: string | null;
}>;

/** View-only overview of the Institution Admin's own institution — no edit or delete. */
export default function InstitutionDetailsPanel({
  institution,
  tierName = null,
  tierLimits = null,
  budgetLimit = null,
  currency = "INR",
  isLoading = false,
  errorMessage = null,
  tierBudgetErrorMessage = null,
}: Readonly<InstitutionDetailsPanelProps>) {
  if (isLoading) {
    return (
      <Card>
        <CardBody>
          <Center h="240px">
            <Spinner size="lg" />
          </Center>
        </CardBody>
      </Card>
    );
  }

  if (errorMessage) {
    return (
      <Alert status="error" borderRadius="md">
        <AlertIcon />
        {errorMessage}
      </Alert>
    );
  }

  if (!institution) {
    return (
      <Alert status="info" borderRadius="md">
        <AlertIcon />
        {`Your ${INSTITUTION.toLowerCase()} details are not available right now.`}
      </Alert>
    );
  }

  const tierLabel = tierBudgetErrorMessage ? UNAVAILABLE : dash(tierName);
  let budgetLabel = EMPTY_VALUE;
  if (tierBudgetErrorMessage) {
    budgetLabel = UNAVAILABLE;
  } else if (budgetLimit != null) {
    budgetLabel = formatSpendMoney(budgetLimit, currency);
  }

  let tierExtrasContent: React.ReactNode = null;
  if (tierName && !tierBudgetErrorMessage) {
    tierExtrasContent = <TierUsageLimits tierLimits={tierLimits} />;
  } else if (tierBudgetErrorMessage) {
    tierExtrasContent = (
      <Alert status="warning" borderRadius="md">
        <AlertIcon />
        <Text fontSize="sm">{tierBudgetErrorMessage}</Text>
      </Alert>
    );
  }

  return (
    <VStack align="stretch" spacing={4} w="full">
      <HStack justify="space-between" align="center" flexWrap="wrap" gap={2}>
        <Text as="h2" fontSize="lg" fontWeight="semibold" color="ink.800" minW={0}>
          {institution.organisation}
        </Text>
        <HStack color="ink.500" spacing={2} flexShrink={0}>
          <FiEye aria-hidden />
          <Text fontSize="sm">View only</Text>
        </HStack>
      </HStack>
      <InstitutionOverview
        tenant={institution}
        tierLabel={tierLabel}
        budgetLabel={budgetLabel}
        tierExtras={tierExtrasContent}
        footer={
          <HStack
            spacing={2}
            color="ink.500"
            pt={2}
            borderTopWidth="1px"
            borderColor="ink.100"
          >
            <FiInfo aria-hidden />
            <Text fontSize="sm">
              Contact your adopter admin to request changes to these details.
            </Text>
          </HStack>
        }
      />
    </VStack>
  );
}
