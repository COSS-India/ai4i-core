import {
  Box,
  Button,
  HStack,
  Stack,
  Text,
} from "@chakra-ui/react";
import StandardModal from "../../common/StandardModal";
import type { TenantDomainMappingRow } from "../types";

export default function PiiMappingDetailModal({
  isOpen,
  onClose,
  mapping,
  onRemove,
}: {
  isOpen: boolean;
  onClose: () => void;
  mapping: TenantDomainMappingRow | null;
  onRemove: (tenantId: string) => void;
}) {
  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Tenant mapping details"
      size="lg"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {mapping ? (
            <Button
              colorScheme="red"
              variant="outline"
              onClick={() => {
                onRemove(mapping.tenant_id);
              }}
            >
              Remove mapping
            </Button>
          ) : null}
        </HStack>
      }
    >
      {mapping ? (
        <Stack spacing={4}>
          <Text fontSize="xs" color="gray.500" fontFamily="mono">
            {mapping.tenant_id}
          </Text>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Tenant ID
            </Text>
            <Text fontSize="sm" fontFamily="mono">
              {mapping.tenant_id}
            </Text>
          </Box>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Domain
            </Text>
            <Text fontSize="sm">{mapping.domain_id}</Text>
          </Box>
          <Text fontSize="sm" color="gray.600">
            Updated {mapping.updated_at ? new Date(mapping.updated_at).toLocaleString() : "—"}
          </Text>
        </Stack>
      ) : null}
    </StandardModal>
  );
}
