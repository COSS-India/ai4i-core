// Read-only Institution details — the Institution Admin's own institution.

import React from "react";
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  Center,
  HStack,
  Heading,
  SimpleGrid,
  Spinner,
  Text,
  Tooltip,
} from "@chakra-ui/react";
import { FiEye, FiInfo } from "react-icons/fi";
import {
  INSTITUTION,
  TIER_RATE_LIMIT_PLATFORM_DEFAULT,
  formatModelTaskTypeLabel,
  formatTenantStatusLabel,
  getTenantStatusColorScheme,
} from "../../config/constants";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import {
  EMPTY_VALUE,
  dash,
  fmtDate,
  formatMonthlyQuota,
} from "../../utils/valueFormatters";
import type { TenantView, TierLimits, TierQuotaLimit } from "../../types/tenant";
import DataTable, { DATA_TABLE_HEADER_SX, type DataTableColumn } from "../common/table";
import InstitutionForm from "./InstitutionForm";

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

function DetailField({
  label,
  children,
}: Readonly<{
  label: string;
  children: React.ReactNode;
}>) {
  return (
    <Box>
      <Text fontWeight="semibold">{label}</Text>
      {children}
    </Box>
  );
}

/** Rate limit and per-task-type monthly quotas of the assigned tier — view only. */
function TierUsageLimits({
  tierLimits,
}: Readonly<{ tierLimits: TierLimits | null }>) {
  const rateLimit = tierLimits?.rate_limit;
  return (
    <Box borderTopWidth="1px" borderColor="ink.100" mt={4} pt={4}>
      <Heading size="sm" mb={3}>
        Tier and usage limits
      </Heading>
      {tierLimits ? (
        <>
          <Box>
            <Text fontWeight="semibold" color={DATA_TABLE_HEADER_SX.color}>
              Rate Limit
            </Text>
            <Text>
              {rateLimit == null
                ? TIER_RATE_LIMIT_PLATFORM_DEFAULT
                : `${rateLimit.toLocaleString("en-US")} requests/min`}
            </Text>
          </Box>
          <Box mt={4}>
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
        </>
      ) : (
        <Text color="ink.500">{UNAVAILABLE}</Text>
      )}
    </Box>
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

/** View-only card of the Institution Admin's own institution — no edit or delete. */
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

  return (
    <Card>
      <CardHeader>
        <HStack justify="space-between" align="center" flexWrap="wrap" gap={2}>
          <HStack flex="1" minW={0} spacing={3}>
            <Tooltip
              label={institution.organisation}
              placement="top"
              hasArrow
              openDelay={300}
            >
              <Heading size="md" isTruncated minW={0}>
                {institution.organisation}
              </Heading>
            </Tooltip>
            <Badge
              colorScheme={getTenantStatusColorScheme(institution.status)}
              flexShrink={0}
            >
              {formatTenantStatusLabel(institution.status)}
            </Badge>
          </HStack>
          <HStack spacing={2} color="ink.500" flexShrink={0}>
            <FiEye aria-hidden />
            <Text fontSize="sm">View only</Text>
          </HStack>
        </HStack>
      </CardHeader>

      <CardBody borderTopWidth="1px" borderColor="ink.100">
        <InstitutionForm
          mode="view"
          showOrganisation={false}
          values={{
            organisation: institution.organisation,
            contact_name: institution.contact_name ?? "",
            email: institution.email ?? "",
            phone_number: institution.phone_number ?? "",
          }}
          pendingEmail={institution.pending_email}
        />
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3} mt={4}>
          <DetailField label={`${INSTITUTION} ID`}>
            <Text fontFamily="mono">{institution.tenant_id}</Text>
          </DetailField>
          <DetailField label="Status">
            <Badge colorScheme={getTenantStatusColorScheme(institution.status)}>
              {formatTenantStatusLabel(institution.status)}
            </Badge>
          </DetailField>
          <DetailField label="Created">
            <Text>{fmtDate(institution.created_at)}</Text>
          </DetailField>
          <DetailField label="Tier Assigned">
            <Text>{tierBudgetErrorMessage ? UNAVAILABLE : dash(tierName)}</Text>
          </DetailField>
          <DetailField label="Budget Assigned">
            <Text>
              {tierBudgetErrorMessage
                ? UNAVAILABLE
                : budgetLimit != null
                  ? formatSpendMoney(budgetLimit, currency)
                  : EMPTY_VALUE}
            </Text>
          </DetailField>
        </SimpleGrid>

        {tierName && !tierBudgetErrorMessage && (
          <TierUsageLimits tierLimits={tierLimits} />
        )}

        {tierBudgetErrorMessage && (
          <Alert status="warning" borderRadius="md" mt={4}>
            <AlertIcon />
            <Text fontSize="sm">{tierBudgetErrorMessage}</Text>
          </Alert>
        )}
      </CardBody>

      <CardFooter borderTopWidth="1px" borderColor="ink.100" pt={4}>
        <HStack spacing={2} color="ink.500">
          <FiInfo aria-hidden />
          <Text fontSize="sm">
            Contact your adopter admin to request changes to these details.
          </Text>
        </HStack>
      </CardFooter>
    </Card>
  );
}
