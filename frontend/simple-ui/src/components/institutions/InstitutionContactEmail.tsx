import { Badge, Box, HStack, Text, VStack } from "@chakra-ui/react";
import { FIELD_HINTS } from "../../config/fieldHints";
import { dash } from "../../utils/valueFormatters";

type InstitutionContactEmailProps = {
  email?: string | null;
  pendingEmail?: string | null;
  /** Compact single-line for table cells. */
  compact?: boolean;
};

/** Effective contact email plus optional pending-verification address (AI4IDS-3401). */
export default function InstitutionContactEmail({
  email,
  pendingEmail,
  compact = false,
}: InstitutionContactEmailProps) {
  const pending = pendingEmail?.trim() || null;

  if (!pending) {
    return (
      <Text fontSize="sm" isTruncated={compact} maxW={compact ? "260px" : undefined}>
        {dash(email)}
      </Text>
    );
  }

  if (compact) {
    return (
      <VStack align="start" spacing={0.5} maxW="280px">
        <Text fontSize="sm" isTruncated maxW="280px">
          {dash(email)}
        </Text>
        <HStack spacing={1} maxW="280px">
          <Text fontSize="xs" color="ink.500" isTruncated>
            {pending}
          </Text>
          <Badge colorScheme="orange" fontSize="0.65rem" flexShrink={0}>
            {FIELD_HINTS.tenant.emailVerificationPending}
          </Badge>
        </HStack>
      </VStack>
    );
  }

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
