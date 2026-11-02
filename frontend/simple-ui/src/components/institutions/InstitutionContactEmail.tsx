import { Badge, Box, HStack, Text, VStack } from "@chakra-ui/react";
import { FIELD_HINTS } from "../../config/fieldHints";
import { dash } from "../../utils/valueFormatters";
import type { TenantView } from "../../types/tenant";

type InstitutionContactEmailProps = Readonly<{
  email?: string | null;
  pendingEmail?: string | null;
  /** Compact single-line for table cells. */
  compact?: boolean;
}>;

/** Effective contact email plus optional pending-verification address (AI4IDS-3401). */
export default function InstitutionContactEmail({
  email,
  pendingEmail,
  compact = false,
}: InstitutionContactEmailProps) {
  const pending = pendingEmail?.trim() || null;

  if (pending && compact) {
    return (
      <VStack align="start" spacing={0.5} maxW="22rem" minW={0}>
        <Text fontSize="sm" isTruncated maxW="22rem">
          {dash(email)}
        </Text>
        <HStack spacing={1} maxW="22rem" minW={0}>
          <Text fontSize="xs" color="ink.500" isTruncated minW={0}>
            {pending}
          </Text>
          <Badge
            colorScheme="orange"
            fontSize="0.65rem"
            flexShrink={0}
            whiteSpace="nowrap"
          >
            {FIELD_HINTS.tenant.emailVerificationPending}
          </Badge>
        </HStack>
      </VStack>
    );
  }

  if (pending) {
    return (
      <Box>
        <Text fontSize="sm" color="ink.800" wordBreak="break-word">
          {dash(email)}
        </Text>
        <HStack mt={1} spacing={2} align="center" flexWrap="wrap">
          <Text fontSize="sm" color="ink.600" wordBreak="break-word">
            {pending}
          </Text>
          <Badge colorScheme="orange">
            {FIELD_HINTS.tenant.emailVerificationPending}
          </Badge>
        </HStack>
      </Box>
    );
  }

  return (
    <Text fontSize="sm" isTruncated={compact} maxW={compact ? "22rem" : undefined}>
      {dash(email)}
    </Text>
  );
}

/**
 * Table cell renderer — module-scoped (not redefined inside the list).
 * camelCase so Sonar does not treat it as a React component needing Readonly props.
 */
export function renderInstitutionEmailTableCell(tenant: TenantView) {
  return (
    <InstitutionContactEmail
      email={tenant.email}
      pendingEmail={tenant.pending_email}
      compact
    />
  );
}
