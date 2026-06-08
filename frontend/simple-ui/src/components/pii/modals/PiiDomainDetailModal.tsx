import {
  Badge,
  Button,
  Heading,
  HStack,
  Stack,
  Text,
} from "@chakra-ui/react";
import StandardModal from "../../common/StandardModal";
import type { Domain } from "../types";

export default function PiiDomainDetailModal({
  isOpen,
  onClose,
  domain,
  isPendingActivation,
  onEditRules,
}: {
  isOpen: boolean;
  onClose: () => void;
  domain: Domain | null;
  isPendingActivation: boolean;
  onEditRules: (domainId: string) => void;
}) {
  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Domain details"
      size="lg"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {domain ? (
            <Button
              colorScheme="blue"
              onClick={() => {
                onEditRules(domain.domain_id);
              }}
            >
              Edit policy rules
            </Button>
          ) : null}
        </HStack>
      }
    >
      {domain ? (
        <Stack spacing={4}>
          <Text fontSize="xs" color="gray.500" fontFamily="mono">
            {domain.domain_id}
          </Text>
          <Heading size="md">{domain.domain_id.toUpperCase()}</Heading>
          <HStack spacing={2}>
            <Badge colorScheme={domain.is_active ? "green" : "gray"}>
              {domain.is_active ? "Active" : "Inactive"}
            </Badge>
            <Badge colorScheme={isPendingActivation ? "blue" : "purple"}>
              {isPendingActivation ? "Selected for activation" : "Not in activation set"}
            </Badge>
          </HStack>
          {domain.description ? (
            <Text fontSize="sm" color="gray.700">
              {domain.description}
            </Text>
          ) : (
            <Text fontSize="sm" color="gray.500">
              No description
            </Text>
          )}
        </Stack>
      ) : null}
    </StandardModal>
  );
}
