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
  formatTenantStatusLabel,
  getTenantStatusColorScheme,
} from "../../config/constants";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import { EMPTY_VALUE, dash, fmtDate } from "../../utils/valueFormatters";
import type { TenantView } from "../../types/tenant";

/** Shown for Tier/Budget when the call behind them failed — not the same as unassigned. */
const UNAVAILABLE = "Unavailable";

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

export interface InstitutionDetailsPanelProps {
  institution: TenantView | null;
  /** Assigned tier name; null renders as an em dash, matching the adopter view. */
  tierName?: string | null;
  /** Assigned budget limit; null renders as an em dash, matching the adopter view. */
  budgetLimit?: number | null;
  currency?: string;
  isLoading?: boolean;
  errorMessage?: string | null;
  /** Set when Tier/Budget could not be read; the two fields then read "Unavailable". */
  tierBudgetErrorMessage?: string | null;
}

/** View-only card of the Institution Admin's own institution — no edit or delete. */
export default function InstitutionDetailsPanel({
  institution,
  tierName = null,
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
            <Spinner size="lg" color="orange.500" />
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
          <HStack spacing={2} color="gray.500" flexShrink={0}>
            <FiEye aria-hidden />
            <Text fontSize="sm">View only</Text>
          </HStack>
        </HStack>
      </CardHeader>

      <CardBody borderTopWidth="1px" borderColor="gray.100">
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3}>
          <DetailField label={`${INSTITUTION} ID`}>
            <Text fontFamily="mono">{institution.tenant_id}</Text>
          </DetailField>
          <DetailField label="Status">
            <Badge colorScheme={getTenantStatusColorScheme(institution.status)}>
              {formatTenantStatusLabel(institution.status)}
            </Badge>
          </DetailField>
          <DetailField label="Contact Name">
            <Text wordBreak="break-word">{dash(institution.contact_name)}</Text>
          </DetailField>
          <DetailField label="Contact Email">
            <Text wordBreak="break-word">{dash(institution.email)}</Text>
          </DetailField>
          <DetailField label="Contact Phone">
            <Text>{dash(institution.phone_number)}</Text>
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

        {tierBudgetErrorMessage && (
          <Alert status="warning" borderRadius="md" mt={4}>
            <AlertIcon />
            <Text fontSize="sm">{tierBudgetErrorMessage}</Text>
          </Alert>
        )}
      </CardBody>

      <CardFooter borderTopWidth="1px" borderColor="gray.100" pt={4}>
        <HStack spacing={2} color="gray.500">
          <FiInfo aria-hidden />
          <Text fontSize="sm">
            Contact your adopter admin to request changes to these details.
          </Text>
        </HStack>
      </CardFooter>
    </Card>
  );
}
